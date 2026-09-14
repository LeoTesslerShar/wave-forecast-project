from datetime import UTC, datetime, timedelta

from app.alerting.material_change import Snapshot, is_material_change


def _snap(height=1.4, verdict="good", start_offset=0, end_offset=3):
    base = datetime(2026, 1, 15, 6, 0, tzinfo=UTC)
    return Snapshot(
        window_start=base + timedelta(hours=start_offset),
        window_end=base + timedelta(hours=end_offset),
        height_estimate_m=height,
        height_range_m=(height - 0.25, height + 0.25),
        quality_verdict=verdict,
        quality_score=0.7,
        operating_point="balanced",
        effective_threshold_m=None,
    )


def test_small_height_drift_is_not_material():
    material, _ = is_material_change(_snap(1.4), _snap(1.45))
    assert material is False


def test_large_height_change_is_material():
    material, reason = is_material_change(_snap(1.4), _snap(2.2))
    assert material is True
    assert "height" in reason


def test_verdict_change_is_always_material():
    material, reason = is_material_change(_snap(1.4, verdict="fair"), _snap(1.4, verdict="excellent"))
    assert material is True
    assert "verdict" in reason


def test_window_shift_is_material():
    material, reason = is_material_change(_snap(), _snap(start_offset=2))
    assert material is True
    assert "window" in reason


def test_snapshot_round_trips_through_dict():
    s = _snap()
    restored = Snapshot.from_dict(s.to_dict())
    assert restored == s
