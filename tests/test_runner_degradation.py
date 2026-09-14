"""Runner-level degradation: a dead buoy source records a failed IngestionRun row and does
not stop forecast ingestion or raise out of the scheduler job -- hard rule 7."""
from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy import select

from app.ingestion.runner import run_buoy_ingestion, run_forecast_ingestion
from app.models import Beach, Buoy, Forecast, IngestionRun
from app.settings import get_settings

pytestmark = pytest.mark.asyncio


@respx.mock
async def test_dead_buoy_records_failure_and_does_not_raise(db_session):
    settings = get_settings()
    buoy = Buoy(id="hadera_isramar", name="Hadera", lat=32.47, lon=34.88, source="isramar", active=True)
    db_session.add(buoy)
    await db_session.commit()

    respx.get(settings.isramar_hadera_url).mock(return_value=httpx.Response(503))

    async with httpx.AsyncClient() as client:
        summary = await run_buoy_ingestion(db_session, client)  # must not raise

    assert summary["rows_written"] == 0
    assert len(summary["failures"]) == 1

    runs = (
        await db_session.execute(select(IngestionRun).where(IngestionRun.source == "buoy:hadera_isramar"))
    ).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert runs[0].error


@respx.mock
async def test_dead_buoy_does_not_block_forecast_ingestion(db_session, marine_fixture, wind_fixture):
    settings = get_settings()
    beach = Beach(id="test_beach", name="Test Beach", lat=32.1, lon=34.8)
    db_session.add(beach)
    await db_session.commit()

    respx.get(settings.open_meteo_marine_base_url).mock(
        return_value=httpx.Response(200, json=marine_fixture)
    )
    respx.get(settings.open_meteo_forecast_base_url).mock(
        return_value=httpx.Response(200, json=wind_fixture)
    )
    respx.get(settings.isramar_hadera_url).mock(return_value=httpx.Response(503))

    async with httpx.AsyncClient() as client:
        forecast_summary = await run_forecast_ingestion(
            db_session, client, issued_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
        )

    assert forecast_summary["wave_ok"] == 1
    assert forecast_summary["wind_ok"] == 1
    rows = (await db_session.execute(select(Forecast))).scalars().all()
    assert len(rows) > 0
