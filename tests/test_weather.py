"""WMO weather-code translation -- app/quality/weather.py. Unlike most heuristics in this
project, this is a standard published lookup table, not a judgement call."""
from app.quality.weather import classify_weather


def test_known_codes():
    assert classify_weather(0).icon_key == "clear"
    assert classify_weather(0).label == "בהיר"
    assert classify_weather(2).icon_key == "partly_cloudy"
    assert classify_weather(3).icon_key == "cloudy"
    assert classify_weather(61).icon_key == "rain"
    assert classify_weather(95).icon_key == "storm"


def test_none_or_unrecognised_code_degrades_not_crashes():
    assert classify_weather(None).icon_key == "unknown"
    assert classify_weather(-1).icon_key == "unknown"
    assert classify_weather(12345).icon_key == "unknown"
