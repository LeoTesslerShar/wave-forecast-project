"""Unit tests for the Open-Meteo marine/wind parsers, driven by committed fixtures."""
from datetime import UTC

from app.clients import open_meteo_forecast, open_meteo_marine


def test_marine_parse_hourly(marine_fixture):
    rows = open_meteo_marine.parse_hourly(marine_fixture)
    assert len(rows) > 0
    row = rows[0]
    assert row["valid_at"].tzinfo == UTC
    assert row["wave_height"] is not None
    assert row["swell_wave_height"] is not None
    assert row["wind_wave_direction"] is not None  # the var missing from the older fixture


def test_wind_parse_hourly(wind_fixture):
    rows = open_meteo_forecast.parse_hourly(wind_fixture)
    assert len(rows) > 0
    row = rows[0]
    assert row["valid_at"].tzinfo == UTC
    assert row["wind_speed_10m"] is not None
    assert row["wind_direction_10m"] is not None
