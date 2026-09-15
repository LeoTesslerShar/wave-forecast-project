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
  - the reduction is scaled by how directly the ray passes the structure, but that scaling
    is linear in distance for want of anything better -- it is not a modelled shadow.

The reduction is GRADED, not binary: a ray passing straight over a breakwater
(lateral ~0 m) gets the full OBSTRUCTION_STRENGTH, one grazing past at nearly
OBSTRUCTION_LATERAL_THRESHOLD_M gets almost nothing. This replaced an earlier flat
all-or-nothing penalty that made the whole exposure model discontinuous: Herzliya went
from a full 40% reduction at a 295 degree swell to zero at 296 degrees, a 1-degree flip,
purely because its coordinate sits ~93 m from the marina breakwater and the ray's closest
approach crossed the 150 m threshold there. tests/test_exposure_geometry.py's own
Bat-Yam-vs-Herzliya known-truth case sits only 4 degrees off that cliff, and a real
forecast (swell from 293 degrees) landed on the wrong side of it, reporting Herzliya ~40%
smaller than Palmachim despite a HIGHER offshore height. See docs/DECISIONS.md.

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
OBSTRUCTION_STRENGTH = 0.4  # MAXIMUM reduction, applied when the ray passes straight over
# a structure; scaled linearly down to 0 at OBSTRUCTION_LATERAL_THRESHOLD_M (see docstring)

# A structure within this distance of the beach coordinate ITSELF is almost always
# something immediately alongside the access point -- a small jetty at the entrance, a
# marina wall, a slipway -- not a true offshore shadow-caster, and is excluded from
# obstruction checks ENTIRELY (see _excluded_structure_indices), not just skipped for the
# first few ray samples. Found via the Bat Yam vs Herzliya acceptance test: Herzliya's
# marina breakwater sits ~93m from the seeded coordinate, which without this exclusion made
# obstruction fire for 5 of 5 tested swell directions instead of tracking direction at all.
#
# The first version of this fix only skipped ray SAMPLES within this distance of the beach,
# not the structure itself -- which meant a large/close structure (e.g. an area=yes
# breakwater polygon with a long footprint) could still register a hit from a LATER sample
# further along the ray, because that sample happened to still be close to the SAME nearby
# structure. Found via a user report: Tel Aviv (Hilton) showed a 25% obstruction from a
# breakwater only 13m from its own beach coordinate -- clearly local infrastructure, not an
# offshore shadow, but the sample-only floor let it through because the hit landed at the
# ray's first post-floor sample (300m out), which was still only ~134m lateral from that
# same 180m-long structure. Excluding the whole structure whenever ANY part of it is closer
# than this distance to the beach fixes it without weakening real, further-out obstruction
# (e.g. Netanya's groyne at ~440m, Bat Yam's pier at ~584m, both still detected). See
# docs/DECISIONS.md.
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


SegmentWithSource = tuple[tuple[float, float], tuple[float, float], int]  # (a, b, structure_index)


