"""Obstruction proximity check (app/exposure/obstruction.py). Uses the real committed OSM
structures extract -- no mocking, this is geometry against real data, same as the
coastline tests."""
from app.exposure.geo_utils import LocalProjection, destination_point
from app.exposure.obstruction import (
    OBSTRUCTION_LATERAL_THRESHOLD_M,
    OBSTRUCTION_STRENGTH,
    _distance_to_nearest_structure,
    _nearest_structure_within,
    obstruction_fraction,
)


def test_stays_within_zero_and_the_maximum_strength():
    lat, lon = 32.1660, 34.7960  # herzliya
    for swell_dir in range(0, 360, 30):
        f = obstruction_fraction(lat, lon, swell_dir)
        assert 0.0 <= f <= OBSTRUCTION_STRENGTH


def test_obstruction_is_graded_by_closest_approach_not_all_or_nothing():
    """Regression test for the binary-penalty bug (docs/DECISIONS.md): obstruction used to
    be a flat OBSTRUCTION_STRENGTH the moment anything came within
    OBSTRUCTION_LATERAL_THRESHOLD_M, which made the model discontinuous. Netanya's groyne
    sits ~436m from its beach coordinate (well outside the near-beach exclusion radius, so
    this exercises grading itself, not exclusion): at a 293 degree swell the ray grazes it
    at ~42m lateral, comfortably inside the threshold but far from a direct hit -- grading
    must land somewhere in between, not snap to the flat maximum."""
    netanya = (32.321, 34.849)
    graded = obstruction_fraction(*netanya, 293.0)
    assert 0.15 * OBSTRUCTION_STRENGTH < graded < 0.85 * OBSTRUCTION_STRENGTH, (
        f"a ray grazing a real, non-excluded structure at ~42m (out of a 150m threshold) "
        f"should land clearly between 0 and the flat maximum, got {graded}"
    )

    # Bat Yam at the same swell: the ray crosses a structure almost head-on (~13m), so it
    # must still take nearly the full reduction -- grading must not defang real blocking.
    bat_yam_direct = obstruction_fraction(32.0133, 34.7432, 293.0)
    assert bat_yam_direct > 0.8 * OBSTRUCTION_STRENGTH, (
        f"a ray passing within ~13m of a breakwater must still be heavily blocked, "
        f"got {bat_yam_direct}"
    )


def test_structure_near_the_beach_itself_is_excluded_entirely_not_just_near_samples():
    """Regression test for a user report (docs/DECISIONS.md): Tel Aviv (Hilton) showed a
    25% obstruction driven by a breakwater only ~13m from its own beach coordinate -- local
    infrastructure at the beach itself, not a genuine offshore shadow-caster. The bug was
    that OBSTRUCTION_MIN_CHECK_DISTANCE_M only skipped ray SAMPLES within that distance of
    the beach, not the offending structure itself, so a later sample further along the ray
    could still register a hit against the very same nearby structure (its footprint reached
    out that far). A real forecast (swell 299 degrees) triggered exactly this. Fixed by
    excluding any structure with a point closer than OBSTRUCTION_MIN_CHECK_DISTANCE_M to the
    beach from consideration at every sample distance, not only the first few."""
    tel_aviv_hilton = (32.087, 34.769)
    assert obstruction_fraction(*tel_aviv_hilton, 299.0) == 0.0

    # And Herzliya's marina breakwater (~93m from its coordinate) must likewise no longer
    # contribute anywhere -- this was the case that originally motivated the exclusion
    # concept, before it turned out only to be applied at the sample level.
    herzliya = (32.1660, 34.7960)
    assert obstruction_fraction(*herzliya, 295.0) == 0.0
    assert obstruction_fraction(*herzliya, 293.0) == 0.0


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
                grid = _nearest_structure_within(
                    sample_lat, sample_lon, proj, OBSTRUCTION_LATERAL_THRESHOLD_M
                )
                if exhaustive <= OBSTRUCTION_LATERAL_THRESHOLD_M:
                    # Inside the threshold the grid result must be EXACT, not just a
                    # correct yes/no -- the graded penalty is computed from this distance.
                    assert grid == exhaustive, (
                        f"grid/exhaustive disagreement at ({sample_lat}, {sample_lon}): "
                        f"exhaustive={exhaustive}, grid={grid}"
                    )
                else:
                    assert grid == float("inf")
