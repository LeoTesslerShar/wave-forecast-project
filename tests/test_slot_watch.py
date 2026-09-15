"""SlotWatch state machine -- app/alerting/slot_watch.py, app/models.py::SlotWatch.
Real Postgres via db_session (see tests/conftest.py), no live network: push delivery is
exercised through deliver_to_user with zero registered PushSubscription rows for the test
user, so it runs its real code path (look up devices, find none, no-op) without needing to
mock pywebpush -- same effect as app/alerting/push.py's own "blank VAPID keys" degradation.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.alerting.slot_watch import QUALIFY_SCORE, WATCH_LEAD_HOURS, run_due_slot_watches, watch_from_for
from app.api.alerting import create_slot_watch
from app.models import Beach, Forecast, SlotWatch
from app.schemas import SlotWatchCreate

HERZLIYA_BEARING = 301.1


async def _seed_beach(db_session) -> Beach:
    beach = Beach(id="herzliya", name="Herzliya", lat=32.1660, lon=34.7960, shoreline_bearing=HERZLIYA_BEARING)
    db_session.add(beach)
    await db_session.commit()
    return beach


async def _seed_forecast(db_session, valid_at: datetime, *, good: bool) -> None:
    """`good=True` -> a clean, well-sized, offshore hour that scores well above
    QUALIFY_SCORE. `good=False` -> small and onshore, capped well below it -- see
    app/quality/verdict.py's SIZE_CEILING/WIND_CEILING (a 0.4m surf-height day caps at 2)."""
    issued_at = datetime.now(UTC)
    if good:
        kwargs = dict(
            wave_height=1.6, wave_direction=HERZLIYA_BEARING, wave_peak_period=9.0,
            swell_wave_height=1.5, swell_wave_direction=HERZLIYA_BEARING, wind_wave_height=0.1,
            wind_speed_10m=8.0, wind_direction_10m=(HERZLIYA_BEARING + 180) % 360, wind_gusts_10m=10.0,
        )
    else:
        kwargs = dict(
            wave_height=0.5, wave_direction=HERZLIYA_BEARING, wave_peak_period=6.0,
            swell_wave_height=0.45, swell_wave_direction=HERZLIYA_BEARING, wind_wave_height=0.1,
            wind_speed_10m=8.0, wind_direction_10m=HERZLIYA_BEARING, wind_gusts_10m=10.0,  # onshore
        )
    db_session.add(Forecast(beach_id="herzliya", issued_at=issued_at, valid_at=valid_at, fetched_at=issued_at, **kwargs))
    await db_session.commit()


@pytest.mark.asyncio
async def test_create_via_api_is_idempotent_on_double_tap(db_session):
    await _seed_beach(db_session)
    valid_at = datetime.now(UTC) + timedelta(hours=20)
    body = SlotWatchCreate(user_id="u1", beach_id="herzliya", valid_at=valid_at)

    first = await create_slot_watch(body, session=db_session)
    second = await create_slot_watch(body, session=db_session)

    assert first.id == second.id
    rows = (await db_session.execute(select(SlotWatch).where(SlotWatch.user_id == "u1"))).scalars().all()
    assert len(rows) == 1
    assert rows[0].watch_from == valid_at - timedelta(hours=WATCH_LEAD_HOURS)


@pytest.mark.asyncio
async def test_watch_outside_the_lead_window_is_not_evaluated(db_session):
    """A watch on a slot far in the future stays untouched -- forecasts this far out
    aren't trustworthy enough to act on (docs/DECISIONS.md)."""
    await _seed_beach(db_session)
    valid_at = datetime.now(UTC) + timedelta(hours=48)
    await _seed_forecast(db_session, valid_at, good=True)  # would qualify if evaluated
    watch = SlotWatch(
        user_id="u1", beach_id="herzliya", valid_at=valid_at,
        watch_from=watch_from_for(valid_at), status="pending", created_at=datetime.now(UTC),
    )
    db_session.add(watch)
    await db_session.commit()

    counts = await run_due_slot_watches(db_session)
    assert counts == {"alerted": 0, "cancelled": 0, "expired": 0, "none": 0, "errors": 0}

    await db_session.refresh(watch)
    assert watch.status == "pending"


