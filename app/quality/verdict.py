"""Combines size/period/wind/chop into one verdict -- prompts/phase-3-quality.md section 3.

Deliberately NOT a fitted model: there is no training data (hard rule 1 -- an opaque score
would be a heuristic wearing false precision). It is a weighted sum for fine-grained
ranking, capped by a small set of explicit rules that encode real surf knowledge a pure
weighted sum would miss (e.g. a huge, long-period, onshore-blown day is not "excellent" no
matter how the arithmetic comes out). Every number here is a judgement call, documented as
one -- see docs/DECISIONS.md for the reasoning behind the specific weights and caps.

Wind is weighted highest (0.4) because the phase prompt identifies it as "the decisive
quality factor," and because it is the component that can turn a good swell into an
unrideable one (onshore chop) -- unlike size or period, which degrade quality gradually.
"""
from dataclasses import dataclass

from app.quality.chop import ChopQuality
from app.quality.period import PeriodQuality
from app.quality.size import SizeQuality
from app.quality.wind import WindQuality

WIND_WEIGHT = 0.40
SIZE_WEIGHT = 0.25
CHOP_WEIGHT = 0.25
PERIOD_WEIGHT = 0.10

LADDER = ["flat", "poor", "fair", "good", "excellent"]

# Score -> ladder position. Judgement calls.
SCORE_THRESHOLDS = [
    (0.80, "excellent"),
    (0.60, "good"),
    (0.40, "fair"),
    (0.0, "poor"),
]


@dataclass
class Verdict:
    quality_score: float  # 0..1, the underlying weighted sum -- for ranking, not display
    verdict: str
    reasoning: str


def _score_to_ladder(score: float) -> str:
    for threshold, label in SCORE_THRESHOLDS:
        if score >= threshold:
            return label
    return "poor"


def _cap(verdict: str, max_label: str) -> str:
    if LADDER.index(verdict) > LADDER.index(max_label):
        return max_label
    return verdict


def combine(size: SizeQuality, period: PeriodQuality, wind: WindQuality, chop: ChopQuality) -> Verdict:
    if size.band == "flat":
        return Verdict(quality_score=0.0, verdict="flat", reasoning="not enough size to surf")

    quality_score = round(
        wind.score * WIND_WEIGHT
        + size.score * SIZE_WEIGHT
        + chop.score * CHOP_WEIGHT
        + period.score * PERIOD_WEIGHT,
        3,
    )
    verdict = _score_to_ladder(quality_score)

    capped_by: list[str] = []
    if wind.relation_to_shore == "onshore":
        new_verdict = _cap(verdict, "fair")
        if new_verdict != verdict:
            capped_by.append("onshore wind")
        verdict = new_verdict
    if chop.band == "choppy":
        new_verdict = _cap(verdict, "fair")
        if new_verdict != verdict:
            capped_by.append("wind-chop")
        verdict = new_verdict

    reasoning = _build_reasoning(size, period, wind, chop, capped_by)
    return Verdict(quality_score=quality_score, verdict=verdict, reasoning=reasoning)


def _build_reasoning(
    size: SizeQuality, period: PeriodQuality, wind: WindQuality, chop: ChopQuality, capped_by: list[str]
) -> str:
    parts = []

    if wind.relation_to_shore == "glassy":
        parts.append("glassy" + (" but gusty" if wind.gusty else ""))
    elif wind.relation_to_shore == "offshore":
        parts.append("clean offshore wind" + (", though gusty" if wind.gusty else ""))
    elif wind.relation_to_shore == "onshore":
        parts.append("onshore wind chopping up the face" + (", gusty too" if wind.gusty else ""))
    elif wind.relation_to_shore == "cross-shore":
        parts.append("cross-shore wind" + (", gusty" if wind.gusty else ""))
    else:
        parts.append("wind direction unavailable")

    parts.append(f"{chop.band} chop" if chop.band != "unknown" else "chop ratio unavailable")
    parts.append(f"{period.band} period" if period.band != "unknown" else "period unavailable")
    parts.append(f"{size.band} size")

    reasoning = ", ".join(parts)
    if capped_by:
        reasoning += f" (capped by {' and '.join(capped_by)})"
    return reasoning
