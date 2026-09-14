"""Wave period scoring -- prompts/phase-3-quality.md section 2.

Thresholds for the Eastern Mediterranean's short-fetch wind-swell character, not imported
from a long-fetch ocean coast (the prompt's explicit warning). docs/BIAS_ANALYSIS.md's own
DeepLev data showed peak periods clustering well under what a Pacific groundswell coast
would call "good" -- see the deployment-9 median Tp context in that document -- so 8s+ here
is deliberately a lower bar than a Californian or Australian site would use, and is a
judgement call, not a measured threshold. Model period error was ~0.97s MAE against DeepLev
(docs/BIAS_ANALYSIS.md), which is why these bands are 2s wide -- narrower bands would be
finer than the forecast can actually resolve.
"""
from dataclasses import dataclass

WEAK_PERIOD_S = 6.0
GOOD_PERIOD_S = 8.0

PERIOD_UNCERTAINTY_S = 1.0  # docs/BIAS_ANALYSIS.md: ~0.97s MAE against DeepLev, rounded


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
