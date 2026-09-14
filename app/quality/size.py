"""Size banding -- reuses the exact regime boundaries docs/BIAS_ANALYSIS.md used for its
own MAE-by-regime breakdown (0, 0.5, 1.0, 1.5, 2.5m), so "rideable" here means the same
thing it meant in that analysis. Operates on the Phase 2 exposure-adjusted estimate, not
the raw offshore height.
"""
from dataclasses import dataclass

# docs/BIAS_ANALYSIS.md height regime boundaries.
FLAT_MAX_M = 0.3  # below this, not worth paddling out for -- narrower than BIAS_ANALYSIS's
# own "flat <0.5" bucket because that bucket's own data (median ~0.3m within it) showed
# most of it is genuinely marginal, not flat; 0.3m is this project's own judgement call.
SMALL_MAX_M = 0.5
RIDEABLE_MAX_M = 1.0
GOOD_MAX_M = 1.5
BIG_MAX_M = 2.5


@dataclass
class SizeQuality:
    band: str  # "flat" | "small" | "rideable" | "good" | "big"
    score: float  # 0..1


def classify_size(estimate_m: float | None) -> SizeQuality:
    if estimate_m is None:
        return SizeQuality(band="unknown", score=0.0)
    if estimate_m < FLAT_MAX_M:
        return SizeQuality(band="flat", score=0.0)
    if estimate_m < SMALL_MAX_M:
        return SizeQuality(band="small", score=0.4)
    if estimate_m < RIDEABLE_MAX_M:
        return SizeQuality(band="rideable", score=0.75)
    if estimate_m < GOOD_MAX_M:
        return SizeQuality(band="good", score=1.0)
    if estimate_m < BIG_MAX_M:
        return SizeQuality(band="big", score=1.0)
    return SizeQuality(band="big", score=0.85)  # past 2.5m: demanding, slight reduction, judgement call
