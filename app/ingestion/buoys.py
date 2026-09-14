"""Hadera buoy ingestion. One reading per call, no history parameter -- a missed fetch is
a permanent gap (docs/DATA_SOURCES.md, prompts/phase-1-ingestion.md section 3)."""
import logging
from datetime import datetime

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import isramar
from app.logging_utils import log_event
from app.models import Buoy, Measurement

logger = logging.getLogger("ingestion.buoys")


async def ingest_hadera(
    session: AsyncSession,
    client: httpx.AsyncClient,
    buoy: Buoy,
    *,
    fetched_at: datetime,
) -> dict:
    payload = await isramar.fetch_hadera(client)  # raises UpstreamError after retries
    reading = isramar.parse_reading(payload)
    if reading is None:
        log_event(
            logger,
            logging.WARNING,
            "hadera payload had no parseable reading",
            buoy_id=buoy.id,
        )
        return {"buoy_id": buoy.id, "rows_written": 0}

    stmt = pg_insert(Measurement).values(
        buoy_id=buoy.id,
        observed_at=reading["observed_at"],
        wave_height=reading["wave_height"],
        wave_period=reading["wave_period"],
        wave_max=reading["wave_max"],
        fetched_at=fetched_at,
    )
    update_cols = {
        c.name: c
        for c in stmt.excluded
        if c.name not in ("id", "buoy_id", "observed_at")
    }
    stmt = stmt.on_conflict_do_update(
        constraint="uq_measurement_natural_key",
        set_=update_cols,
    )
    await session.execute(stmt)
    return {"buoy_id": buoy.id, "rows_written": 1}
