"""The dedup scenario -- prompts/phase-4-alerting.md acceptance check 1. Six forecast
refreshes over one target window: conditions drift slightly, then improve materially, then
drop below threshold. Exactly one initial alert, one material-change update, one
cancellation, and nothing else.
"""
from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.alerting.runner import evaluate_subscription_for_date
from app.alerting.timewindow import window_utc_for_date
from app.models import AlertSent, Beach, Forecast, Subscription

TARGET_DATE = date(2026, 1, 15)  # a plain Thursday, no DST boundary nearby


async def _seed_beach_and_sub(db_session) -> Subscription:
    beach = Beach(id="herzliya", name="Herzliya", lat=32.1660, lon=34.7960, shoreline_bearing=301.1)
    db_session.add(beach)
    sub = Subscription(
        user_id="u1",
        beach_id="herzliya",
        min_height=1.0,
        max_height=None,
        swell_dir_min=None,
        swell_dir_max=None,
        time_window_start=time(6, 0),
        time_window_end=time(9, 0),
        operating_point="balanced",
        active=True,
        created_at=datetime.now(UTC),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


async def _refresh_forecast(db_session, wave_height: float, refresh_num: int) -> None:
    """Simulates one ingestion poll: a fresh issued_at, new values for the 3 hours in the
    subscription's window -- offshore glassy wind and a good period throughout so height
    is what drives the qualifying/verdict changes in this test."""
    start, end = window_utc_for_date(TARGET_DATE, time(6, 0), time(9, 0))
    issued_at = datetime.now(UTC) + timedelta(seconds=refresh_num)  # strictly increasing
    hour = start
    while hour < end:
        db_session.add(
            Forecast(
                beach_id="herzliya",
                issued_at=issued_at,
                valid_at=hour,
                wave_height=wave_height,
                wave_direction=301.1,
                wave_period=8.5,
                swell_wave_height=wave_height * 0.95,
                swell_wave_direction=301.1,  # head-on -- exposure_factor ~1.0
                wind_wave_height=wave_height * 0.05,
                wind_speed_10m=7.0,           # light -- glassy regardless of direction
                wind_direction_10m=121.1,     # offshore (301.1 + 180)
                wind_gusts_10m=9.0,
                fetched_at=issued_at,
            )
        )
        hour += timedelta(hours=1)
    await db_session.commit()


@pytest.mark.asyncio
async def test_six_refreshes_produce_exactly_one_alert_one_update_one_cancellation(db_session):
    sub = await _seed_beach_and_sub(db_session)

    actions = []

    # Refresh 1: qualifies (1.4m, well above the 1.0m bar) -- initial alert.
    await _refresh_forecast(db_session, 1.4, 1)
    actions.append(await evaluate_subscription_for_date(db_session, sub.id, TARGET_DATE))

    # Refresh 2: drifts to 1.45m -- not material (< 0.3m height change), verdict unlikely
    # to flip at this size -- expect no action.
    await _refresh_forecast(db_session, 1.45, 2)
    actions.append(await evaluate_subscription_for_date(db_session, sub.id, TARGET_DATE))

    # Refresh 3: improves materially to 2.4m -- update.
    await _refresh_forecast(db_session, 2.4, 3)
    actions.append(await evaluate_subscription_for_date(db_session, sub.id, TARGET_DATE))

    # Refresh 4: unchanged -- no action.
    await _refresh_forecast(db_session, 2.4, 4)
    actions.append(await evaluate_subscription_for_date(db_session, sub.id, TARGET_DATE))

    # Refresh 5: drops below the 1.0m bar (and below the balanced-operating-point's
    # effective 0.85m floor) entirely -- cancellation.
    await _refresh_forecast(db_session, 0.4, 5)
    actions.append(await evaluate_subscription_for_date(db_session, sub.id, TARGET_DATE))

    # Refresh 6: still flat -- no action, stays silent after the cancellation.
    await _refresh_forecast(db_session, 0.3, 6)
    actions.append(await evaluate_subscription_for_date(db_session, sub.id, TARGET_DATE))

    assert actions == ["alert", "none", "update", "none", "cancellation", "none"], actions

    rows = (
        await db_session.execute(
            AlertSent.__table__.select().where(AlertSent.subscription_id == sub.id).order_by(AlertSent.sent_at)
        )
    ).all()
    kinds = [r.kind for r in rows]
    assert kinds == ["alert", "update", "cancellation"]
