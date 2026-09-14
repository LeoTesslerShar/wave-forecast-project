"""Idempotent delivery under concurrency -- prompts/phase-4-alerting.md acceptance check 3.
Two evaluations of the SAME subscription+date, run concurrently against a real Postgres
(not mocked), must produce exactly one send. This tests the actual row lock in
app/alerting/runner.py (`SELECT ... FOR UPDATE`), not a simulation of one.
"""
import asyncio
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerting.runner import evaluate_subscription_for_date
from app.alerting.timewindow import window_utc_for_date
from app.models import AlertSent, Beach, Forecast, Subscription
from tests.conftest import _test_db_url_and_name

TARGET_DATE = date(2026, 1, 20)


async def _seed(db_session) -> int:
    beach = Beach(id="herzliya", name="Herzliya", lat=32.1660, lon=34.7960, shoreline_bearing=301.1)
    db_session.add(beach)
    sub = Subscription(
        user_id="u1", beach_id="herzliya", min_height=1.0, max_height=None,
        swell_dir_min=None, swell_dir_max=None,
        time_window_start=time(6, 0), time_window_end=time(9, 0),
        operating_point="balanced", active=True, created_at=datetime.now(UTC),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)

    start, end = window_utc_for_date(TARGET_DATE, time(6, 0), time(9, 0))
    issued_at = datetime.now(UTC)
    hour = start
    while hour < end:
        db_session.add(
            Forecast(
                beach_id="herzliya", issued_at=issued_at, valid_at=hour,
                wave_height=1.4, wave_direction=301.1, wave_period=8.5,
                swell_wave_height=1.33, swell_wave_direction=301.1,
                wind_wave_height=0.07,
                wind_speed_10m=7.0, wind_direction_10m=121.1, wind_gusts_10m=9.0,
                fetched_at=issued_at,
            )
        )
        hour += timedelta(hours=1)
    await db_session.commit()
    return sub.id


@pytest.mark.asyncio
async def test_concurrent_evaluations_of_same_subscription_send_once(db_session):
    sub_id = await _seed(db_session)

    test_url, _ = _test_db_url_and_name()
    engine = create_async_engine(test_url.replace("postgresql", "postgresql+asyncpg", 1))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def run_eval():
        async with session_factory() as s:
            return await evaluate_subscription_for_date(s, sub_id, TARGET_DATE)

    results = await asyncio.gather(run_eval(), run_eval())
    await engine.dispose()

    # Exactly one of the two concurrent evaluations actually sent; the other, after
    # waiting on the row lock, saw the first's committed AlertSent row and found nothing
    # material to add.
    assert sorted(results) == ["alert", "none"], results

    rows = (
        await db_session.execute(
            AlertSent.__table__.select().where(AlertSent.subscription_id == sub_id)
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].kind == "alert"
