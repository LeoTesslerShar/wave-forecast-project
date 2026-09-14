"""Each upstream failing independently records its own failure, never blocks the others,
and never raises out of the scheduler -- hard rule 7, prompts/phase-1-ingestion.md section 5."""
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.clients.errors import UpstreamError
from app.ingestion.forecasts import ingest_forecasts_for_beach
from app.models import Beach
from app.settings import get_settings

pytestmark = pytest.mark.asyncio


async def _make_beach(db_session) -> Beach:
    beach = Beach(id="test_beach", name="Test Beach", lat=32.1, lon=34.8)
    db_session.add(beach)
    await db_session.commit()
    return beach


@respx.mock
async def test_wind_down_wave_up_does_not_raise(db_session, marine_fixture):
    settings = get_settings()
    beach = await _make_beach(db_session)

    respx.get(settings.open_meteo_marine_base_url).mock(
        return_value=httpx.Response(200, json=marine_fixture)
    )
    respx.get(settings.open_meteo_forecast_base_url).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        result = await ingest_forecasts_for_beach(
            db_session,
            client,
            beach,
            issued_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
            forecast_days=2,
        )

    assert result["wave_failed"] is False
    assert result["wind_failed"] is True
    assert result["rows_written"] > 0


@respx.mock
async def test_wave_down_wind_up_does_not_raise(db_session, wind_fixture):
    settings = get_settings()
    beach = await _make_beach(db_session)

    respx.get(settings.open_meteo_marine_base_url).mock(return_value=httpx.Response(500))
    respx.get(settings.open_meteo_forecast_base_url).mock(
        return_value=httpx.Response(200, json=wind_fixture)
    )

    async with httpx.AsyncClient() as client:
        result = await ingest_forecasts_for_beach(
            db_session,
            client,
            beach,
            issued_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
            forecast_days=2,
        )

    assert result["wave_failed"] is True
    assert result["wind_failed"] is False
    assert result["rows_written"] > 0


@respx.mock
async def test_both_down_raises_so_caller_can_record_failure(db_session):
    settings = get_settings()
    beach = await _make_beach(db_session)

    respx.get(settings.open_meteo_marine_base_url).mock(return_value=httpx.Response(500))
    respx.get(settings.open_meteo_forecast_base_url).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        with pytest.raises(UpstreamError):
            await ingest_forecasts_for_beach(
                db_session,
                client,
                beach,
                issued_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
                forecast_days=2,
            )
