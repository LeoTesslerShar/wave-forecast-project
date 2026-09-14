"""Obstruction proximity check (app/exposure/obstruction.py). Uses the real committed OSM
structures extract -- no mocking, this is geometry against real data, same as the
coastline tests."""
from app.exposure.geo_utils import LocalProjection
from app.exposure.obstruction import (
    OBSTRUCTION_STRENGTH,
    _distance_to_nearest_structure,
    obstruction_fraction,
)


def test_returns_zero_or_the_flat_strength_never_in_between():
    lat, lon = 32.1660, 34.7960  # herzliya
    for swell_dir in range(0, 360, 30):
        f = obstruction_fraction(lat, lon, swell_dir)
        assert f in (0.0, OBSTRUCTION_STRENGTH)


def test_varies_by_direction_not_constant():
    """Regression test for the bug found during the Bat Yam vs Herzliya acceptance check:
    obstruction firing for every direction because the beach coordinate itself sits close
    to a structure, making the ray's first sample indistinguishable regardless of bearing."""
    lat, lon = 32.1660, 34.7960  # herzliya -- ~93m from the marina breakwater
    results = {d: obstruction_fraction(lat, lon, d) for d in range(0, 360, 20)}
    assert len(set(results.values())) > 1, (
        "obstruction is identical for every swell direction -- likely the self-exclusion "
        "bug (see OBSTRUCTION_MIN_CHECK_DISTANCE_M) rather than a genuine direction-"
        "independent shadow"
    )


def test_open_water_direction_has_no_obstruction_far_from_any_structure():
    # A point well inland from any mapped structure/coastline in this dataset's bbox.
    lat, lon = 32.20, 34.85
    assert obstruction_fraction(lat, lon, 270.0) == 0.0


def test_distance_to_nearest_structure_is_positive_and_finite():
    proj = LocalProjection(ref_lat=32.166)
    d = _distance_to_nearest_structure(32.1660, 34.7960, proj)
    assert 0 < d < 50_000
