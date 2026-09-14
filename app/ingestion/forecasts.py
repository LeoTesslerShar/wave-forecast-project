"""Fetches wave (marine-api) + wind (forecast-api) for one beach and merges them into one
Forecast row per valid_at, keyed on (beach_id, issued_at, valid_at).

Idempotency (prompts/phase-1-ingestion.md section 3): `issued_at` is passed in by the
caller (the ingestion run's start time), not read from the clock per-row, so re-running the
same logical run with the same issued_at upserts onto the same natural key and writes zero
NEW rows -- tested directly in tests/test_ingestion_idempotency.py.

Wave and wind failures are handled independently: one upstream being down does not block
the other, and a partial row (one side present, other NULL + flagged) is written rather
than no row at all (section 3, "Requirements"). Only if BOTH fail does this raise, so the
caller can record the whole beach's forecast ingestion as failed for this run.
"""
import logging
from datetime import date, datetime

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import open_meteo_forecast, open_meteo_marine
from app.clients.errors import UpstreamError
from app.logging_utils import log_event
from app.models import Beach, Forecast

logger = logging.getLogger("ingestion.forecasts")

WAVE_SOURCE_MODEL = "open-meteo-marine-best_match"


async def ingest_forecasts_for_beach(
    session: AsyncSession,
    client: httpx.AsyncClient,
    beach: Beach,
    *,
    issued_at: datetime,
    forecast_days: int,
    backfilled: bool = False,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    wave_rows: list[dict] = []
    wave_failed = False
    try:
        if backfilled:
            payload = await open_meteo_marine.fetch_marine_range(
                client, beach.lat, beach.lon, start_date, end_date
            )
        else:
            payload = await open_meteo_marine.fetch_marine_live(
                client, beach.lat, beach.lon, forecast_days
            )
        wave_rows = open_meteo_marine.parse_hourly(payload)
    except (UpstreamError, httpx.HTTPError) as exc:
        wave_failed = True
        log_event(
            logger, logging.WARNING, "wave fetch failed", beach_id=beach.id, error=str(exc)
        )

    wind_rows: list[dict] = []
    wind_failed = False
    try:
        if backfilled:
            payload = await open_meteo_forecast.fetch_wind_range(
                client, beach.lat, beach.lon, start_date, end_date
            )
        else:
            payload = await open_meteo_forecast.fetch_wind_live(
                client, beach.lat, beach.lon, forecast_days
            )
        wind_rows = open_meteo_forecast.parse_hourly(payload)
    except (UpstreamError, httpx.HTTPError) as exc:
        wind_failed = True
        log_event(
            logger, logging.WARNING, "wind fetch failed", beach_id=beach.id, error=str(exc)
        )

    if wave_failed and wind_failed:
        raise UpstreamError(f"both wave and wind upstreams failed for beach {beach.id}")

    merged = _merge(wave_rows, wind_rows)

    rows_written = 0
    for row in merged:
        stmt = pg_insert(Forecast).values(
            beach_id=beach.id,
            issued_at=issued_at,
            valid_at=row["valid_at"],
            wave_height=row.get("wave_height"),
            wave_direction=row.get("wave_direction"),
            wave_period=row.get("wave_period"),
            swell_wave_height=row.get("swell_wave_height"),
            swell_wave_direction=row.get("swell_wave_direction"),
            swell_wave_period=row.get("swell_wave_period"),
            wind_wave_height=row.get("wind_wave_height"),
            wind_wave_direction=row.get("wind_wave_direction"),
            wind_wave_period=row.get("wind_wave_period"),
            wave_source_model=None if wave_failed else WAVE_SOURCE_MODEL,
            wind_speed_10m=row.get("wind_speed_10m"),
            wind_direction_10m=row.get("wind_direction_10m"),
            wind_gusts_10m=row.get("wind_gusts_10m"),
            fetched_at=issued_at,
            backfilled=backfilled,
            wave_fetch_failed=wave_failed,
            wind_fetch_failed=wind_failed,
        )
        update_cols = {
            c.name: c
            for c in stmt.excluded
            if c.name not in ("id", "beach_id", "issued_at", "valid_at")
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_forecast_natural_key",
            set_=update_cols,
        )
        await session.execute(stmt)
        rows_written += 1

    return {
        "beach_id": beach.id,
        "rows_written": rows_written,
        "wave_failed": wave_failed,
        "wind_failed": wind_failed,
    }


def _merge(wave_rows: list[dict], wind_rows: list[dict]) -> list[dict]:
    by_time: dict[datetime, dict] = {}
    for r in wave_rows:
        by_time.setdefault(r["valid_at"], {}).update(r)
    for r in wind_rows:
        by_time.setdefault(r["valid_at"], {}).update(r)
    return [{"valid_at": t, **v} for t, v in sorted(by_time.items())]