@pytest.mark.asyncio
async def test_inside_window_but_below_bar_stays_silent(db_session):
    await _seed_beach(db_session)
    valid_at = datetime.now(UTC) + timedelta(hours=6)
    await _seed_forecast(db_session, valid_at, good=False)
    watch = SlotWatch(
        user_id="u1", beach_id="herzliya", valid_at=valid_at,
        watch_from=watch_from_for(valid_at), status="pending", created_at=datetime.now(UTC),
    )
    db_session.add(watch)
    await db_session.commit()

    counts = await run_due_slot_watches(db_session)
    assert counts["alerted"] == 0
    assert counts["none"] == 1

    await db_session.refresh(watch)
    assert watch.status == "pending"


@pytest.mark.asyncio
async def test_crossing_the_bar_fires_exactly_one_alert_and_does_not_refire(db_session):
    await _seed_beach(db_session)
    valid_at = datetime.now(UTC) + timedelta(hours=6)
    await _seed_forecast(db_session, valid_at, good=True)
    watch = SlotWatch(
        user_id="u1", beach_id="herzliya", valid_at=valid_at,
        watch_from=watch_from_for(valid_at), status="pending", created_at=datetime.now(UTC),
    )
    db_session.add(watch)
    await db_session.commit()

    first = await run_due_slot_watches(db_session)
    assert first["alerted"] == 1

    await db_session.refresh(watch)
    assert watch.status == "alerted"
    assert watch.alerted_at is not None
    assert watch.conditions_snapshot["quality_score"] >= QUALIFY_SCORE

    second = await run_due_slot_watches(db_session)
    assert second["alerted"] == 0
    assert second["none"] == 1  # still qualifies, but already told -- no re-fire


@pytest.mark.asyncio
async def test_falling_back_below_the_bar_sends_one_cancellation(db_session):
    await _seed_beach(db_session)
    valid_at = datetime.now(UTC) + timedelta(hours=6)
    await _seed_forecast(db_session, valid_at, good=True)
    watch = SlotWatch(
        user_id="u1", beach_id="herzliya", valid_at=valid_at,
        watch_from=watch_from_for(valid_at), status="pending", created_at=datetime.now(UTC),
    )
    db_session.add(watch)
    await db_session.commit()

    await run_due_slot_watches(db_session)
    await db_session.refresh(watch)
    assert watch.status == "alerted"

    # The forecast refreshes and the window falls apart -- a newer issued_at row for the
    # same valid_at, which get_latest_forecasts picks up as the current truth.
    await _seed_forecast(db_session, valid_at, good=False)

    counts = await run_due_slot_watches(db_session)
    assert counts["cancelled"] == 1

    await db_session.refresh(watch)
    assert watch.status == "cancelled"
    assert watch.conditions_snapshot["quality_score"] < QUALIFY_SCORE

    # And it must not cancel a second time.
    again = await run_due_slot_watches(db_session)
    assert again["cancelled"] == 0
    assert again["none"] == 0  # cancelled is a terminal status -- not selected as due at all


@pytest.mark.asyncio
async def test_a_slot_that_passes_without_qualifying_expires_silently(db_session):
    await _seed_beach(db_session)
    valid_at = datetime.now(UTC) - timedelta(minutes=5)  # already passed
    watch = SlotWatch(
        user_id="u1", beach_id="herzliya", valid_at=valid_at,
        watch_from=watch_from_for(valid_at), status="pending", created_at=datetime.now(UTC),
    )
    db_session.add(watch)
    await db_session.commit()

    counts = await run_due_slot_watches(db_session)
    assert counts["expired"] == 1
    assert counts["alerted"] == 0

    await db_session.refresh(watch)
    assert watch.status == "expired"
