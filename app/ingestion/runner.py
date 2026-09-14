"""Orchestrates one ingestion cycle: forecasts (wave+wind merged) for every beach, plus the
Hadera buoy. Records one IngestionRun row per source, aggregated across beaches, so
/health and gap detection can query "did the 04:00 run actually happen" instead of
grepping logs (prompts/phase-1-ingestion.md section 2/3).

Graceful degradation (hard rule 7): a failure in one beach, or in the buoy, is caught here
and recorded -- it never propagates out of run_ingestion, and it never blocks the other
sources. run_ingestion always returns a summary; it does not raise.
"""
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.errors import UpstreamError
from app.ingestion.backfill import backfill_beach
from app.ingestion.buoys import ingest_hadera
from app.ingestion.forecasts import ingest_forecasts_for_beach
from app.logging_utils import log_event
from app.models import Beach, Buoy, IngestionRun
from app.settings import get_settings

logger = logging.getLogger("ingestion.runner")


async def _record_run(
    session: AsyncSession,
    *,
    source: str,
    started_at: datetime,
    status: str,
    rows_written: int,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    error: str | None = None,
) -> None:
    session.add(
        IngestionRun(
            source=source,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            status=status,
            rows_written=rows_written,
            window_start=window_start,
            window_end=window_end,
            error=error,
        )
    )
    await session.commit()


async def run_forecast_ingestion(
    session: AsyncSession, client: httpx.AsyncClient, *, issued_at: datetime | None = None
) -> dict:
    settings = get_settings()
    issued_at = issued_at or datetime.now(UTC)
    started_at = datetime.now(UTC)

    beaches = (await session.execute(select(Beach))).scalars().all()

    wave_ok = wave_fail = wind_ok = wind_fail = 0
    total_rows = 0
    errors: list[str] = []

    for beach in beaches:
        try:
            result = await ingest_forecasts_for_beach(
                session,
                client,
                beach,
                issued_at=issued_at,
                forecast_days=max(1, settings.forecast_hours_ahead // 24 + 1),
            )
            total_rows += result["rows_written"]
            if result["wave_failed"]:
                wave_fail += 1
            else:
                wave_ok += 1
            if result["wind_failed"]:
                wind_fail += 1
            else:
                wind_ok += 1
        except UpstreamError as exc:
            # Both wave and wind failed for this beach -- log and move to the next beach.
            wave_fail += 1
            wind_fail += 1
            errors.append(f"{beach.id}: {exc}")
            log_event(
                logger,
                logging.ERROR,
                "forecast ingestion failed for beach",
                beach_id=beach.id,
                error=str(exc),
            )

    await session.commit()

    def _status(ok: int, fail: int) -> str:
        if fail == 0:
            return "success"
        if ok == 0:
            return "failed"
        return "partial"

    await _record_run(
        session,
        source="wave",
        started_at=started_at,
        status=_status(wave_ok, wave_fail),
        rows_written=total_rows,
        error="; ".join(errors) or None,
    )
    await _record_run(
        session,
        source="wind",
        started_at=started_at,
        status=_status(wind_ok, wind_fail),
        rows_written=total_rows,
        error="; ".join(errors) or None,
    )

    summary = {
        "beaches": len(beaches),
        "rows_written": total_rows,
        "wave_ok": wave_ok,
        "wave_fail": wave_fail,
        "wind_ok": wind_ok,
        "wind_fail": wind_fail,
    }
    log_event(logger, logging.INFO, "forecast ingestion run complete", **summary)
    return summary


async def run_buoy_ingestion(session: AsyncSession, client: httpx.AsyncClient) -> dict:
    started_at = datetime.now(UTC)
    buoys = (
        (await session.execute(select(Buoy).where(Buoy.active.is_(True)))).scalars().all()
    )

    total_rows = 0
    failures: list[str] = []
    for buoy in buoys:
        try:
            result = await ingest_hadera(session, client, buoy, fetched_at=started_at)
            total_rows += result["rows_written"]
            await session.commit()
            await _record_run(
                session,
                source=f"buoy:{buoy.id}",
                started_at=started_at,
                status="success",
                rows_written=result["rows_written"],
            )
        except UpstreamError as exc:
            failures.append(f"{buoy.id}: {exc}")
            log_event(
                logger, logging.ERROR, "buoy ingestion failed", buoy_id=buoy.id, error=str(exc)
            )
            await _record_run(
                session,
                source=f"buoy:{buoy.id}",
                started_at=started_at,
                status="failed",
                rows_written=0,
                error=str(exc),
            )

    summary = {"buoys": len(buoys), "rows_written": total_rows, "failures": failures}
    log_event(logger, logging.INFO, "buoy ingestion run complete", **summary)
    return summary


async def run_backfill(
    session: AsyncSession, client: httpx.AsyncClient, *, issued_at: datetime | None = None
) -> dict:
    issued_at = issued_at or datetime.now(UTC)
    started_at = datetime.now(UTC)
    beaches = (await session.execute(select(Beach))).scalars().all()

    total_rows = 0
    all_gap_days: dict[str, list[str]] = {}
    errors: list[str] = []
    for beach in beaches:
        try:
            result = await backfill_beach(session, client, beach, issued_at=issued_at)
            total_rows += result["rows_written"]
            if result["gap_days"]:
                all_gap_days[beach.id] = result["gap_days"]
        except UpstreamError as exc:
            errors.append(f"{beach.id}: {exc}")
            log_event(
                logger, logging.ERROR, "backfill failed for beach", beach_id=beach.id, error=str(exc)
            )

    await session.commit()
    await _record_run(
        session,
        source="wave-backfill",
        started_at=started_at,
        status="failed" if errors and total_rows == 0 else ("partial" if errors else "success"),
        rows_written=total_rows,
        error="; ".join(errors) or None,
    )

    summary = {"rows_written": total_rows, "gap_days_by_beach": all_gap_days, "errors": errors}
    log_event(logger, logging.INFO, "backfill run complete", **summary)
    return summary


async def run_full_ingestion_cycle(session: AsyncSession, client: httpx.AsyncClient) -> dict:
    """The scheduled entry point: backfill first (catch up on missed runs), then the
    current live fetch, then the buoy."""
    backfill_summary = await run_backfill(session, client)
    forecast_summary = await run_forecast_ingestion(session, client)
    buoy_summary = await run_buoy_ingestion(session, client)
    return {
        "backfill": backfill_summary,
        "forecast": forecast_summary,
        "buoy": buoy_summary,
    }
