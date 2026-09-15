from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerting.slot_watch import watch_from_for
from app.alerting.status import get_subscription_status
from app.db import get_session
from app.models import Beach, PushSubscription, SlotWatch, Subscription
from app.schemas import (
    PushConfigOut,
    PushSubscriptionCreate,
    PushSubscriptionOut,
    SlotWatchCreate,
    SlotWatchOut,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionStatusOut,
)
from app.settings import get_settings

router = APIRouter()


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=201)
async def create_subscription(
    body: SubscriptionCreate, session: AsyncSession = Depends(get_session)
) -> Subscription:
    beach = await session.get(Beach, body.beach_id)
    if beach is None:
        raise HTTPException(status_code=404, detail=f"unknown beach '{body.beach_id}'")

    sub = Subscription(
        user_id=body.user_id,
        beach_id=body.beach_id,
        min_height=body.min_height,
        max_height=body.max_height,
        swell_dir_min=body.swell_dir_min,
        swell_dir_max=body.swell_dir_max,
        time_window_start=body.time_window_start,
        time_window_end=body.time_window_end,
        operating_point=body.operating_point,
        active=True,
        created_at=datetime.now(UTC),
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(user_id: str, session: AsyncSession = Depends(get_session)) -> list[Subscription]:
    result = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
    return list(result.scalars().all())


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionOut)
async def update_subscription_active(
    subscription_id: int, active: bool, session: AsyncSession = Depends(get_session)
) -> Subscription:
    sub = await session.get(Subscription, subscription_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="unknown subscription")
    sub.active = active
    await session.commit()
    await session.refresh(sub)
    return sub


@router.get("/subscriptions/{subscription_id}/status", response_model=SubscriptionStatusOut)
async def subscription_status(subscription_id: int, session: AsyncSession = Depends(get_session)):
    """prompts/phase-4-alerting.md section 7: a status a user can check, distinct from
    silence that looks like the system stopped working."""
    status = await get_subscription_status(session, subscription_id)
    if status is None:
        raise HTTPException(status_code=404, detail="unknown subscription")
    return status


@router.post("/push-subscriptions", response_model=PushSubscriptionOut, status_code=201)
async def register_push_subscription(
    body: PushSubscriptionCreate, session: AsyncSession = Depends(get_session)
) -> PushSubscription:
    existing = (
        await session.execute(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    ).scalar_one_or_none()
    if existing is not None:
        existing.active = True
        existing.user_id = body.user_id
        existing.p256dh = body.p256dh
        existing.auth = body.auth
        await session.commit()
        await session.refresh(existing)
        return existing

    push_sub = PushSubscription(
        user_id=body.user_id,
        endpoint=body.endpoint,
        p256dh=body.p256dh,
        auth=body.auth,
        active=True,
        created_at=datetime.now(UTC),
    )
    session.add(push_sub)
    await session.commit()
    await session.refresh(push_sub)
    return push_sub


@router.delete("/push-subscriptions/{push_subscription_id}", status_code=204)
async def unregister_push_subscription(push_subscription_id: int, session: AsyncSession = Depends(get_session)):
    push_sub = await session.get(PushSubscription, push_subscription_id)
    if push_sub is None:
        raise HTTPException(status_code=404, detail="unknown push subscription")
    push_sub.active = False
    await session.commit()


@router.get("/push-config", response_model=PushConfigOut)
async def push_config() -> PushConfigOut:
    """Exposes the VAPID *public* key to the browser -- pushManager.subscribe(...) needs it
    as applicationServerKey. The private key (app/settings.py) never leaves this function."""
    return PushConfigOut(vapid_public_key=get_settings().vapid_public_key)


@router.post("/slot-watches", response_model=SlotWatchOut, status_code=201)
async def create_slot_watch(body: SlotWatchCreate, session: AsyncSession = Depends(get_session)) -> SlotWatch:
    beach = await session.get(Beach, body.beach_id)
    if beach is None:
        raise HTTPException(status_code=404, detail=f"unknown beach '{body.beach_id}'")

    now = datetime.now(UTC)
    settings = get_settings()
    if body.valid_at <= now:
        raise HTTPException(status_code=422, detail="valid_at must be in the future")
    if body.valid_at > now + timedelta(hours=settings.forecast_hours_ahead):
        raise HTTPException(
            status_code=422,
            detail=f"valid_at is beyond the {settings.forecast_hours_ahead}h forecast horizon",
        )

    # watch_from can legally land in the past -- a slot tapped when it's already inside the
    # 12h window is meant to be evaluated on the very next dispatcher tick, not rejected.
    watch = SlotWatch(
        user_id=body.user_id,
        beach_id=body.beach_id,
        valid_at=body.valid_at,
        watch_from=watch_from_for(body.valid_at),
        status="pending",
        created_at=now,
    )
    session.add(watch)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        # UniqueConstraint("user_id", "beach_id", "valid_at") -- double-tapping the same
        # slot must be idempotent, not a 500. Return the existing row.
        existing = (
            await session.execute(
                select(SlotWatch).where(
                    SlotWatch.user_id == body.user_id,
                    SlotWatch.beach_id == body.beach_id,
                    SlotWatch.valid_at == body.valid_at,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        return existing
    await session.refresh(watch)
    return watch


@router.get("/slot-watches", response_model=list[SlotWatchOut])
async def list_slot_watches(user_id: str, session: AsyncSession = Depends(get_session)) -> list[SlotWatch]:
    result = await session.execute(select(SlotWatch).where(SlotWatch.user_id == user_id))
    return list(result.scalars().all())


@router.delete("/slot-watches/{slot_watch_id}", status_code=204)
async def cancel_slot_watch(slot_watch_id: int, session: AsyncSession = Depends(get_session)):
    watch = await session.get(SlotWatch, slot_watch_id)
    if watch is None:
        raise HTTPException(status_code=404, detail="unknown slot watch")
    # Soft, same as every other delete in this file. A watch the user cancels before it
    # ever alerted must not later fire -- the dispatcher only touches 'pending'/'alerted'.
    watch.status = "cancelled"
    await session.commit()
