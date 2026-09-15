"""Combines a Beach's shoreline_bearing with one Forecast row into the exposure-adjusted
estimate shape from prompts/phase-2-exposure.md section 3. The only place in the codebase
that builds this response shape -- API routes call this, not scoring.py directly, so the
honest-labelling requirement (every field always present) can't be bypassed accidentally.
"""
from app.exposure.scoring import compute_exposure
from app.models import Beach, Forecast
from app.schemas import ExposureComponents, ExposureConfidence, ExposureEstimateOut

# docs/BIAS_ANALYSIS.md: on the healthy DeepLev deployment, 90% of offshore-model errors
# fell within this half-width. Never narrow the displayed range below it -- exposure adds
# uncertainty on top of the offshore forecast, it does not remove the offshore forecast's
# own measured uncertainty.
OFFSHORE_UNCERTAINTY_M = 0.25

# Open-Meteo's wave_height (and everything this module derives from it) is significant wave
# height (Hs) -- the average of the highest third of waves, measured in deep water, the
# oceanographic convention docs/BIAS_ANALYSIS.md was validated against. What Israeli surf
# reports quote is a different thing: the height of the waves actually breaking at the
# beach. This factor converts between them, for DISPLAY ONLY (app/quality/size.py's bands
# stay on Hs).
#
# It is BELOW 1.0, which is the opposite of the textbook surf-forecasting rule of thumb, and
# that is deliberate. The familiar "face height is ~1.3x the deep-water swell" figure
# (Surfline's own published guidance) is stated explicitly for 12-16 SECOND GROUND SWELL,
# where long-period energy shoals up hard as it reaches the bank. Israel's Mediterranean is
# a short-fetch WIND SEA -- our own peak periods run 5-7s. Short-period waves shoal far less,
# and much of the offshore Hs in a wind sea is steep, disorganised chop that never forms a
# rideable face at all, so the local reports land BELOW the deep-water Hs rather than above
# it. Importing the ground-swell rule of thumb to this coast was the mistake behind two
# earlier wrong values here (1.8, then 1.3 -- see docs/DECISIONS.md).
#
# 0.8 is calibrated against GoSurf (gosurf.co.il), an Israeli surfer-facing forecast, over
# its published 7-day Tel Aviv outlook compared hour-for-hour against our own offshore Hs
# for the same days: ratios 0.60, 0.64, 0.70, 0.83, 0.85, 0.90, 1.14 -- median 0.83, mean
# 0.81. Cross-checked against surf-forecast.com, whose Tel Aviv "wave height" (0.5-0.6m at
# 6s for the calibration day) tracks our raw Hs closely rather than GoSurf's 0.3-0.5m,
# which is what pins the gap on the reporting convention rather than on model disagreement.
#
# Still an empirical calibration against one local service, not a measurement: the scatter
# above (0.60-1.14) is wide, and a genuinely period-dependent conversion would be better
# than any single constant if this coast ever gets a real ground-swell day. Same
# judgement-call caveat as OBSTRUCTION_LATERAL_THRESHOLD_M.
SURF_HEIGHT_FACTOR = 0.8


def build_exposure_estimate(beach: Beach, forecast: Forecast) -> ExposureEstimateOut:
    offshore_raw = forecast.wave_height
    swell_direction = forecast.swell_wave_direction or forecast.wave_direction

    if offshore_raw is None or swell_direction is None:
        # Wave data itself is missing this hour (wave_fetch_failed, or a genuinely thin
        # upstream response) -- nothing to adjust. Say so plainly rather than fabricate 0s.
        return ExposureEstimateOut(
            beach_id=beach.id,
            valid_at=forecast.valid_at,
            wave_height_estimate=None,
            wave_height_range=None,
            surf_height_estimate=None,
            surf_height_range=None,
            method="raw_offshore_unavailable",
            components=ExposureComponents(
                offshore_raw=None, exposure_factor=0.0, directional_factor=0.0, obstruction=0.0
            ),
            confidence=ExposureConfidence(offshore_raw="unavailable"),
            exposure_basis="no wave/swell direction data for this hour",
        )

    result = compute_exposure(beach.lat, beach.lon, beach.shoreline_bearing, swell_direction)

    estimate = round(offshore_raw * result.exposure_factor, 2)
    lo = round(max(0.0, estimate - OFFSHORE_UNCERTAINTY_M), 2)
    hi = round(estimate + OFFSHORE_UNCERTAINTY_M, 2)

    surf_estimate = round(estimate * SURF_HEIGHT_FACTOR, 2)
    surf_lo = round(max(0.0, lo * SURF_HEIGHT_FACTOR), 2)
    surf_hi = round(hi * SURF_HEIGHT_FACTOR, 2)

    bearing_str = (
        f"{beach.shoreline_bearing:.0f}deg" if beach.shoreline_bearing is not None else "unknown"
    )
    obstruction_str = (
        f"obstruction detected (-{result.obstruction:.0%})" if result.obstruction > 0 else "no obstruction modelled"
    )
    basis = (
        f"shoreline bearing {bearing_str}, swell from {swell_direction:.0f}deg "
        f"(angular diff {result.angular_difference_deg:.0f}deg), {obstruction_str}"
    )

    return ExposureEstimateOut(
        beach_id=beach.id,
        valid_at=forecast.valid_at,
        wave_height_estimate=estimate,
        wave_height_range=(lo, hi),
        surf_height_estimate=surf_estimate,
        surf_height_range=(surf_lo, surf_hi),
        method="raw_offshore+heuristic_exposure" if beach.shoreline_bearing is not None else result.method,
        components=ExposureComponents(
            offshore_raw=offshore_raw,
            exposure_factor=result.exposure_factor,
            directional_factor=result.directional_factor,
            obstruction=result.obstruction,
        ),
        confidence=ExposureConfidence(),
        exposure_basis=basis,
    )
