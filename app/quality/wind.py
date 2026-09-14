"""Wind relation to shore -- prompts/phase-3-quality.md section 2, "the decisive quality
factor."

Convention: wind_direction_10m, like swell direction, is where the wind is coming FROM
(Open-Meteo, matches app/exposure/scoring.py's swell convention). shoreline_bearing is the
seaward normal -- the bearing you'd face standing on the beach looking out to sea.

  wind FROM the shoreline_bearing itself  -> wind blowing IN from the sea    -> ONSHORE (bad)
  wind FROM the opposite bearing (+180)   -> wind blowing OUT toward the sea -> OFFSHORE (good)
  wind FROM 90 degrees off either way     -> CROSS-SHORE (neutral)

This is the mirror image of the swell convention in app/exposure/scoring.py, where angular
difference near 0 is head-on (best). For wind, angular difference near 0 is onshore
(worst) and near 180 is offshore (best) -- opposite meanings for the same geometry, because
swell you want arriving square to the beach, wind you want blowing away from it.
"""
import math
from dataclasses import dataclass

from app.exposure.geo_utils import angular_difference

# Below this speed, direction barely matters at these swell sizes -- glassy regardless.
# Judgement call, not measured (docs/DECISIONS.md).
LIGHT_WIND_KMH = 8.0

# Gusts this far above the mean signal an unstable, bumpy session even when the average
# direction looks clean. Judgement call.
GUST_SPREAD_KMH = 15.0
GUST_PENALTY = 0.8  # multiplicative penalty on the wind score when gusty

# Angular buckets for the relation_to_shore label. 45/135 splits the 0-180 range into three
# equal bands centred on onshore (0), cross-shore (90), offshore (180).
ONSHORE_MAX_DIFF = 45.0
OFFSHORE_MIN_DIFF = 135.0


@dataclass
class WindQuality:
    relation_to_shore: str  # "onshore" | "cross-shore" | "offshore" | "glassy"
    score: float            # 0..1, what the verdict combiner actually uses
    gusty: bool
    angular_difference_deg: float | None


def classify_wind(
    wind_speed_kmh: float | None,
    wind_direction_from: float | None,
    wind_gusts_kmh: float | None,
    shoreline_bearing: float | None,
) -> WindQuality:
    if wind_speed_kmh is None or wind_direction_from is None:
        return WindQuality(relation_to_shore="unknown", score=0.5, gusty=False, angular_difference_deg=None)

    gusty = wind_gusts_kmh is not None and (wind_gusts_kmh - wind_speed_kmh) >= GUST_SPREAD_KMH

    if wind_speed_kmh < LIGHT_WIND_KMH:
        score = 0.95
        if gusty:
            score *= GUST_PENALTY
        return WindQuality(relation_to_shore="glassy", score=round(score, 3), gusty=gusty, angular_difference_deg=None)

    if shoreline_bearing is None:
        # No geometry to judge relation-to-shore against -- degrade to neutral, not a crash.
        return WindQuality(relation_to_shore="unknown", score=0.5, gusty=gusty, angular_difference_deg=None)

    diff = angular_difference(wind_direction_from, shoreline_bearing)
    if diff <= ONSHORE_MAX_DIFF:
        relation = "onshore"
    elif diff >= OFFSHORE_MIN_DIFF:
        relation = "offshore"
    else:
        relation = "cross-shore"

    # grooming in [-1, 1]: +1 = dead offshore (best), -1 = dead onshore (worst).
    grooming = -math.cos(math.radians(diff))
    score = (grooming + 1) / 2  # -> [0, 1]
    if gusty:
        score *= GUST_PENALTY

    return WindQuality(
        relation_to_shore=relation, score=round(score, 3), gusty=gusty, angular_difference_deg=round(diff, 1)
    )
