"""Obstruction proximity check (app/exposure/obstruction.py). Uses the real committed OSM
structures extract -- no mocking, this is geometry against real data, same as the
coastline tests."""
from app.exposure.geo_utils import LocalProjection, destination_point
from app.exposure.obstruction import (
    OBSTRUCTION_LATERAL_THRESHOLD_M,
    OBSTRUCTION_STRENGTH,
    _distance_to_nearest_structure,
    _within_threshold_of_structure,
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


def test_projected_structures_cache_gives_identical_results_to_a_fresh_projection():
    """Regression test for a caching bug caught by test_exposure_geometry's known-truth
    test: an earlier version of this cache bucketed the reference latitude to 0.1 degrees
    to increase the hit rate, which silently flipped Herzliya's obstruction at a 300 degree
    swell (false -> true) by shifting the coordinate frame just enough to cross the 150m
    threshold on a near-boundary case. The cache must key on the EXACT ref_lat, not a
    rounded one -- this pins the specific case that broke."""
    from app.exposure.obstruction import _projected_structures

    lat, lon = 32.1660, 34.7960  # herzliya
    proj = LocalProjection(ref_lat=lat)

    cached = _distance_to_nearest_structure(lat, lon, proj)
    # Force a fresh, uncached projection at the exact same ref_lat and confirm it agrees
    # bit-for-bit -- proves the cache is not silently approximating anything.
    _projected_structures.cache_clear()
    fresh = _distance_to_nearest_structure(lat, lon, proj)
    assert cached == fresh

    # The specific case the rounded-latitude cache got wrong: Herzliya at a 300 degree
    # swell must be CLEAR (0.0), not obstructed -- test_exposure_geometry.py's own
    # Bat-Yam-vs-Herzliya known-truth test depends on this (directional_factor alone
    # decides the ranking there; obstruction must not silently add a false positive).
    assert obstruction_fraction(lat, lon, 300.0) == 0.0


def test_grid_threshold_check_agrees_with_exhaustive_scan():
    """Regression/correctness test for the grid-index performance fix
    (_within_threshold_of_structure): for a spread of real sample points along each beach's
    swell ray, the grid-indexed threshold check must agree with the exhaustive nearest-
    structure scan it replaced in the hot path. A grid bug (wrong cell size, off-by-one
    neighbour range) would silently miss structures near a cell boundary -- exactly the kind
    of approximation drift the exact-ref_lat cache fix above was written to guard against."""
    beaches = [
        (32.1660, 34.7960),  # herzliya
        (32.0133, 34.7432),  # bat yam
        (31.9300, 34.6940),  # palmachim
        (31.7830, 34.6290),  # ashdod
    ]
    for lat, lon in beaches:
        proj = LocalProjection(ref_lat=lat)
        for swell_dir in range(0, 360, 15):
            for dist in range(300, 1600, 100):
                sample_lat, sample_lon = destination_point(lat, lon, swell_dir, dist)
                exhaustive = _distance_to_nearest_structure(sample_lat, sample_lon, proj)
                grid_hit = _within_threshold_of_structure(
                    sample_lat, sample_lon, proj, OBSTRUCTION_LATERAL_THRESHOLD_M
                )
                assert grid_hit == (exhaustive <= OBSTRUCTION_LATERAL_THRESHOLD_M), (
                    f"grid/exhaustive disagreement at ({sample_lat}, {sample_lon}): "
                    f"exhaustive nearest={exhaustive}, grid_hit={grid_hit}"
                )
