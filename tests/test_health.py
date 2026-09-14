"""/health reports degraded, not down, when a source is stale or failed -- hard rule 7,
prompts/phase-1-ingestion.md section 4."""
from datetime import UTC, datetime, timedelta

import pytest

from app.api.health import health
from app.models import IngestionRun

pytestmark = pytest.mark.asyncio


async def test_no_runs_yet_is_degraded_not_crashed(db_session):
    result = await health(db_session)
    assert result.database is True
    assert result.status == "degraded"
    assert result.sources == []


async def test_all_sources_healthy_is_ok(db_session):
    now = datetime.now(UTC)
    for source in ["wave", "wind", "buoy:hadera_isramar"]:
        db_session.add(
            IngestionRun(
                source=source,
                started_at=now - timedelta(minutes=5),
                finished_at=now,
                status="success",
                rows_written=10,
            )
        )
    await db_session.commit()

    result = await health(db_session)
    assert result.status == "ok"
    assert all(s.status == "ok" for s in result.sources)


async def test_one_source_failed_degrades_overall_but_not_down(db_session):
    now = datetime.now(UTC)
    db_session.add(
        IngestionRun(
            source="wave", started_at=now, finished_at=now, status="success", rows_written=10
        )
    )
    db_session.add(
        IngestionRun(
            source="buoy:hadera_isramar",
            started_at=now,
            finished_at=now,
            status="failed",
            rows_written=0,
            error="503",
        )
    )
    await db_session.commit()

    result = await health(db_session)
    assert result.status == "degraded"  # NOT "down" -- a dead buoy must not take the app down
    statuses = {s.source: s.status for s in result.sources}
    assert statuses["wave"] == "ok"
    assert statuses["buoy:hadera_isramar"] == "down"  # failed with no prior success


async def test_stale_source_reported_as_stale(db_session):
    now = datetime.now(UTC)
    db_session.add(
        IngestionRun(
            source="wave",
            started_at=now - timedelta(hours=100),
            finished_at=now - timedelta(hours=100),
            status="success",
            rows_written=10,
        )
    )
    await db_session.commit()

    result = await health(db_session)
    assert result.status == "degraded"
    assert result.sources[0].status == "stale"
