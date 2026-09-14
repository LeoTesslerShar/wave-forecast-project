"""GET /health -- DB, Redis, and per-source last-successful-ingestion age. Degraded, not
down, when a source is stale (hard rule 7, prompts/phase-1-ingestion.md section 4)."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache
from app.db import get_session
from app.models import IngestionRun
from app.schemas import HealthOut, HealthSource
from app.settings import get_settings

router = APIRouter()

# A source is stale if its last SUCCESSFUL run is older than this many scheduler
# intervals -- generous enough to absorb one missed run without flapping to "down".
STALE_INTERVAL_MULTIPLIER = 3


@router.get("/health", response_model=HealthOut)
async def health(session: AsyncSession = Depends(get_session)) -> HealthOut:
    settings = get_settings()
    db_ok = True
    sources: list[HealthSource] = []
    try:
        # Latest row per source, regardless of status -- we want to know about failures too.
        subq = (
            select(
                IngestionRun.source,
                func.max(IngestionRun.started_at).label("latest_started_at"),
            )
            .group_by(IngestionRun.source)
            .subquery()
        )
        stmt = select(IngestionRun).join(
            subq,
            (IngestionRun.source == subq.c.source)
            & (IngestionRun.started_at == subq.c.latest_started_at),
        )
        rows = (await session.execute(stmt)).scalars().all()

        # Latest SUCCESSFUL run per source, for the staleness clock.
        success_subq = (
            select(
                IngestionRun.source,
                func.max(IngestionRun.finished_at).label("last_success_at"),
            )
            .where(IngestionRun.status.in_(["success", "partial"]))
            .group_by(IngestionRun.source)
            .subquery()
        )
        success_rows = {
            r.source: r.last_success_at
            for r in (
                await session.execute(
                    select(success_subq.c.source, success_subq.c.last_success_at)
                )
            ).all()
        }

        now = datetime.now(UTC)
        stale_after = settings.ingestion_schedule_minutes * 60 * STALE_INTERVAL_MULTIPLIER

        for row in rows:
            last_success = success_rows.get(row.source)
            age = (now - last_success).total_seconds() if last_success else None
            if row.status == "failed" and last_success is None:
                status = "down"
            elif age is not None and age > stale_after:
                status = "stale"
            elif row.status == "partial":
                status = "degraded"
            elif row.status == "failed":
                status = "degraded"  # failed this run, but has succeeded before
            else:
                status = "ok"
            sources.append(
                HealthSource(
                    source=row.source, status=status, last_success_at=last_success, age_seconds=age
                )
            )
    except Exception:  # noqa: BLE001 -- DB itself unreachable
        db_ok = False

    redis_ok = await cache.ping()

    if not db_ok:
        overall = "down"
    elif not sources or any(s.status in ("down", "stale", "degraded") for s in sources):
        overall = "degraded"
    else:
        overall = "ok"

    return HealthOut(status=overall, database=db_ok, redis=redis_ok, sources=sources)
