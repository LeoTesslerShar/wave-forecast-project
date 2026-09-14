"""Obstruction from breakwaters, piers and groynes between a beach and the direction a
swell is arriving from -- prompts/phase-2-exposure.md section 2.

Method: cast a ray from the beach toward the bearing the swell is coming FROM (the same
convention as scoring.py), sample it every OBSTRUCTION_STEP_M, and check each sample's
distance to the nearest OSM breakwater/pier/groyne. If any sample within
OBSTRUCTION_CHECK_RANGE_M comes within OBSTRUCTION_LATERAL_THRESHOLD_M of a structure, that
swell direction is treated as partly blocked for this beach.

This is a deliberately coarse heuristic, not a real diffraction/shadowing model:
  - it does not account for structure height, submersion, or the swell's actual angular
    width;
  - the check range (1500 m) and lateral threshold (150 m) are judgment calls with no
    ground truth to tune them against -- see docs/DECISIONS.md;
  - a hit reduces exposure by a flat OBSTRUCTION_STRENGTH rather than a modelled amount.

It exists because the planning doc's own example (Bat Yam vs Herzliya) is partly a
directional-exposure effect and partly a real marina/breakwater effect, and ignoring
obstruction entirely would understate the difference for beaches that do sit behind one.

Performance (docs/DECISIONS.md): profiling a single 96-hour /beaches/{id}/quality request
found this the dominant cost of the whole endpoint (~2.4s of ~2.6s) for two compounding
reasons, fixed here in order:
  1. Structure geometry was re-projected to local XY from scratch on every one of ~2,160
     ray-cast samples (5.5M redundant to_xy() calls) -- fixed by _projected_structures(),
     cached per EXACT reference latitude (not rounded -- see its own docstring for why a
     rounded version was caught silently changing a real result).
  2. Even with projection cached, each sample did a linear scan over EVERY point of EVERY
     one of ~226 structure lines to find the nearest one -- an O(all structures) search
     for a query that only ever cares about a 150m radius. Fixed with a uniform grid index
     (_structure_grid()): each structure segment is bucketed into every grid cell its
     bounding box overlaps; a query only inspects the sample's own cell and its 8
     neighbours. Correct as long as GRID_CELL_M >= OBSTRUCTION_LATERAL_THRESHOLD_M -- a
     point within the threshold of ANY segment must then share or neighbour that segment's
     cell, so nothing reachable is ever skipped.
Correctness of the grid vs. the original exhaustive scan is checked directly in
tests/test_exposure_obstruction.py (random sample points, not just the known cases).
"""
from functools import lru_cache

from app.exposure.coastline_data import structure_lines
from app.exposure.geo_utils import LocalProjection, destination_point

OBSTRUCTION_CHECK_RANGE_M = 1500.0
OBSTRUCTION_STEP_M = 100.0
OBSTRUCTION_LATERAL_THRESHOLD_M = 150.0
OBSTRUCTION_STRENGTH = 0.4  # flat reduction applied to directional exposure on a hit

# A structure within this distance of the beach coordinate ITSELF (not a ray sample) is
# almost always something immediately alongside the access point -- a small jetty at the
# entrance, a slipway -- not a true offshore shadow-caster. Without this floor, any beach
# whose (approximate, per data/beaches.yml) coordinate happens to sit within
# OBSTRUCTION_LATERAL_THRESHOLD_M of ANY structure gets flagged as obstructed from nearly
# every swell direction, because the ray's first sample is still that close to the start
# point regardless of bearing. Found via the Bat Yam vs Herzliya acceptance test: Herzliya's
# marina breakwater sits ~93m from the seeded coordinate, which without this floor made
# obstruction fire for 5 of 5 tested swell directions instead of tracking direction at all.
OBSTRUCTION_MIN_CHECK_DISTANCE_M = 300.0

# Must be >= OBSTRUCTION_LATERAL_THRESHOLD_M for the 3x3-neighbourhood grid search below to
# be correct (see module docstring, point 2).
GRID_CELL_M = 200.0


