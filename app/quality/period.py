"""Wave period scoring -- prompts/phase-3-quality.md section 2.

These bands are written for PEAK period (Tp), not mean period (Tm) -- the caller
(app/quality/apply.py) is responsible for passing the right one, and flags it when it has
to substitute. Getting that wrong is not a rounding difference: Tm runs ~20-25% below Tp,
which is enough to push most days a whole band down.

Thresholds are for the Eastern Mediterranean's short-fetch wind-swell character, not
imported from a long-fetch ocean coast (the prompt's explicit warning), so 8s+ here is
deliberately a lower bar than a Californian or Australian site would use. This is a
judgement call, not a measured threshold.

The bands are 2s wide because forecast period error is of that order and finer bands would
claim resolution the forecast does not have. Note this is NOT backed by a local
measurement: an earlier version of this docstring cited "~0.97s MAE against DeepLev
(docs/BIAS_ANALYSIS.md)", but that analysis validated wave HEIGHT only and contains no
period comparison at all -- the figure appears to have been a misreading of its 0.973
height correlation. PERIOD_UNCERTAINTY_S below is therefore an assumption, not a result;
treat it as unvalidated until someone actually measures it. See docs/DECISIONS.md.
"""
from dataclasses import dataclass

WEAK_PERIOD_S = 6.0
GOOD_PERIOD_S = 8.0

PERIOD_UNCERTAINTY_S = 1.0  # assumed, NOT measured here -- see the module docstring


@dataclass
class PeriodQuality:
    band: str  # "weak" | "workable" | "good"
    score: float  # 0..1


def classify_period(period_s: float | None) -> PeriodQuality:
    if period_s is None:
        return PeriodQuality(band="unknown", score=0.5)
    if period_s < WEAK_PERIOD_S:
        return PeriodQuality(band="weak", score=0.3)
    if period_s < GOOD_PERIOD_S:
        return PeriodQuality(band="workable", score=0.7)
    return PeriodQuality(band="good", score=1.0)
