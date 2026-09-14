"""Calibrated threshold -- prompts/phase-4-alerting.md acceptance check 5."""
from app.alerting.calibration import (
    BIAS_TABLE,
    describe_operating_point,
    missed_rate_pct,
    wasted_rate_pct,
)


def test_interpolation_matches_measured_table_exactly_at_its_own_points():
    for threshold, missed, wasted in BIAS_TABLE:
        assert missed_rate_pct(threshold) == missed
        assert wasted_rate_pct(threshold) == wasted


def test_missed_rate_increases_with_threshold():
    """docs/BIAS_ANALYSIS.md: the model misses more real sessions as the bar rises."""
    assert missed_rate_pct(0.6) < missed_rate_pct(1.0) < missed_rate_pct(1.5)


def test_strict_never_lowers_the_effective_threshold():
    e = describe_operating_point(1.5, "strict")
    assert e.effective_threshold_m == 1.5
    assert e.extra_sessions_caught_pct == 0.0
    assert e.extra_false_alarms_pct == 0.0


def test_generous_catches_more_than_balanced_at_more_false_alarm_cost():
    balanced = describe_operating_point(1.5, "balanced")
    generous = describe_operating_point(1.5, "generous")
    assert generous.effective_threshold_m < balanced.effective_threshold_m
    assert generous.extra_sessions_caught_pct >= balanced.extra_sessions_caught_pct
    assert generous.extra_false_alarms_pct >= balanced.extra_false_alarms_pct


def test_description_cites_the_real_numbers_not_invented_ones():
    e = describe_operating_point(1.0, "generous")
    assert f"{e.extra_sessions_caught_pct:.0f}%" in e.description
    assert "docs/BIAS_ANALYSIS.md" in e.description


def test_threshold_below_measured_range_does_not_extrapolate_wildly():
    # 0.1m is below the measured table's lowest point (0.6m) -- clamped, not extrapolated.
    assert missed_rate_pct(0.1) == missed_rate_pct(0.6)
    assert missed_rate_pct(5.0) == missed_rate_pct(1.5)
