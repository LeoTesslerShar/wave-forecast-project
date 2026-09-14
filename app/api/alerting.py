from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerting.status import get_subscription_status
from app.db import get_session
from app.models import Beach, PushSubscription, Subscription
from app.schemas import (
    PushSubscriptionCreate,
    PushSubscriptionOut,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionStatusOut,
)

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
