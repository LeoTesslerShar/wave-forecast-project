"""Unit tests for the ISRAMAR Hadera parser, driven by the committed fixture -- no live
network. Confirms Hs/Tp/Hmax are kept distinct (docs/DATA_SOURCES.md)."""
from app.clients.isramar import parse_reading


def test_parses_real_fixture(hadera_fixture):
    reading = parse_reading(hadera_fixture)
    assert reading is not None
    assert reading["wave_height"] == 0.42
    assert reading["wave_period"] == 5.9
    assert reading["wave_max"] == 0.5334
    assert reading["observed_at"].year == 2026


def test_missing_wave_height_returns_none():
    payload = {
        "datetime": "2026-09-13 14:00 UTC",
        "parameters": [{"name": "Peak wave period", "units": "s", "values": [5.9]}],
    }
    assert parse_reading(payload) is None


def test_unparseable_datetime_returns_none():
    payload = {"datetime": "not a date", "parameters": []}
    assert parse_reading(payload) is None


def test_out_of_range_value_rejected():
    payload = {
        "datetime": "2026-09-13 14:00 UTC",
        "parameters": [{"name": "Significant wave height", "units": "m", "values": [-5]}],
    }
    assert parse_reading(payload) is None