@lru_cache(maxsize=32)
def _structure_grid(ref_lat: float) -> dict[tuple[int, int], tuple[SegmentWithSource, ...]]:
    """Every structure segment, bucketed into each grid cell its bounding box overlaps, each
    tagged with the index of the structure (line) it came from -- so a query can exclude an
    entire nearby structure, not just the one segment closest to a given sample point (see
    _excluded_structure_indices). Built once per (cached) reference latitude, reused for
    every ray-cast sample against that beach for the life of the process."""
    grid: dict[tuple[int, int], list[SegmentWithSource]] = {}
    for struct_idx, pts in enumerate(_projected_structures(ref_lat)):
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            gx0, gx1 = sorted((int(a[0] // GRID_CELL_M), int(b[0] // GRID_CELL_M)))
            gy0, gy1 = sorted((int(a[1] // GRID_CELL_M), int(b[1] // GRID_CELL_M)))
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    grid.setdefault((gx, gy), []).append((a, b, struct_idx))
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


@lru_cache(maxsize=32)
def _excluded_structure_indices(lat: float, lon: float) -> frozenset[int]:
    """Indices (into _projected_structures) of every structure with any point closer than
    OBSTRUCTION_MIN_CHECK_DISTANCE_M to this exact beach coordinate -- local infrastructure
    at the beach itself, not an offshore shadow-caster (see that constant's docstring).
    Cached on the EXACT (lat, lon), same discipline as _projected_structures: one beach's
    calls all share its own literal coordinate, so this is one exclusion-set computation
    per beach per process with no approximation risk. Deliberately exhaustive (checks all
    ~226 structures against one point) rather than grid-indexed -- this runs once per beach,
    not once per ray sample, so it is not the hot path the grid exists for."""
    proj = LocalProjection(ref_lat=lat)
    bx, by = proj.to_xy(lat, lon)
    excluded = set()
    for struct_idx, pts in enumerate(_projected_structures(lat)):
        for i in range(len(pts) - 1):
            if _distance_point_to_segment(bx, by, pts[i], pts[i + 1]) < OBSTRUCTION_MIN_CHECK_DISTANCE_M:
                excluded.add(struct_idx)
                break
    return frozenset(excluded)


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


def _nearest_structure_within(
    lat: float,
    lon: float,
    proj: LocalProjection,
    threshold_m: float,
    excluded: frozenset[int] = frozenset(),
) -> float:
    """Distance to the nearest NON-EXCLUDED structure, grid-indexed -- only inspects
    segments in the sample's own cell and its 8 neighbours, not all ~226 structure lines.
    Correct given GRID_CELL_M >= threshold_m: any segment within threshold_m of (px, py) has
    at least one point within threshold_m, which places it in the same cell as (px, py) or
    an adjacent one. Returns inf when nothing (non-excluded) is within threshold_m -- the
    result is therefore EXACT whenever it is <= threshold_m, which is the only range the
    caller grades on, but must not be read as a true global nearest distance beyond that
    (use _distance_to_nearest_structure for that, which does not support exclusion)."""
    px, py = proj.to_xy(lat, lon)
    gx, gy = _cell_of(px, py)
    grid = _structure_grid(proj.ref_lat)
    best = float("inf")
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for a, b, struct_idx in grid.get((gx + dx, gy + dy), ()):
                if struct_idx in excluded:
                    continue
                d = _distance_point_to_segment(px, py, a, b)
                if d < best:
                    best = d
    return best if best <= threshold_m else float("inf")


def obstruction_fraction(
    lat: float,
    lon: float,
    swell_direction_from: float,
    *,
    max_range_m: float = OBSTRUCTION_CHECK_RANGE_M,
) -> float:
    """0.0 (clear) up to OBSTRUCTION_STRENGTH (the ray passes straight over a structure),
    scaled linearly by the ray's CLOSEST approach to any structure -- see the module
    docstring for why this is graded rather than all-or-nothing. Returns 0.0 immediately if
    no structures are loaded at all.

    Every sample is checked rather than returning on the first one inside the threshold:
    the grade depends on the closest approach along the whole ray, so an early grazing pass
    must not mask a later direct hit."""
    if not structure_lines():
        return 0.0

    proj = LocalProjection(ref_lat=lat)
    excluded = _excluded_structure_indices(lat, lon)
    steps = max(1, int(max_range_m // OBSTRUCTION_STEP_M))
    start_step = max(1, int(OBSTRUCTION_MIN_CHECK_DISTANCE_M // OBSTRUCTION_STEP_M))
    closest = float("inf")
    for i in range(start_step, steps + 1):
        dist = i * OBSTRUCTION_STEP_M
        sample_lat, sample_lon = destination_point(lat, lon, swell_direction_from, dist)
        d = _nearest_structure_within(sample_lat, sample_lon, proj, OBSTRUCTION_LATERAL_THRESHOLD_M, excluded)
        if d < closest:
            closest = d

    if closest > OBSTRUCTION_LATERAL_THRESHOLD_M:
        return 0.0
    return round(OBSTRUCTION_STRENGTH * (1.0 - closest / OBSTRUCTION_LATERAL_THRESHOLD_M), 3)
