"""Evaluates SlotWatch rows and sends the alert/cancellation -- see app/models.py::SlotWatch
for the full state-machine rationale. Distinct from app/alerting/runner.py's recurring
Subscription evaluation: a watch is a one-off "tell me about THIS slot", re-checked as
forecasts refresh, not a standing criteria rule re-evaluated over a rolling date range.

State machine, per tick:
  pending,   before watch_from        -> untouched (dormant, too far out to trust the data)
  pending,   watch_from <= now < slot -> re-score; quality_score >= QUALIFY_SCORE -> alerted
  alerted,   watch_from <= now < slot -> re-score; fallen below QUALIFY_SCORE -> cancelled
  pending,   slot has passed          -> expired, no message (never qualified)
  alerted,   slot has passed          -> untouched (already said everything there is to say)

Idempotency: the same row-lock discipline as app/alerting/runner.py -- SELECT ... FOR
UPDATE SKIP LOCKED, mark the new status and commit BEFORE attempting delivery, so a crash
between commit and delivery loses at most one push, never sends a duplicate.
"""
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerting.runner import deliver_to_user
from app.alerting.timewindow import local_hour_label
from app.logging_utils import log_event
from app.models import Beach, SlotWatch
from app.quality.apply import build_quality
from app.queries import get_latest_forecasts

logger = logging.getLogger("alerting.slot_watch")

# How long before the watched slot the watch wakes up and starts checking. Forecasts move
# too fast on this coast to trust much earlier -- see docs/DECISIONS.md; a judgement call,
# not measured.
WATCH_LEAD_HOURS = 12

# The quality_score (0..10, app/quality/verdict.py) a slot must reach to fire the alert.
QUALIFY_SCORE = 5.0


def _snapshot(quality) -> dict:
    return {
        "quality_score": quality.quality_score,
        "quality_verdict": quality.quality_verdict,
        "surf_height_estimate": quality.size.surf_height_estimate,
        "wind_speed_kmh": quality.wind.speed_kmh,
        "wind_relation_to_shore": quality.wind.relation_to_shore,
    }


def _build_payload(beach: Beach, watch: SlotWatch, quality, *, kind: str) -> dict:
    slot_label = local_hour_label(watch.valid_at)
    title = {
        "alert": f"{beach.name}: {slot_label} looks on",
        "cancellation": f"{beach.name}: {slot_label} dropped off",
    }[kind]
    return {
        "title": title,
        "beach_id": beach.id,
        "beach_name": beach.name,
        "kind": kind,
        "valid_at": watch.valid_at.isoformat(),
        "quality_score": quality.quality_score,
        "quality_verdict": quality.quality_verdict,
        "quality_reasoning": quality.quality_reasoning,
        "size": {
            "surf_height_estimate": quality.size.surf_height_estimate,
            "surf_height_range": list(quality.size.surf_height_range) if quality.size.surf_height_range else None,
            "confidence": quality.size.confidence.surf_height,
        },
        "wind": quality.wind.model_dump(),
        "swell_direction_deg": quality.swell_direction_deg,
        "qualify_score": QUALIFY_SCORE,
        "honesty_marker": "beach-level size and quality verdict are unvalidated heuristics -- see confidence fields",
    }


async def _quality_for_slot(session: AsyncSession, beach: Beach, valid_at: datetime):
    forecasts = await get_latest_forecasts(session, beach.id, valid_at, valid_at)
    if not forecasts:
        return None
    return build_quality(beach, forecasts[0])


async def _evaluate_one(session: AsyncSession, watch: SlotWatch, *, now_utc: datetime) -> str:
    """Returns the action taken: 'alerted' | 'cancelled' | 'expired' | 'none'."""
    if watch.valid_at <= now_utc:
        if watch.status == "pending":
            watch.status = "expired"
            await session.commit()
            return "expired"
        return "none"  # already alerted/cancelled -- nothing left to say once the slot passes

    if watch.status not in ("pending", "alerted"):
        return "none"

    beach = await session.get(Beach, watch.beach_id)
    quality = await _quality_for_slot(session, beach, watch.valid_at)
    if quality is None:
        return "none"  # no forecast row for this slot yet -- try again next tick

    if watch.status == "pending":
        if quality.quality_score < QUALIFY_SCORE:
            return "none"
        watch.status = "alerted"
        watch.alerted_at = now_utc
        watch.conditions_snapshot = _snapshot(quality)
        await session.commit()
        await deliver_to_user(session, watch.user_id, _build_payload(beach, watch, quality, kind="alert"))
        return "alerted"

    # status == "alerted": watch for it falling back below the bar.
    if quality.quality_score >= QUALIFY_SCORE:
        return "none"
    watch.status = "cancelled"
    watch.conditions_snapshot = _snapshot(quality)
    await session.commit()
    await deliver_to_user(session, watch.user_id, _build_payload(beach, watch, quality, kind="cancellation"))
    return "cancelled"


async def run_due_slot_watches(session: AsyncSession, *, now_utc: datetime | None = None) -> dict:
    """Evaluates every watch whose window is currently open (watch_from <= now, or already
    alerted and still before the slot). Never raises -- one watch's failure is logged and
    does not block the others (hard rule 7), same discipline as run_alert_evaluation."""
    now_utc = now_utc or datetime.now(UTC)

    # A row is "due" once its watch_from has passed, whether it is still pending or already
    # alerted (cancellation-watching needs the same window). Rows outside that window --
    # too far in the future, or already resolved (cancelled/expired) -- are left alone.
    # skip_locked mirrors app/alerting/runner.py's approach to a row lock, but here it lets
    # concurrent dispatcher ticks skip past a row another tick already holds rather than
    # blocking on it -- a slow push send must not stall the rest of the batch.
    stmt = (
        select(SlotWatch)
        .where(
            SlotWatch.status.in_(("pending", "alerted")),
            SlotWatch.watch_from <= now_utc,
        )
        .with_for_update(skip_locked=True)
    )
    watches = (await session.execute(stmt)).scalars().all()

    counts = {"alerted": 0, "cancelled": 0, "expired": 0, "none": 0, "errors": 0}
    for watch in watches:
        try:
            action = await _evaluate_one(session, watch, now_utc=now_utc)
            counts[action] += 1
        except Exception as exc:  # noqa: BLE001 -- one watch must not block the others
            counts["errors"] += 1
            log_event(
                logger, logging.ERROR, "slot watch evaluation failed",
                slot_watch_id=watch.id, error=str(exc),
            )

    log_event(logger, logging.INFO, "slot watch dispatch cycle complete", **counts)
    return counts


def watch_from_for(valid_at: datetime) -> datetime:
    """The watch_from to store for a new SlotWatch on this slot -- exposed so the API route
    computes it the same way the dispatcher reasons about it, rather than duplicating the
    WATCH_LEAD_HOURS arithmetic."""
    return valid_at - timedelta(hours=WATCH_LEAD_HOURS)
