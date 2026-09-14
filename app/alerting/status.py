"""A checkable status for one subscription -- prompts/phase-4-alerting.md section 7.
`docs/BIAS_ANALYSIS.md` found only 26% of hours reach 1m annually and September sees it
1.3% of the time; an extended flat spell produces zero AlertSent rows by design (nothing
qualified, nothing to say), which must not look identical to "the system stopped
evaluating this subscription." This distinguishes the two.
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertSent, IngestionRun, Subscription

STATUS_LOOKBACK_DAYS = 14


@dataclass
class SubscriptionStatus:
    subscription_id: int
    active: bool
    system_healthy: bool
    last_alert_kind: str | None
    last_alert_at: datetime | None
    last_alert_target_date: str | None
    currently_alerted: bool
    message: str


async def get_subscription_status(session: AsyncSession, subscription_id: int) -> SubscriptionStatus | None:
    sub = await session.get(Subscription, subscription_id)
    if sub is None:
        return None

    cutoff = datetime.now(UTC) - timedelta(days=STATUS_LOOKBACK_DAYS)
    last_alert = (
        await session.execute(
            select(AlertSent)
            .where(AlertSent.subscription_id == subscription_id)
            .order_by(AlertSent.sent_at.desc())
            .limit(1)
        )
    ).scalars().first()

    # System-alive check: has ANY ingestion succeeded recently? Distinguishes "nothing
    # qualified" from "the whole pipeline is down and nothing has been evaluated".
    recent_success = (
        await session.execute(
            select(IngestionRun)
            .where(IngestionRun.status.in_(["success", "partial"]), IngestionRun.finished_at >= cutoff)
            .limit(1)
        )
    ).scalars().first()
    system_healthy = recent_success is not None

    currently_alerted = last_alert is not None and last_alert.kind != "cancellation"

    if not sub.active:
        message = "subscription is inactive"
    elif not system_healthy:
        message = "system has not completed an ingestion run recently -- status may be stale, not necessarily flat"
    elif currently_alerted:
        message = f"currently alerted for {last_alert.target_date} ({last_alert.kind})"
    elif last_alert is not None:
        message = f"nothing qualifying since the {last_alert.target_date} window closed"
    else:
        message = f"nothing has met your criteria in the last {STATUS_LOOKBACK_DAYS} days"

    return SubscriptionStatus(
        subscription_id=subscription_id,
        active=sub.active,
        system_healthy=system_healthy,
        last_alert_kind=last_alert.kind if last_alert else None,
        last_alert_at=last_alert.sent_at if last_alert else None,
        last_alert_target_date=str(last_alert.target_date) if last_alert else None,
        currently_alerted=currently_alerted,
        message=message,
    )
