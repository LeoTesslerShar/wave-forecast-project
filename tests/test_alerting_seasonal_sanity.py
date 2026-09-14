"""Seasonal sanity -- prompts/phase-4-alerting.md section 7 / acceptance check 6. A
multi-week all-flat window produces zero alerts (correctly -- nothing qualified) and a
status a user can check, distinct from "the system stopped working"."""
from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.alerting.runner import evaluate_subscription_for_date
from app.alerting.status import get_subscription_status
from app.alerting.timewindow import window_utc_for_date
from app.models import AlertSent, Beach, Forecast, IngestionRun, Subscription

START_DATE = date(2026, 7, 1)  # a flat Israeli summer stretch -- docs/BIAS_ANALYSIS.md
WEEKS = 3


@pytest.mark.asyncio
async def test_three_week_flat_spell_produces_no_alerts_and_a_checkable_status(db_session):
    beach = Beach(id="herzliya", name="Herzliya", lat=32.1660, lon=34.7960, shoreline_bearing=301.1)
    db_session.add(beach)
    sub = Subscription(
        user_id="u1", beach_id="herzliya", min_height=1.0, max_height=None,
        swell_dir_min=None, swell_dir_max=None,
        time_window_start=time(6, 0), time_window_end=time(9, 0),
        operating_point="balanced", active=True, created_at=datetime.now(UTC),
    )
    db_session.add(sub)
    # Proves the system is alive -- distinguishes "flat" from "stopped evaluating".
    db_session.add(
        IngestionRun(
            source="wave", started_at=datetime.now(UTC), finished_at=datetime.now(UTC),
            status="success", rows_written=100,
        )
    )
    await db_session.commit()
    await db_session.refresh(sub)

    dates = [START_DATE + timedelta(days=i) for i in range(WEEKS * 7)]
    for target_date in dates:
        start, end = window_utc_for_date(target_date, time(6, 0), time(9, 0))
        issued_at = datetime.now(UTC)
        hour = start
        while hour < end:
            db_session.add(
                Forecast(
                    beach_id="herzliya", issued_at=issued_at, valid_at=hour,
                    wave_height=0.2, wave_direction=301.1, wave_period=4.0,  # genuinely flat
                    swell_wave_height=0.18, swell_wave_direction=301.1,
                    wind_wave_height=0.02,
                    wind_speed_10m=10.0, wind_direction_10m=301.1, wind_gusts_10m=14.0,
                    fetched_at=issued_at,
                )
            )
            hour += timedelta(hours=1)
        await db_session.commit()

    actions = []
    for target_date in dates:
        actions.append(await evaluate_subscription_for_date(db_session, sub.id, target_date))

    assert set(actions) == {"none"}, "a flat spell must never produce a spontaneous alert"

    alert_rows = (
        await db_session.execute(AlertSent.__table__.select().where(AlertSent.subscription_id == sub.id))
    ).all()
    assert alert_rows == []

    status = await get_subscription_status(db_session, sub.id)
    assert status is not None
    assert status.system_healthy is True
    assert status.currently_alerted is False
    assert "nothing" in status.message.lower()
