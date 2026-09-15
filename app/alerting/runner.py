"""Evaluates one Subscription against current forecasts and decides whether to send an
alert, an update, or a cancellation -- prompts/phase-4-alerting.md sections 2-3.

Idempotency (acceptance check 3): the whole evaluate-and-maybe-send sequence for one
(subscription, target_date) runs inside a transaction that takes a row lock on the
Subscription (`SELECT ... FOR UPDATE`). Two concurrent evaluations of the same
subscription serialise on that lock -- the second one, after the first commits, re-reads
the latest AlertSent row and finds nothing material changed, so it sends nothing. This is
a real lock against a real Postgres, not a mock -- see tests/test_alerting_idempotency.py,
which runs two overlapping evaluations against the same database.
"""
import logging
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerting.calibration import describe_operating_point
from app.alerting.matching import best_cluster, cluster_qualifying_hours, hour_qualifies
from app.alerting.material_change import Snapshot, is_material_change
from app.alerting.notification import build_payload
from app.alerting.push import PushResult, send_push
from app.alerting.timewindow import local_date_range_for_utc_now, window_utc_for_date
from app.logging_utils import log_event
from app.models import AlertSent, Beach, PushSubscription, Subscription
from app.quality.apply import build_quality
from app.queries import get_latest_forecasts
from app.settings import get_settings

logger = logging.getLogger("alerting.runner")


async def _latest_alert(session: AsyncSession, subscription_id: int, target_date: date) -> AlertSent | None:
    stmt = (
        select(AlertSent)
        .where(AlertSent.subscription_id == subscription_id, AlertSent.target_date == target_date)
        .order_by(AlertSent.sent_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


def _cluster_to_snapshot(cluster, operating_point: str, effective_threshold: float | None) -> Snapshot:
    best_hour = max(cluster.hours, key=lambda h: h.hour.quality_score).hour
    heights = [
        h.hour.size.wave_height_estimate for h in cluster.hours if h.hour.size.wave_height_estimate is not None
    ]
    return Snapshot(
        window_start=cluster.start,
        window_end=cluster.end,
        height_estimate_m=round(sum(heights) / len(heights), 2) if heights else 0.0,
        height_range_m=(round(min(heights), 2), round(max(heights), 2)) if heights else (0.0, 0.0),
        quality_verdict=best_hour.quality_verdict,
        quality_score=best_hour.quality_score,
        operating_point=operating_point,
        effective_threshold_m=effective_threshold,
    )


async def evaluate_subscription_for_date(
    session: AsyncSession, subscription_id: int, target_date: date, *, now_utc: datetime | None = None
) -> str:
    """Returns the action taken: 'alert' | 'update' | 'cancellation' | 'none'."""
    now_utc = now_utc or datetime.now(UTC)

    # Row lock -- see module docstring on why this is the idempotency guard.
    sub = (
        await session.execute(select(Subscription).where(Subscription.id == subscription_id).with_for_update())
    ).scalar_one_or_none()
    if sub is None or not sub.active:
        return "none"

    beach = await session.get(Beach, sub.beach_id)
    window_start, window_end = window_utc_for_date(target_date, sub.time_window_start, sub.time_window_end)

    forecasts = await get_latest_forecasts(session, sub.beach_id, window_start, window_end)
    forecasts.sort(key=lambda f: f.valid_at)
    quality_rows = [build_quality(beach, f) for f in forecasts]

    matches = [hour_qualifies(f, q, sub) for f, q in zip(forecasts, quality_rows, strict=True)]
    clusters = cluster_qualifying_hours(matches)
    cluster = best_cluster(clusters)

    effective_threshold = None
    operating_effect = None
    if sub.min_height is not None:
        operating_effect = describe_operating_point(sub.min_height, sub.operating_point)
        effective_threshold = operating_effect.effective_threshold_m

    last_alert = await _latest_alert(session, sub.id, target_date)
    last_was_cancellation = last_alert is not None and last_alert.kind == "cancellation"
    has_active_prior = last_alert is not None and not last_was_cancellation

    action: str
    new_snapshot: Snapshot | None = None

    if cluster is None:
        action = "cancellation" if has_active_prior else "none"
    else:
        new_snapshot = _cluster_to_snapshot(cluster, sub.operating_point, effective_threshold)
        if not has_active_prior:
            action = "alert"
        else:
            old_snapshot = Snapshot.from_dict(last_alert.conditions_snapshot)
            material, reason = is_material_change(old_snapshot, new_snapshot)
            if material:
                action = "update"
                log_event(logger, logging.INFO, "material change detected", subscription_id=sub.id, reason=reason)
            else:
                action = "none"

    if action == "none":
        return "none"

    kind = action
    if kind == "cancellation":
        snapshot_to_store = Snapshot.from_dict(last_alert.conditions_snapshot)
    else:
        snapshot_to_store = new_snapshot

    session.add(
        AlertSent(
            subscription_id=sub.id,
            target_date=target_date,
            kind=kind,
            window_start=snapshot_to_store.window_start,
            window_end=snapshot_to_store.window_end,
            conditions_snapshot=snapshot_to_store.to_dict(),
            sent_at=now_utc,
        )
    )
    await session.commit()

    if kind != "cancellation" and cluster is not None:
        payload = build_payload(beach, sub, cluster, kind, operating_effect)
    else:
        payload = {
            "title": f"{beach.name_he or beach.name}: החלון כבר לא מתאים",
            "beach_id": beach.id,
            "kind": "cancellation",
            "window_start": snapshot_to_store.window_start.isoformat(),
            "window_end": snapshot_to_store.window_end.isoformat(),
        }

    await deliver_to_user(session, sub.user_id, payload)
    log_event(logger, logging.INFO, "alert action taken", subscription_id=sub.id, target_date=str(target_date), kind=kind)
    return kind


async def deliver_to_user(session: AsyncSession, user_id: str, payload: dict) -> None:
    push_subs = (
        await session.execute(
            select(PushSubscription).where(PushSubscription.user_id == user_id, PushSubscription.active.is_(True))
        )
    ).scalars().all()

    for push_sub in push_subs:
        result = send_push(push_sub, payload)
        if result == PushResult.EXPIRED:
            push_sub.active = False
    await session.commit()


async def run_alert_evaluation(session: AsyncSession, *, now_utc: datetime | None = None) -> dict:
    """Evaluates every active subscription over the next
    `ALERT_EVALUATION_DAYS_AHEAD` local calendar days. Never raises -- one subscription's
    failure is logged and does not block the others (hard rule 7)."""
    settings = get_settings()
    now_utc = now_utc or datetime.now(UTC)
    dates = local_date_range_for_utc_now(now_utc, settings.alert_evaluation_days_ahead)

    sub_ids = (
        await session.execute(select(Subscription.id).where(Subscription.active.is_(True)))
    ).scalars().all()

    counts = {"alert": 0, "update": 0, "cancellation": 0, "none": 0, "errors": 0}
    for sub_id in sub_ids:
        for target_date in dates:
            try:
                action = await evaluate_subscription_for_date(session, sub_id, target_date, now_utc=now_utc)
                counts[action] += 1
            except Exception as exc:  # noqa: BLE001 -- one subscription must not block others
                counts["errors"] += 1
                log_event(
                    logger, logging.ERROR, "alert evaluation failed for subscription",
                    subscription_id=sub_id, target_date=str(target_date), error=str(exc),
                )

    log_event(logger, logging.INFO, "alert evaluation cycle complete", **counts)
    return counts
