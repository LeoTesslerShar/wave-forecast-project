"""Unit tests for the quality scorer -- prompts/phase-3-quality.md acceptance checks 1, 2, 4.
No DB, no network: pure combination logic against the sub-scorers directly."""
from app.quality.chop import classify_chop
from app.quality.period import classify_period
from app.quality.size import classify_size
from app.quality.verdict import combine
from app.quality.wind import classify_wind

HERZLIYA_BEARING = 301.1


def _score(size_m, period_s, wind_speed, wind_dir, gusts, swell_h, wind_h):
    size = classify_size(size_m)
    period = classify_period(period_s)
    wind = classify_wind(wind_speed, wind_dir, gusts, HERZLIYA_BEARING)
    chop = classify_chop(swell_h, wind_h)
    return combine(size, period, wind, chop)


def test_storm_peak_scores_worse_than_following_dawn():
    """Acceptance check 1 -- the test the whole idea rests on. Real numbers: an afternoon
    storm peak (big, choppy, onshore) vs the next dawn (smaller, clean, offshore) once the
    land breeze has turned -- the local pattern section 2 describes explicitly."""
    storm = _score(
        size_m=2.2, period_s=6.5,
        wind_speed=32, wind_dir=HERZLIYA_BEARING, gusts=48,  # onshore, strong, gusty
        swell_h=1.6, wind_h=0.9,
    )
    dawn = _score(
        size_m=1.4, period_s=8.5,
        wind_speed=9, wind_dir=(HERZLIYA_BEARING + 180) % 360, gusts=12,  # offshore, light
        swell_h=1.3, wind_h=0.2,
    )

    assert dawn.quality_score > storm.quality_score
    assert ["flat", "poor", "fair", "good", "excellent"].index(dawn.verdict) > \
           ["flat", "poor", "fair", "good", "excellent"].index(storm.verdict)
    assert "onshore" in storm.reasoning
    assert "offshore" in dawn.reasoning


def test_full_day_hour_by_hour_wind_rotation():
    """Acceptance check 2: a worked example across a day as wind rotates from onshore
    (afternoon storm) to offshore (dawn) -- score must vary hour-by-hour, not stay flat."""
    hours = [
        # (label, wind_speed, wind_dir_offset_from_bearing, gusts)
        ("14:00 storm peak", 30, 0, 45),        # onshore
        ("18:00 storm easing", 22, 20, 30),      # still onshore-ish
        ("22:00 transition", 14, 90, 16),        # cross-shore
        ("02:00 land breeze building", 10, 150, 12),  # nearly offshore
        ("06:00 dawn glass-off", 8, 180, 10),     # offshore
    ]
    scores = []
    for label, speed, offset, gusts in hours:
        wind_dir = (HERZLIYA_BEARING + offset) % 360
        v = _score(size_m=1.5, period_s=8.0, wind_speed=speed, wind_dir=wind_dir, gusts=gusts,
                   swell_h=1.3, wind_h=0.2)
        scores.append((label, v.quality_score, v.verdict))

    values = [s[1] for s in scores]
    assert len(set(values)) > 1, f"score did not vary hour-by-hour: {scores}"
    # Monotonic improvement as wind rotates from onshore to offshore, same swell throughout.
    assert values == sorted(values), f"expected monotonic improvement toward dawn: {scores}"
    assert scores[-1][1] > scores[0][1]


def test_high_chop_degrades_verdict_even_at_good_height():
    """Acceptance check 4: a 'good' height sea that is mostly wind-chop must not verdict as
    well as the same height with a clean groundswell face."""
    clean = _score(
        size_m=1.3, period_s=8.0, wind_speed=8, wind_dir=(HERZLIYA_BEARING + 180) % 360, gusts=10,
        swell_h=1.25, wind_h=0.05,  # chop ratio ~0.04
    )
    choppy = _score(
        size_m=1.3, period_s=8.0, wind_speed=8, wind_dir=(HERZLIYA_BEARING + 180) % 360, gusts=10,
        swell_h=0.5, wind_h=0.8,  # chop ratio ~0.62 -- same total height, mostly wind-chop
    )

    assert clean.quality_score > choppy.quality_score
    assert "clean" in clean.reasoning
    assert "chop" in choppy.reasoning


def test_flat_size_overrides_everything():
    v = _score(size_m=0.15, period_s=9.0, wind_speed=8, wind_dir=(HERZLIYA_BEARING + 180) % 360,
               gusts=10, swell_h=0.14, wind_h=0.01)
    assert v.verdict == "flat"


def test_verdict_is_always_one_of_the_defined_ladder():
    from app.quality.verdict import LADDER
    for size_m in [0.1, 0.4, 0.8, 1.3, 2.0, 3.0]:
        for wind_dir_offset in [0, 45, 90, 135, 180]:
            v = _score(size_m, 7.5, 15, (HERZLIYA_BEARING + wind_dir_offset) % 360, 20, 1.0, 0.3)
            assert v.verdict in LADDER
            assert 0.0 <= v.quality_score <= 1.0
