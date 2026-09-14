"""API-level subscription/push-subscription/status tests."""
from datetime import time

import pytest
from pydantic import ValidationError

from app.api.alerting import (
    create_subscription,
    list_subscriptions,
    register_push_subscription,
    subscription_status,
    unregister_push_subscription,
    update_subscription_active,
)
from app.models import Beach
from app.schemas import PushSubscriptionCreate, SubscriptionCreate


async def _seed_beach(db_session):
    beach = Beach(id="herzliya", name="Herzliya", lat=32.1660, lon=34.7960, shoreline_bearing=301.1)
    db_session.add(beach)
    await db_session.commit()


@pytest.mark.asyncio
async def test_create_and_list_subscription(db_session):
    await _seed_beach(db_session)
    body = SubscriptionCreate(
        user_id="u1", beach_id="herzliya", min_height=1.0, max_height=None,
        time_window_start=time(6, 0), time_window_end=time(9, 0),
    )
    created = await create_subscription(body, session=db_session)
    assert created.id is not None
    assert created.operating_point == "balanced"

    listed = await list_subscriptions(user_id="u1", session=db_session)
    assert len(listed) == 1
    assert listed[0].id == created.id


@pytest.mark.asyncio
async def test_unknown_beach_rejected(db_session):
    from fastapi import HTTPException

    body = SubscriptionCreate(
        user_id="u1", beach_id="does_not_exist",
        time_window_start=time(6, 0), time_window_end=time(9, 0),
    )
    with pytest.raises(HTTPException) as exc_info:
        await create_subscription(body, session=db_session)
    assert exc_info.value.status_code == 404


def test_max_height_below_min_height_rejected():
    with pytest.raises(ValidationError):
        SubscriptionCreate(
            user_id="u1", beach_id="herzliya", min_height=1.5, max_height=1.0,
            time_window_start=time(6, 0), time_window_end=time(9, 0),
        )


def test_height_out_of_sane_range_rejected():
    with pytest.raises(ValidationError):
        SubscriptionCreate(
            user_id="u1", beach_id="herzliya", min_height=50.0,
            time_window_start=time(6, 0), time_window_end=time(9, 0),
        )


def test_direction_out_of_range_rejected():
    with pytest.raises(ValidationError):
        SubscriptionCreate(
            user_id="u1", beach_id="herzliya", swell_dir_min=400.0,
            time_window_start=time(6, 0), time_window_end=time(9, 0),
        )


def test_unknown_operating_point_rejected():
    with pytest.raises(ValidationError):
        SubscriptionCreate(
            user_id="u1", beach_id="herzliya", operating_point="yolo",
            time_window_start=time(6, 0), time_window_end=time(9, 0),
        )


def test_midnight_crossing_window_is_legal():
    # Must NOT raise -- crossing midnight is a legal window, handled in matching, not
    # rejected at the API boundary.
    SubscriptionCreate(
        user_id="u1", beach_id="herzliya",
        time_window_start=time(22, 0), time_window_end=time(2, 0),
    )


@pytest.mark.asyncio
async def test_deactivate_subscription(db_session):
    await _seed_beach(db_session)
    body = SubscriptionCreate(
        user_id="u1", beach_id="herzliya",
        time_window_start=time(6, 0), time_window_end=time(9, 0),
    )
    created = await create_subscription(body, session=db_session)
    updated = await update_subscription_active(created.id, active=False, session=db_session)
    assert updated.active is False


@pytest.mark.asyncio
async def test_register_and_unregister_push_subscription(db_session):
    body = PushSubscriptionCreate(user_id="u1", endpoint="https://push.example/1", p256dh="k", auth="a")
    created = await register_push_subscription(body, session=db_session)
    assert created.active is True

    await unregister_push_subscription(created.id, session=db_session)
    await db_session.refresh(created)
    assert created.active is False


@pytest.mark.asyncio
async def test_reregistering_same_endpoint_reactivates_rather_than_duplicating(db_session):
    body = PushSubscriptionCreate(user_id="u1", endpoint="https://push.example/dup", p256dh="k1", auth="a1")
    first = await register_push_subscription(body, session=db_session)
    await unregister_push_subscription(first.id, session=db_session)

    body2 = PushSubscriptionCreate(user_id="u1", endpoint="https://push.example/dup", p256dh="k2", auth="a2")
    second = await register_push_subscription(body2, session=db_session)
    assert second.id == first.id
    assert second.active is True


@pytest.mark.asyncio
async def test_status_for_unknown_subscription_returns_none(db_session):
    from app.alerting.status import get_subscription_status

    result = await get_subscription_status(db_session, 999999)
    assert result is None


@pytest.mark.asyncio
async def test_status_endpoint_reflects_inactive_subscription(db_session):
    await _seed_beach(db_session)
    body = SubscriptionCreate(
        user_id="u1", beach_id="herzliya",
        time_window_start=time(6, 0), time_window_end=time(9, 0),
    )
    created = await create_subscription(body, session=db_session)
    await update_subscription_active(created.id, active=False, session=db_session)

    status = await subscription_status(created.id, session=db_session)
    assert status.active is False
    assert "inactive" in status.message
