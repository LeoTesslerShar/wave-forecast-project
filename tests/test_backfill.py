"""Gap detection + backfill for missed scheduled runs -- prompts/phase-1-ingestion.md
section 5. Backfilled rows are flagged; a second backfill run over the same gap adds
nothing (idempotent, same as live ingestion).

Uses a dynamically-built payload (not the static fixtures) because the gap window is
relative to "today" at test-run time -- a static fixture's dates would not line up with
whatever "today" happens to be."""
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import func, select

from app.ingestion.backfill import backfill_beach, find_gap_days
from app.models import Beach, Forecast
from app.settings import get_settings

pytestmark = pytest.mark.asyncio


def _marine_payload_for_range(start, end) -> dict:
    hours = int((end - start).total_seconds() // 3600) + 1
    times = [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(hours)]
    n = len(times)
    return {
        "latitude": 32.1,
        "longitude": 34.8,
        "hourly": {
            "time": times,
            "wave_height": [1.0] * n,
            "wave_direction": [280] * n,
            "wave_period": [7.0] * n,
            "swell_wave_height": [0.9] * n,
            "swell_wave_direction": [280] * n,
            "swell_wave_period": [8.0] * n,
            "wind_wave_height": [0.3] * n,
            "wind_wave_direction": [270] * n,
            "wind_wave_period": [3.0] * n,
        },
    }


def _wind_payload_for_range(start, end) -> dict:
    hours = int((end - start).total_seconds() // 3600) + 1
    times = [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(hours)]
    n = len(times)
    return {
        "latitude": 32.1,
        "longitude": 34.8,
        "hourly": {
            "time": times,
            "wind_speed_10m": [10.0] * n,
            "wind_direction_10m": [300] * n,
            "wind_gusts_10m": [15.0] * n,
        },
    }


@respx.mock
async def test_gap_detected_and_backfilled(db_session):
    settings = get_settings()
    beach = Beach(id="test_beach", name="Test Beach", lat=32.1, lon=34.8)
    db_session.add(beach)
    await db_session.commit()

    # A day with zero rows should be detected as a gap.
    gaps = await find_gap_days(db_session, beach.id, max_days=settings.backfill_max_days)
    assert len(gaps) == settings.backfill_max_days  # entirely empty -> every day is a gap

    window_start = datetime.combine(min(gaps), datetime.min.time(), tzinfo=UTC)
    window_end = datetime.combine(max(gaps), datetime.min.time(), tzinfo=UTC) + timedelta(
        hours=23
    )

    respx.get(settings.open_meteo_marine_base_url).mock(
        return_value=httpx.Response(200, json=_marine_payload_for_range(window_start, window_end))
    )
    respx.get(settings.open_meteo_forecast_base_url).mock(
        return_value=httpx.Response(200, json=_wind_payload_for_range(window_start, window_end))
    )

    async with httpx.AsyncClient() as client:
        result = await backfill_beach(
            db_session, client, beach, issued_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
        )
        await db_session.commit()

    assert result["rows_written"] > 0
    assert len(result["gap_days"]) == settings.backfill_max_days

    rows = (await db_session.execute(select(Forecast))).scalars().all()
    assert all(r.backfilled for r in rows)
    count_after_first = len(rows)

    # A second backfill run: the gap is now filled with backfilled rows for the same days,
    # so find_gap_days should report those days as covered -- and the row count must not
    # grow just from running backfill twice.
    async with httpx.AsyncClient() as client:
        result2 = await backfill_beach(
            db_session, client, beach, issued_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
        )
        await db_session.commit()

    assert result2["gap_days"] == []  # no longer a gap -- the earlier backfill covered it
    count_after_second = (
        await db_session.execute(select(func.count()).select_from(Forecast))
    ).scalar_one()
    assert count_after_second == count_after_first
