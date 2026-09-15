"""Unit tests for the quality scorer -- prompts/phase-3-quality.md acceptance checks 1, 2, 4.
No DB, no network: pure combination logic against the sub-scorers directly."""
from app.exposure.apply import SURF_HEIGHT_FACTOR
from app.quality.chop import classify_chop
from app.quality.period import classify_period
from app.quality.size import classify_size
from app.quality.verdict import combine
from app.quality.wind import classify_wind

HERZLIYA_BEARING = 301.1


def _score(size_m, period_s, wind_speed, wind_dir, gusts, swell_h, wind_h, surf_height_m=None):
    size = classify_size(size_m)
    period = classify_period(period_s)
    wind = classify_wind(wind_speed, wind_dir, gusts, HERZLIYA_BEARING)
    chop = classify_chop(swell_h, wind_h)
    if surf_height_m is None:
        surf_height_m = round(size_m * SURF_HEIGHT_FACTOR, 2)
    return combine(size, period, wind, chop, surf_height_m=surf_height_m)


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
    well as the same height with a clean groundswell face.

    size_m=1.8, not the original 1.3: at 1.3 (surf height ~1.04m) BOTH scenarios' raw
    weighted scores land above SIZE_CEILING's 0.8-1.2m bucket (7.0) and saturate to the
    identical clamped number, which erases the chop-driven numeric gap this test exists to
    check (the verdict WORD still correctly degrades good->fair via the separate onshore/
    choppy _cap mechanism, just not the number). 1.8 keeps surf height under 2.0m, where the
    ceiling is 10 (effectively unbound), so the underlying chop difference shows through."""
    clean = _score(
        size_m=1.8, period_s=8.0, wind_speed=8, wind_dir=(HERZLIYA_BEARING + 180) % 360, gusts=10,
        swell_h=1.25, wind_h=0.05,  # chop ratio ~0.04
    )
    choppy = _score(
        size_m=1.8, period_s=8.0, wind_speed=8, wind_dir=(HERZLIYA_BEARING + 180) % 360, gusts=10,
        swell_h=0.5, wind_h=0.8,  # chop ratio ~0.62 -- same swell/wind-wave split, mostly wind-chop
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
            assert 0.0 <= v.quality_score <= 10.0


def test_small_surf_height_can_never_score_as_excellent():
    """Regression test for the reported bug: a 0.5m day with clean wind/period/chop scored
    0.9375 (on the old 0..1 scale) -- "excellent" -- despite there being, in the user's own
    words, "no waves at 0.5". The SIZE_CEILING in verdict.py must cap the numeric score, not
    just relabel it, since ranking/alerting sort on the raw number."""
    v = _score(
        size_m=0.62, period_s=9.0,  # Hs 0.62m -> surf height ~0.5m at SURF_HEIGHT_FACTOR
        wind_speed=6, wind_dir=(HERZLIYA_BEARING + 180) % 360, gusts=8,  # glassy
        swell_h=0.6, wind_h=0.02,  # clean
    )
    assert v.quality_score <= 4.0, f"a 0.5m day must not score above the small-size ceiling, got {v.quality_score}"
    assert v.verdict not in ("good", "excellent"), f"a 0.5m day must not read {v.verdict}"


def test_strong_onshore_wind_caps_the_score_hard():
    """Wind SPEED did not affect the old score at all above 8 km/h -- a 60 km/h onshore gale
    scored identically to a 9 km/h breeze, purely on direction. WIND_CEILING must cap a big,
    clean, well-timed swell if the wind blowing straight into it is strong enough to wreck it."""
    v = _score(
        size_m=1.5, period_s=9.0,
        wind_speed=45, wind_dir=HERZLIYA_BEARING, gusts=50,  # dead onshore, very strong
        swell_h=1.4, wind_h=0.1,
    )
    assert v.quality_score <= 2.0, f"a 45 km/h onshore gale must cap the score hard, got {v.quality_score}"


def test_strong_offshore_wind_is_not_punished():
    """The mirror case: strong OFFSHORE wind grooms the face and must not be capped the same
    way onshore wind is -- only once it gets strong enough to hold the wave up too much."""
    v = _score(
        size_m=1.5, period_s=9.0,
        wind_speed=25, wind_dir=(HERZLIYA_BEARING + 180) % 360, gusts=28,  # dead offshore, brisk
        swell_h=1.4, wind_h=0.1,
    )
    assert v.quality_score >= 7.0, f"brisk offshore wind should not cap a clean, well-sized swell, got {v.quality_score}"
