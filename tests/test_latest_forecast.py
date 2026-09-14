"""The latest-forecast access path (app/queries.py) returns exactly the newest issued_at
row per valid_at -- prompts/phase-1-ingestion.md section 5."""
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Beach, Forecast
from app.queries import get_latest_forecasts

pytestmark = pytest.mark.asyncio


async def test_latest_forecast_returns_newest_issued_at(db_session):
    beach = Beach(id="test_beach", name="Test Beach", lat=32.1, lon=34.8)
    db_session.add(beach)
    await db_session.commit()

    valid_at = datetime(2026, 9, 20, 6, 0, tzinfo=UTC)
    base = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)

    # Three successive forecast runs for the same target hour, each issued a day later
    # and revising the estimate upward -- the newest issued_at (day 3, 1.5m) must win.
    for days_since_base, height in [(0, 1.0), (1, 1.2), (2, 1.5)]:
        db_session.add(
            Forecast(
                beach_id=beach.id,
                issued_at=base + timedelta(days=days_since_base),
                valid_at=valid_at,
                wave_height=height,
                fetched_at=base + timedelta(days=days_since_base),
            )
        )
    await db_session.commit()

    rows = await get_latest_forecasts(
        db_session, beach.id, valid_at - timedelta(hours=1), valid_at + timedelta(hours=1)
    )

    assert len(rows) == 1
    assert rows[0].wave_height == 1.5
    assert rows[0].issued_at == base + timedelta(days=2)


async def test_latest_forecast_one_row_per_valid_at(db_session):
    """Multiple valid_at hours, each with multiple issued_at versions -- one row per hour
    out, always the newest issued_at for that hour."""
    beach = Beach(id="test_beach", name="Test Beach", lat=32.1, lon=34.8)
    db_session.add(beach)
    await db_session.commit()

    base = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)
    for hour_offset in range(3):
        valid_at = base + timedelta(hours=hour_offset)
        for issued_offset, height in [(0, 1.0), (1, 1.1)]:
            db_session.add(
                Forecast(
                    beach_id=beach.id,
                    issued_at=base + timedelta(hours=issued_offset),
                    valid_at=valid_at,
                    wave_height=height,
                    fetched_at=base,
                )
            )
    await db_session.commit()

    rows = await get_latest_forecasts(
        db_session, beach.id, base - timedelta(hours=1), base + timedelta(hours=3)
    )

    assert len(rows) == 3
    assert all(r.wave_height == 1.1 for r in rows)
