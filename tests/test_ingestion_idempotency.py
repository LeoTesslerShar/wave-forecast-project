"""Re-running ingestion over the same window (same issued_at) writes zero new rows and
mutates nothing -- prompts/phase-1-ingestion.md section 5."""
from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy import func, select

from app.ingestion.forecasts import ingest_forecasts_for_beach
from app.models import Beach, Forecast
from app.settings import get_settings

pytestmark = pytest.mark.asyncio


async def _make_beach(db_session) -> Beach:
    beach = Beach(id="test_beach", name="Test Beach", lat=32.1, lon=34.8)
    db_session.add(beach)
    await db_session.commit()
    return beach


@respx.mock
async def test_idempotent_reingest_same_window(db_session, marine_fixture, wind_fixture):
    settings = get_settings()
    beach = await _make_beach(db_session)
    issued_at = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)

    respx.get(settings.open_meteo_marine_base_url).mock(
        return_value=httpx.Response(200, json=marine_fixture)
    )
    respx.get(settings.open_meteo_forecast_base_url).mock(
        return_value=httpx.Response(200, json=wind_fixture)
    )

    async with httpx.AsyncClient() as client:
        first = await ingest_forecasts_for_beach(
            db_session, client, beach, issued_at=issued_at, forecast_days=2
        )
        await db_session.commit()
        count_after_first = (
            await db_session.execute(select(func.count()).select_from(Forecast))
        ).scalar_one()

        second = await ingest_forecasts_for_beach(
            db_session, client, beach, issued_at=issued_at, forecast_days=2
        )
        await db_session.commit()
        count_after_second = (
            await db_session.execute(select(func.count()).select_from(Forecast))
        ).scalar_one()

    assert first["rows_written"] == second["rows_written"]
    assert count_after_first == count_after_second
    assert count_after_first > 0

    rows = (await db_session.execute(select(Forecast))).scalars().all()
    for row in rows:
        assert row.wave_height is not None
        assert row.wind_speed_10m is not None
        assert row.issued_at == issued_at