@lru_cache(maxsize=32)
def _projected_structures(ref_lat: float) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Structure line geometry projected to local XY, cached per EXACT reference latitude
    (no rounding/bucketing -- a first attempt at this rounded to 0.1deg and was caught by
    the test suite flipping a near-threshold obstruction result for Herzliya at a 300deg
    swell, false -> true, because the tiny coordinate-frame shift from using a different
    ref_lat for the structures than for the sample point pushed a boundary case across the
    150m threshold. Exact-float caching has no such risk -- every call for one beach shares
    the beach's own literal `lat`, so the cache still collapses to one computation per
    beach per process, with zero behavioural difference from the uncached version."""
    proj = LocalProjection(ref_lat=ref_lat)
    return tuple(tuple(proj.to_xy(la, lo) for la, lo in line) for line in structure_lines())


def _cell_of(x: float, y: float) -> tuple[int, int]:
    return (int(x // GRID_CELL_M), int(y // GRID_CELL_M))


@lru_cache(maxsize=32)
def _structure_grid(
    ref_lat: float,
) -> dict[tuple[int, int], tuple[tuple[tuple[float, float], tuple[float, float]], ...]]:
    """Every structure segment, bucketed into each grid cell its bounding box overlaps.
    Built once per (cached) reference latitude, reused for every ray-cast sample against
    that beach for the life of the process."""
    grid: dict[tuple[int, int], list[tuple[tuple[float, float], tuple[float, float]]]] = {}
    for pts in _projected_structures(ref_lat):
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            gx0, gx1 = sorted((int(a[0] // GRID_CELL_M), int(b[0] // GRID_CELL_M)))
            gy0, gy1 = sorted((int(a[1] // GRID_CELL_M), int(b[1] // GRID_CELL_M)))
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    grid.setdefault((gx, gy), []).append((a, b))
    return {k: tuple(v) for k, v in grid.items()}


def _distance_point_to_segment(px: float, py: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    abx, aby = bx - ax, by - ay
    ab_len_sq = abx * abx + aby * aby
    if ab_len_sq == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / ab_len_sq))
    cx, cy = ax + t * abx, ay + t * aby
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _distance_to_nearest_structure(lat: float, lon: float, proj: LocalProjection) -> float:
    """Exhaustive scan over every structure segment -- the ground-truth reference this
    module is checked against (tests/test_exposure_obstruction.py), and the fallback if a
    caller needs an exact global minimum rather than a threshold check. Not used in the hot
    path any more; see _within_threshold_of_structure for that."""
    px, py = proj.to_xy(lat, lon)
    best = float("inf")
    for pts in _projected_structures(proj.ref_lat):
        for i in range(len(pts) - 1):
            d = _distance_point_to_segment(px, py, pts[i], pts[i + 1])
            if d < best:
                best = d
    return best


def _within_threshold_of_structure(lat: float, lon: float, proj: LocalProjection, threshold_m: float) -> bool:
    """Grid-indexed threshold check -- only inspects segments in the sample's own cell and
    its 8 neighbours, not all ~226 structure lines. Correct given GRID_CELL_M >=
    threshold_m: any segment within threshold_m of (px, py) has at least one point within
    threshold_m, which places it in the same cell as (px, py) or an adjacent one."""
    px, py = proj.to_xy(lat, lon)
    gx, gy = _cell_of(px, py)
    grid = _structure_grid(proj.ref_lat)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for a, b in grid.get((gx + dx, gy + dy), ()):
                if _distance_point_to_segment(px, py, a, b) <= threshold_m:
                    return True
    return False


def obstruction_fraction(
    lat: float,
    lon: float,
    swell_direction_from: float,
    *,
    max_range_m: float = OBSTRUCTION_CHECK_RANGE_M,
) -> float:
    """0.0 (clear) or OBSTRUCTION_STRENGTH (a structure sits in the swell's path) -- not a
    continuous value, since the underlying check is a proximity threshold, not a measured
    shadow angle. Returns 0.0 immediately if no structures are loaded at all."""
    if not structure_lines():
        return 0.0

    proj = LocalProjection(ref_lat=lat)
    steps = max(1, int(max_range_m // OBSTRUCTION_STEP_M))
    start_step = max(1, int(OBSTRUCTION_MIN_CHECK_DISTANCE_M // OBSTRUCTION_STEP_M))
    for i in range(start_step, steps + 1):
        dist = i * OBSTRUCTION_STEP_M
        sample_lat, sample_lon = destination_point(lat, lon, swell_direction_from, dist)
        if _within_threshold_of_structure(sample_lat, sample_lon, proj, OBSTRUCTION_LATERAL_THRESHOLD_M):
            return OBSTRUCTION_STRENGTH
    return 0.0
