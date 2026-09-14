"""Exposure score: how directly a given swell reaches a given beach, given its shoreline
orientation -- prompts/phase-2-exposure.md section 2.

    exposure = f(angular difference between swell direction and shoreline normal) x (1 - obstruction)

Direction convention (asserted in tests/test_exposure_geometry.py against a known case):
swell_direction, like Open-Meteo's wave_direction and wind_direction_10m, is the compass
bearing the swell is coming FROM (meteorological convention). shoreline_bearing (from
app.exposure.bearing) is the seaward normal -- the bearing you'd face standing on the beach
looking out to sea. A swell arriving FROM that same bearing hits the beach head-on
(exposure = 1). A swell arriving from 90 degrees or more off that bearing runs parallel to
the shore or from behind it and does not reach the break (exposure = 0).
"""
import math
from dataclasses import dataclass

from app.exposure.geo_utils import angular_difference
from app.exposure.obstruction import obstruction_fraction

# Structures within this range of the beach, close enough to the swell-arrival ray, are
# treated as obstructing -- see app/exposure/obstruction.py for the ray-cast itself.
OBSTRUCTION_RANGE_M = 3000.0


@dataclass
class ExposureResult:
    exposure_factor: float          # combined 0..1, what actually scales the wave height
    directional_factor: float       # 0..1, from angle alone, before obstruction
    obstruction: float              # 0..1, fraction of directional exposure removed
    angular_difference_deg: float
    method: str = "cosine_clamped_directional_x_obstruction"


def directional_exposure(swell_direction_from: float, shoreline_bearing: float) -> tuple[float, float]:
    """Cosine of the angle between swell arrival and the shoreline normal, clamped to zero
    beyond +/-90 degrees. Returns (factor, angular_difference_deg)."""
    diff = angular_difference(swell_direction_from, shoreline_bearing)
    if diff >= 90:
        return 0.0, diff
    return math.cos(math.radians(diff)), diff


def compute_exposure(
    lat: float,
    lon: float,
    shoreline_bearing: float | None,
    swell_direction_from: float,
) -> ExposureResult:
    if shoreline_bearing is None:
        # No bearing computed for this beach yet -- degrade to "fully exposed" rather than
        # crash or silently drop the beach; callers must still see method/confidence
        # marking this as unmodelled, not measured (hard rule 1).
        return ExposureResult(
            exposure_factor=1.0,
            directional_factor=1.0,
            obstruction=0.0,
            angular_difference_deg=0.0,
            method="no_shoreline_bearing_available",
        )

    directional, diff = directional_exposure(swell_direction_from, shoreline_bearing)
    obstruction = obstruction_fraction(lat, lon, swell_direction_from, max_range_m=OBSTRUCTION_RANGE_M) if directional > 0 else 0.0
    combined = directional * (1 - obstruction)

    return ExposureResult(
        exposure_factor=round(combined, 3),
        directional_factor=round(directional, 3),
        obstruction=round(obstruction, 3),
        angular_difference_deg=round(diff, 1),
    )
