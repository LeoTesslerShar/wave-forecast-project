"""End-to-end -- prompts/phase-4-alerting.md acceptance check 7. Create a subscription via
the API, force a matching forecast, show the push attempt logged with its full payload."""
import logging
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import patch

import pytest

from app.alerting.runner import evaluate_subscription_for_date
from app.alerting.timewindow import window_utc_for_date
from app.api.alerting import create_subscription, register_push_subscription
from app.models import Beach, Forecast
from app.schemas import PushSubscriptionCreate, SubscriptionCreate

TARGET_DATE = date(2026, 2, 3)


@pytest.mark.asyncio
async def test_end_to_end_subscription_forecast_and_push_payload(db_session, caplog):
    beach = Beach(id="herzliya", name="Herzliya", lat=32.1660, lon=34.7960, shoreline_bearing=301.1)
    db_session.add(beach)
    await db_session.commit()

    # 1. Create a subscription through the real API function.
    sub = await create_subscription(
        SubscriptionCreate(
            user_id="surfer1", beach_id="herzliya", min_height=1.0,
            time_window_start=time(6, 0), time_window_end=time(9, 0), operating_point="balanced",
        ),
        session=db_session,
    )

    # 2. Register a push endpoint through the real API function.
    await register_push_subscription(
        PushSubscriptionCreate(user_id="surfer1", endpoint="https://push.example/e2e", p256dh="k", auth="a"),
        session=db_session,
    )

    # 3. Force a matching forecast -- clean offshore, good size and period.
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
                wind_speed_10m=12.0, wind_direction_10m=121.1, wind_gusts_10m=15.0,
                fetched_at=issued_at,
            )
        )
        hour += timedelta(hours=1)
    await db_session.commit()

    # 4. Run evaluation, capturing both the logged event and the actual push payload.
    captured = {}

    def fake_send_push(push_subscription, payload):
        captured["payload"] = payload
        from app.alerting.push import PushResult
        return PushResult.SENT

    with caplog.at_level(logging.INFO, logger="alerting.runner"):
        with patch("app.alerting.runner.send_push", side_effect=fake_send_push):
            action = await evaluate_subscription_for_date(db_session, sub.id, TARGET_DATE)

    assert action == "alert"

    # The push attempt is in the logs.
    assert any("alert action taken" in r.message for r in caplog.records)

    # The full payload -- range, quality components, operating point (acceptance check 7).
    payload = captured["payload"]
    print("\n--- captured push payload ---")
    print(payload)
    assert payload["height_range_m"] is not None and len(payload["height_range_m"]) == 2
    assert payload["quality_components"]["wind"]["relation_to_shore"] == "offshore"
    assert payload["quality_components"]["chop_ratio"] is not None
    assert payload["quality_components"]["period_s"] is not None
    assert payload["operating_point"] == "balanced"
    assert "honesty_marker" in payload
