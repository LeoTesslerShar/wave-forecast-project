"""Computes the shoreline normal (seaward-facing bearing) for a point near the coast, from
OSM coastline geometry -- prompts/phase-2-exposure.md section 1.

Method:
  1. Find the nearest point on the whole coastline (across all OSM ways) to the target.
  2. Take a WINDOW of coastline around that point (default 500 m total, +/-250 m) rather
     than the single nearest segment -- OSM coastline vertices are irregular and one short
     segment can be up to ~40 degrees off the real local orientation (section 1). The
     window is walked in arc-length along the polyline, not by vertex count, so it adapts
     to however densely each way is digitised.
  3. The tangent bearing across that window gives two candidate normals (tangent +/- 90).
  4. Pick whichever candidate points more nearly WEST. This resolves the land/sea ambiguity
     using a fact specific to this coast, not a general algorithm -- the Israeli
     Mediterranean shoreline runs roughly north-south with the sea to the west, so the
     correct (seaward) normal always has a dominant westward component. Verified as a
     dedicated sanity assertion in tests/test_exposure_geometry.py; would need revisiting
     for a coastline of a different orientation.
"""
import math
from dataclasses import dataclass

from app.exposure.coastline_data import Line, coastline_lines
from app.exposure.geo_utils import LocalProjection, closest_point_on_segment

DEFAULT_WINDOW_M = 500.0
WEST_BEARING = 270.0


@dataclass
class BearingResult:
    bearing_deg: float          # the seaward shoreline normal -- what we actually want
    tangent_bearing_deg: float  # the shoreline's own local direction, for debugging
    distance_to_coast_m: float
    window_points_used: int
    # The longest single unsubdivided OSM segment contributing to the window, in metres.
    # NOT a data-quality signal by itself -- a long straight segment can be a deliberate,
    # accurate digitisation of a genuinely straight stretch of coast (verified against two
    # real cases via OSM's own edit history, docs/DECISIONS.md), and often gives a MORE
    # stable tangent than several short jittery vertices would. What it does mean: any real
    # curvature *within* that span is invisible to this method, since OSM recorded none.
    max_segment_span_m: float
    method: str = "osm_coastline_window_tangent"


def _line_xy(line: Line, proj: LocalProjection) -> list[tuple[float, float]]:
    return [proj.to_xy(lat, lon) for lat, lon in line]


def _nearest_on_polyline(
    target_xy: tuple[float, float], pts_xy: list[tuple[float, float]]
) -> tuple[int, float, tuple[float, float], float] | None:
    if len(pts_xy) < 2:
        return None
    best = None
    for i in range(len(pts_xy) - 1):
        closest_xy, t, dist = closest_point_on_segment(target_xy, pts_xy[i], pts_xy[i + 1])
        if best is None or dist < best[3]:
            best = (i, t, closest_xy, dist)
    return best


def _windowed_tangent(
    pts_xy: list[tuple[float, float]], seg_idx: int, t: float, closest_xy: tuple[float, float], window_m: float
) -> tuple[float, int, float]:
    half = window_m / 2
    max_span = 0.0

    # Walk backward from the closest point, accumulating distance until half-window or the
    # start of the line.
    back_point = closest_xy
    remaining = half
    i = seg_idx
    n_back = 0
    cur = closest_xy
    while remaining > 0 and i >= 0:
        seg_start = pts_xy[i]
        d = math.hypot(cur[0] - seg_start[0], cur[1] - seg_start[1])
        if d >= remaining:
            frac = remaining / d if d > 0 else 0
            back_point = (cur[0] + (seg_start[0] - cur[0]) * frac, cur[1] + (seg_start[1] - cur[1]) * frac)
            # Report the segment's REAL length (d), not just the portion of it the window
            # budget covered -- a 3km segment truncated at 250m is still a 3km segment;
            # capping this at the budget would understate how far the "no curvature
            # visible here" caveat actually extends.
            max_span = max(max_span, d)
            remaining = 0
            break
        remaining -= d
        max_span = max(max_span, d)
        cur = seg_start
        back_point = cur
        i -= 1
        n_back += 1

    # Walk forward similarly.
    fwd_point = closest_xy
    remaining = half
    i = seg_idx + 1
    n_fwd = 0
    cur = closest_xy
    while remaining > 0 and i < len(pts_xy):
        seg_end = pts_xy[i]
        d = math.hypot(seg_end[0] - cur[0], seg_end[1] - cur[1])
        if d >= remaining:
            frac = remaining / d if d > 0 else 0
            fwd_point = (cur[0] + (seg_end[0] - cur[0]) * frac, cur[1] + (seg_end[1] - cur[1]) * frac)
            max_span = max(max_span, d)  # real segment length, not just the budget used
            remaining = 0
            break
        remaining -= d
        max_span = max(max_span, d)
        cur = seg_end
        fwd_point = cur
        i += 1
        n_fwd += 1

    dx, dy = fwd_point[0] - back_point[0], fwd_point[1] - back_point[1]
    if dx == 0 and dy == 0:
        # Degenerate (window collapsed to a point, e.g. a very short isolated way) --
        # fall back to the immediate segment direction.
        dx, dy = pts_xy[min(seg_idx + 1, len(pts_xy) - 1)][0] - pts_xy[seg_idx][0], \
                  pts_xy[min(seg_idx + 1, len(pts_xy) - 1)][1] - pts_xy[seg_idx][1]
    tangent_bearing = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    return tangent_bearing, n_back + n_fwd + 1, max_span


def compute_shoreline_bearing(
    lat: float, lon: float, *, window_m: float = DEFAULT_WINDOW_M, lines: tuple[Line, ...] | None = None
) -> BearingResult:
    lines = lines if lines is not None else coastline_lines()
    proj = LocalProjection(ref_lat=lat)
    target_xy = proj.to_xy(lat, lon)

    best = None  # (dist, line_idx, seg_idx, t, closest_xy, pts_xy)
    for line in lines:
        pts_xy = _line_xy(line, proj)
        found = _nearest_on_polyline(target_xy, pts_xy)
        if found is None:
            continue
        seg_idx, t, closest_xy, dist = found
        if best is None or dist < best[0]:
            best = (dist, seg_idx, t, closest_xy, pts_xy)

    if best is None:
        raise ValueError("no coastline geometry loaded -- check scripts/exposure/coastline.geojson")

    dist, seg_idx, t, closest_xy, pts_xy = best
    tangent_bearing, n_points, max_span = _windowed_tangent(pts_xy, seg_idx, t, closest_xy, window_m)

    normal_a = (tangent_bearing + 90) % 360
    normal_b = (tangent_bearing - 90) % 360
    seaward = normal_a if _west_score(normal_a) < _west_score(normal_b) else normal_b

    return BearingResult(
        bearing_deg=round(seaward, 1),
        tangent_bearing_deg=round(tangent_bearing, 1),
        distance_to_coast_m=round(dist, 1),
        window_points_used=n_points,
        max_segment_span_m=round(max_span, 1),
    )


def _west_score(bearing: float) -> float:
    """How far this bearing is from due west -- smaller is more westward."""
    d = abs(bearing - WEST_BEARING) % 360
    return min(d, 360 - d)
