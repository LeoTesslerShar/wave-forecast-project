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
"""
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


def _distance_to_nearest_structure(lat: float, lon: float, proj: LocalProjection) -> float:
    px, py = proj.to_xy(lat, lon)
    best = float("inf")
    for line in structure_lines():
        pts = [proj.to_xy(la, lo) for la, lo in line]
        for i in range(len(pts) - 1):
            ax, ay = pts[i]
            bx, by = pts[i + 1]
            abx, aby = bx - ax, by - ay
            ab_len_sq = abx * abx + aby * aby
            if ab_len_sq == 0:
                d = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            else:
                t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / ab_len_sq))
                cx, cy = ax + t * abx, ay + t * aby
                d = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
            if d < best:
                best = d
    return best


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
        if _distance_to_nearest_structure(sample_lat, sample_lon, proj) <= OBSTRUCTION_LATERAL_THRESHOLD_M:
            return OBSTRUCTION_STRENGTH
    return 0.0
