"""Loads data/beaches.yml into the beaches/buoys tables. Idempotent -- upserts by id, safe
to run on every startup."""
import logging
from pathlib import Path

import yaml
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_utils import log_event
from app.models import Beach, Buoy

logger = logging.getLogger("seed")

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "beaches.yml"


async def seed_beaches_and_buoys(session: AsyncSession) -> dict:
    data = yaml.safe_load(SEED_PATH.read_text(encoding="utf-8"))

    beach_count = 0
    for b in data.get("beaches", []):
        # shoreline_bearing is written by scripts/exposure/compute_bearings.py
        # (prompts/phase-2-exposure.md section 1), not computed here -- this just carries
        # whatever that script last wrote into data/beaches.yml through to the DB.
        stmt = pg_insert(Beach).values(
            id=b["id"],
            name=b["name"],
            name_he=b.get("name_he"),
            lat=b["lat"],
            lon=b["lon"],
            shoreline_bearing=b.get("shoreline_bearing"),
            coordinate_source="data/beaches.yml, approximate public map lookup, unsurveyed",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": stmt.excluded.name,
                "name_he": stmt.excluded.name_he,
                "lat": stmt.excluded.lat,
                "lon": stmt.excluded.lon,
                "shoreline_bearing": stmt.excluded.shoreline_bearing,
            },
        )
        await session.execute(stmt)
        beach_count += 1

    buoy_count = 0
    for buoy in data.get("buoys", []):
        stmt = pg_insert(Buoy).values(
            id=buoy["id"],
            name=buoy["name"],
            lat=buoy["lat"],
            lon=buoy["lon"],
            source=buoy["source"],
            active=buoy.get("active", False),
            licence_note=buoy.get("licence_note"),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": stmt.excluded.name,
                "lat": stmt.excluded.lat,
                "lon": stmt.excluded.lon,
                "source": stmt.excluded.source,
                "active": stmt.excluded.active,
                "licence_note": stmt.excluded.licence_note,
            },
        )
        await session.execute(stmt)
        buoy_count += 1

    await session.commit()
    log_event(logger, logging.INFO, "seed complete", beaches=beach_count, buoys=buoy_count)

    for buoy in data.get("buoys", []):
        if buoy.get("licence_note") and "written permission" in buoy["licence_note"]:
            log_event(
                logger,
                logging.WARNING,
                "buoy data has unresolved licence restriction -- do not redistribute",
                buoy_id=buoy["id"],
            )

    return {"beaches": beach_count, "buoys": buoy_count}
