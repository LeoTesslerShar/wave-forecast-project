"""Calibrated threshold end-to-end -- prompts/phase-4-alerting.md acceptance check 5.
A forecast at 1.35m with a subscription set to >=1.5m: 'generous' fires, 'strict' does not.
The fired alert's text names the gap and the calibration reason (section 6).
"""
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import patch

import pytest

from app.alerting.runner import evaluate_subscription_for_date
from app.alerting.timewindow import window_utc_for_date
from app.models import Beach, Forecast, PushSubscription, Subscription

TARGET_DATE = date(2026, 1, 22)


async def _seed_forecast(db_session):
    beach = Beach(id="herzliya", name="Herzliya", lat=32.1660, lon=34.7960, shoreline_bearing=301.1)
    db_session.add(beach)
    await db_session.commit()

    start, end = window_utc_for_date(TARGET_DATE, time(6, 0), time(9, 0))
    issued_at = datetime.now(UTC)
    hour = start
    while hour < end:
        db_session.add(
            Forecast(
                beach_id="herzliya", issued_at=issued_at, valid_at=hour,
                wave_height=1.35, wave_direction=301.1, wave_period=8.5,
                swell_wave_height=1.28, swell_wave_direction=301.1,
                wind_wave_height=0.07,
                wind_speed_10m=7.0, wind_direction_10m=121.1, wind_gusts_10m=9.0,
                fetched_at=issued_at,
            )
        )
        hour += timedelta(hours=1)
    await db_session.commit()


async def _make_subscription(db_session, operating_point: str, beach_id="herzliya") -> Subscription:
    sub = Subscription(
        user_id=f"u_{operating_point}", beach_id=beach_id, min_height=1.5, max_height=None,
        swell_dir_min=None, swell_dir_max=None,
        time_window_start=time(6, 0), time_window_end=time(9, 0),
        operating_point=operating_point, active=True, created_at=datetime.now(UTC),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


@pytest.mark.asyncio
async def test_generous_fires_strict_does_not_at_1_35m_against_1_5m_bar(db_session):
    await _seed_forecast(db_session)

    strict_sub = await _make_subscription(db_session, "strict")
    generous_sub = await _make_subscription(db_session, "generous")

    strict_action = await evaluate_subscription_for_date(db_session, strict_sub.id, TARGET_DATE)
    generous_action = await evaluate_subscription_for_date(db_session, generous_sub.id, TARGET_DATE)

    assert strict_action == "none"
    assert generous_action == "alert"


@pytest.mark.asyncio
async def test_fired_alert_names_the_gap_and_calibration_reason(db_session):
    await _seed_forecast(db_session)
    sub = await _make_subscription(db_session, "generous", beach_id="herzliya")

    push_sub = PushSubscription(
        user_id=sub.user_id, endpoint="https://push.example/x", p256dh="k", auth="a",
        active=True, created_at=datetime.now(UTC),
    )
    db_session.add(push_sub)
    await db_session.commit()

    captured = {}

    def fake_send_push(push_subscription, payload):
        captured["payload"] = payload
        from app.alerting.push import PushResult
        return PushResult.SENT

    with patch("app.alerting.runner.send_push", side_effect=fake_send_push):
        action = await evaluate_subscription_for_date(db_session, sub.id, TARGET_DATE)

    assert action == "alert"
    payload = captured["payload"]
    assert payload["calibration_note"] is not None
    assert "1.50" in payload["calibration_note"]  # names the user's literal bar
    assert "1.3" in payload["calibration_note"]    # names the actual (lower) height
    assert "generous" in payload["calibration_note"]
