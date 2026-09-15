"""Builds the actual push payload -- prompts/phase-4-alerting.md section 5. Carries the
same honesty markers the API does (hard rule 1): a range, not a bare decimal; the quality
components; and, when the calibrated threshold is what actually fired, says so explicitly
rather than implying the user's literal bar was met.

User-facing strings (title, calibration_note) are Hebrew -- this is what actually lands in
a push notification (docs/DECISIONS.md, the Hebrew/RTL entry). `operating_effect.
description` (app/alerting/calibration.py) stays English by contrast: it is a more
technical explanation carrying a literal "docs/BIAS_ANALYSIS.md" reference its own tests
check for verbatim, and is embedded rather than the primary sentence the user reads.
"""
from app.alerting.calibration import OperatingPointEffect
from app.alerting.matching import Cluster
from app.models import Beach, Subscription


def build_payload(
    beach: Beach,
    subscription: Subscription,
    cluster: Cluster,
    kind: str,
    operating_effect: OperatingPointEffect | None,
) -> dict:
    best_hour = max(cluster.hours, key=lambda h: h.hour.quality_score).hour
    heights = [h.hour.size.wave_height_estimate for h in cluster.hours if h.hour.size.wave_height_estimate is not None]
    beach_name = beach.name_he or beach.name

    title = {
        "alert": f"{beach_name}: נפתח חלון גלישה",
        "update": f"{beach_name}: החלון עודכן",
        "cancellation": f"{beach_name}: החלון כבר לא מתאים",
    }[kind]

    calibration_note = None
    if (
        kind != "cancellation"
        and operating_effect is not None
        and subscription.min_height is not None
        and min(heights, default=0) < subscription.min_height
    ):
        calibration_note = (
            f"ביקשת מעל {subscription.min_height:.2f} מ'; השעה הנמוכה ביותר בחלון הזה היא "
            f"{min(heights):.2f} מ', הותרעת בזכות הגדרת '{subscription.operating_point}' כי "
            f"{operating_effect.description}"
        )

    return {
        "title": title,
        "beach_id": beach.id,
        "beach_name": beach_name,
        "kind": kind,
        "window_start": cluster.start.isoformat(),
        "window_end": cluster.end.isoformat(),
        "height_range_m": [round(min(heights), 2), round(max(heights), 2)] if heights else None,
        "quality_verdict": best_hour.quality_verdict,
        "quality_score": best_hour.quality_score,
        "quality_components": {
            "size": {
                "estimate_m": best_hour.size.wave_height_estimate,
                "range_m": list(best_hour.size.wave_height_range) if best_hour.size.wave_height_range else None,
                "confidence": best_hour.size.confidence.exposure,
            },
            "period_s": best_hour.period_s,
            "period_band": best_hour.period_band,
            "wind": best_hour.wind.model_dump(),
            "chop_ratio": best_hour.chop_ratio,
            "chop_band": best_hour.chop_band,
        },
        "operating_point": subscription.operating_point,
        "calibration_note": calibration_note,
        "honesty_marker": "הערכת הגודל והציון ברמת החוף הן הערכות לא מאומתות -- ראו שדות confidence",
    }
