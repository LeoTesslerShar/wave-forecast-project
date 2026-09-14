"""Pure geometry helpers -- no I/O, no OSM-specific knowledge. Everything in this file is
unit-testable against hand-computed cases.

Coordinates are always (lat, lon) in degrees, matching Beach.lat/lon. Bearings are compass
degrees [0, 360), measured clockwise from true north -- the same convention Open-Meteo uses
for wave_direction and wind_direction_10m (both "direction the wave/wind is coming FROM").
"""
import math

EARTH_RADIUS_M = 6_371_000.0


def initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing (degrees, [0, 360)) from point 1 to point 2, great-circle."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    theta = math.atan2(x, y)
    return (math.degrees(theta) + 360) % 360


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def angular_difference(a: float, b: float) -> float:
    """Smallest angle between two compass bearings, in [0, 180]."""
    d = abs(a - b) % 360
    return min(d, 360 - d)


def destination_point(lat: float, lon: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    """Point reached travelling `distance_m` from (lat, lon) along `bearing_deg`."""
    delta = distance_m / EARTH_RADIUS_M
    theta = math.radians(bearing_deg)
    phi1, lambda1 = math.radians(lat), math.radians(lon)

    phi2 = math.asin(
        math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    )
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), (math.degrees(lambda2) + 540) % 360 - 180


class LocalProjection:
    """Flat-earth approximation good to well under 1% error over the ~150km extent of the
    Israeli coast (bbox used in scripts/exposure/fetch_coastline.py). Used only for nearest
    -point-on-line and ray/segment proximity checks, never for the bearings themselves
    (those use the great-circle formulas above)."""

    def __init__(self, ref_lat: float):
        self.ref_lat = ref_lat
        self._cos_ref = math.cos(math.radians(ref_lat))

    def to_xy(self, lat: float, lon: float) -> tuple[float, float]:
        x = math.radians(lon) * self._cos_ref * EARTH_RADIUS_M
        y = math.radians(lat) * EARTH_RADIUS_M
        return x, y

    def to_latlon(self, x: float, y: float) -> tuple[float, float]:
        lat = math.degrees(y / EARTH_RADIUS_M)
        lon = math.degrees(x / (self._cos_ref * EARTH_RADIUS_M))
        return lat, lon


def closest_point_on_segment(
    p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> tuple[tuple[float, float], float, float]:
    """p, a, b are (x, y) in a local projection. Returns (closest_xy, t, distance) where t
    in [0, 1] is the fraction along a->b."""
    ax, ay = a
    bx, by = b
    px, py = p
    abx, aby = bx - ax, by - ay
    ab_len_sq = abx * abx + aby * aby
    if ab_len_sq == 0:
        return a, 0.0, math.hypot(px - ax, py - ay)
    t = ((px - ax) * abx + (py - ay) * aby) / ab_len_sq
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * abx, ay + t * aby
    return (cx, cy), t, math.hypot(px - cx, py - cy)
