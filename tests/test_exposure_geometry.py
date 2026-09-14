"""Geometry tests for the exposure layer -- prompts/phase-2-exposure.md section 2/acceptance
checks 1-3. No live network: coastline/structure data comes from the committed
scripts/exposure/*.geojson extracts."""

from app.exposure.bearing import compute_shoreline_bearing
from app.exposure.scoring import compute_exposure, directional_exposure

BEACHES = {
    "bat_yam": (32.0133, 34.7432, 284.6),
    "herzliya": (32.1660, 34.7960, 301.1),
    "palmachim": (31.9300, 34.6940, 296.7),
    "netanya": (32.3210, 34.8490, 282.3),
    "ashdod": (31.7830, 34.6290, 295.2),
    "hadera": (32.4370, 34.8830, 281.5),
    "olga": (32.4000, 34.8700, 262.4),
    "tel_aviv_hilton": (32.0870, 34.7690, 283.6),
}


def test_all_beach_bearings_face_broadly_seaward():
    """Acceptance check 1: every computed bearing for the Israeli Mediterranean coast
    should face broadly west -- the coastline runs roughly north-south with the sea to the
    west (documented assumption in app/exposure/bearing.py)."""
    for beach_id, (lat, lon, _expected) in BEACHES.items():
        r = compute_shoreline_bearing(lat, lon)
        # "broadly seaward" for this coast: between due south-west and due north-west,
        # generously bounded to tolerate real coastline curvature.
        assert 200 <= r.bearing_deg <= 340, (
            f"{beach_id}: bearing {r.bearing_deg} is not broadly westward -- geometry bug "
            f"or a genuinely unusual stretch of coast that needs manual review"
        )


def test_direction_convention_head_on_swell_scores_high():
    """Swell arriving FROM the exact shoreline normal hits the beach head-on."""
    lat, lon, bearing = BEACHES["herzliya"]
    factor, diff = directional_exposure(swell_direction_from=bearing, shoreline_bearing=bearing)
    assert diff == 0
    assert factor == 1.0


def test_direction_convention_swell_from_behind_scores_zero():
    """Swell 'arriving' from 180 degrees opposite the shoreline normal would have to pass
    through land first -- must score zero, not just low."""
    lat, lon, bearing = BEACHES["herzliya"]
    opposite = (bearing + 180) % 360
    factor, diff = directional_exposure(swell_direction_from=opposite, shoreline_bearing=bearing)
    assert diff == 180
    assert factor == 0.0


def test_offshore_parallel_swell_scores_zero():
    """Swell running parallel to the shore (90 degrees off the normal) does not reach the
    break -- the clamp boundary, acceptance check 3."""
    lat, lon, bearing = BEACHES["herzliya"]
    parallel = (bearing + 90) % 360
    factor, diff = directional_exposure(swell_direction_from=parallel, shoreline_bearing=bearing)
    assert diff == 90
    assert factor == 0.0

    # And just past parallel -- still zero, not negative.
    just_past = (bearing + 91) % 360
    factor2, _ = directional_exposure(swell_direction_from=just_past, shoreline_bearing=bearing)
    assert factor2 == 0.0


def test_bat_yam_vs_herzliya_known_truth():
    """Acceptance check 2 -- the case the planning doc opens with. Under a typical Israeli
    winter WNW groundswell (300 degrees -- the dominant swell window for this coast),
    Herzliya must score higher than Bat Yam, with a stated geometric reason."""
    swell_direction = 300.0
    bat_yam_lat, bat_yam_lon, bat_yam_bearing = BEACHES["bat_yam"]
    herzliya_lat, herzliya_lon, herzliya_bearing = BEACHES["herzliya"]

    bat_yam = compute_exposure(bat_yam_lat, bat_yam_lon, bat_yam_bearing, swell_direction)
    herzliya = compute_exposure(herzliya_lat, herzliya_lon, herzliya_bearing, swell_direction)

    assert herzliya.exposure_factor > bat_yam.exposure_factor, (
        f"expected Herzliya ({herzliya.exposure_factor}) > Bat Yam ({bat_yam.exposure_factor}) "
        f"under a {swell_direction} degree swell -- exposure model contradicts the known case"
    )
    # The geometric reason: Herzliya's shoreline faces closer to this swell's arrival
    # direction than Bat Yam's does.
    assert herzliya.angular_difference_deg < bat_yam.angular_difference_deg


def test_exposure_factor_never_exceeds_one_or_goes_negative():
    for beach_id, (lat, lon, bearing) in BEACHES.items():
        for swell_dir in range(0, 360, 15):
            r = compute_exposure(lat, lon, bearing, swell_dir)
            assert 0.0 <= r.exposure_factor <= 1.0, f"{beach_id} @ {swell_dir}: {r.exposure_factor}"


def test_no_shoreline_bearing_degrades_to_fully_exposed_not_a_crash():
    r = compute_exposure(32.0, 34.7, None, 280.0)
    assert r.exposure_factor == 1.0
    assert r.method == "no_shoreline_bearing_available"


def test_max_segment_span_reports_true_length_not_capped_at_window_budget():
    """Regression test for a bug caught during review: the walk truncates at the window
    budget (250m half-window), but max_segment_span_m must report the underlying segment's
    real length beyond that point, not the budget itself. Netanya and Ashdod both rest on
    OSM segments ~2-3km long (verified as legitimate mapped coastline, not sparse data --
    docs/DECISIONS.md); the bug reported exactly 250.0 for both, which is the window's own
    half-width by construction and would be true regardless of the underlying data."""
    for lat, lon in [(32.321, 34.849), (31.783, 34.629)]:  # netanya, ashdod
        r = compute_shoreline_bearing(lat, lon)
        assert r.max_segment_span_m > 250.0, (
            f"max_segment_span_m={r.max_segment_span_m} looks capped at the window "
            f"half-width rather than reporting the real segment length"
        )
