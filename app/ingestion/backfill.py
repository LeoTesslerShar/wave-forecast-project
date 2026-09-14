"""Gap detection and backfill for MISSED SCHEDULED RUNS, not deep history
(prompts/phase-1-ingestion.md section 3). A day with zero forecast rows for a beach, inside
the recent `backfill_max_days` window, means a scheduled run was missed (app down, upstream
down for the whole window, etc.) -- refetching it now gets "what the forecast says now for
that past hour," not what was actually forecast at the time, so every row written this way
is flagged backfilled=True (see Forecast.backfilled and docs/DECISIONS.md).

The Hadera buoy has no history endpoint at all -- there is nothing to backfill it from; a
missed buoy fetch is a permanent gap, surfaced only via ingestion_runs / /health.
"""
import logging
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.forecasts import ingest_forecasts_for_beach
from app.logging_utils import log_event
from app.models import Beach, Forecast
from app.settings import get_settings

logger = logging.getLogger("ingestion.backfill")


async def find_gap_days(session: AsyncSession, beach_id: str, *, max_days: int) -> list[date]:
    """Days in the last `max_days`, up to and including yesterday, with zero forecast rows
    for this beach. Today is excluded -- a normal scheduled run may simply not have fired
    yet today, which is not a gap."""
    today = datetime.now(UTC).date()
    window_start = today - timedelta(days=max_days)

    result = await session.execute(
        select(Forecast.valid_at).where(
            Forecast.beach_id == beach_id,
            Forecast.valid_at >= datetime.combine(window_start, datetime.min.time(), tzinfo=UTC),
            Forecast.valid_at < datetime.combine(today, datetime.min.time(), tzinfo=UTC),
        )
    )
    covered_days = {row[0].date() for row in result.all()}

    gap_days = []
    d = window_start
    while d < today:
        if d not in covered_days:
            gap_days.append(d)
        d += timedelta(days=1)
    return gap_days


async def backfill_beach(
    session: AsyncSession,
    client: httpx.AsyncClient,
    beach: Beach,
    *,
    issued_at: datetime,
) -> dict:
    settings = get_settings()
    gap_days = await find_gap_days(session, beach.id, max_days=settings.backfill_max_days)
    if not gap_days:
        return {"beach_id": beach.id, "gap_days": [], "rows_written": 0}

    log_event(
        logger,
        logging.INFO,
        "backfilling gap",
        beach_id=beach.id,
        gap_days=[d.isoformat() for d in gap_days],
    )
    result = await ingest_forecasts_for_beach(
        session,
        client,
        beach,
        issued_at=issued_at,
        forecast_days=0,
        backfilled=True,
        start_date=min(gap_days),
        end_date=max(gap_days),
    )
    result["gap_days"] = [d.isoformat() for d in gap_days]
    return result
