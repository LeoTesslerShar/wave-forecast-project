"""Combines size/period/wind/chop into one verdict -- prompts/phase-3-quality.md section 3.

Deliberately NOT a fitted model: there is no training data (hard rule 1 -- an opaque score
would be a heuristic wearing false precision). It is a weighted sum for fine-grained
ranking, capped by a small set of explicit rules that encode real surf knowledge a pure
weighted sum would miss. Every number here is a judgement call, documented as one -- see
docs/DECISIONS.md for the reasoning behind the specific weights and caps.

Wind is weighted highest (0.4) because the phase prompt identifies it as "the decisive
quality factor," and because it is the component that can turn a good swell into an
unrideable one (onshore chop) -- unlike size or period, which degrade quality gradually.

Scale is 0..10, not 0..1 -- meant to be READ, not just compared (see quality_score's own
docstring on Verdict). Two hard ceilings are applied to the numeric score BEFORE the ladder,
not just to the verdict word (docs/DECISIONS.md, "a 0.5m day scored excellent" bug):

  - SIZE_CEILING, keyed on the displayed SURF HEIGHT (not Hs): a small day cannot read as a
    top score no matter how clean the wind/period/chop are. A ceiling on the *word* alone
    (the pre-existing _cap mechanism below) is not enough, because ranking, alert clustering
    and best-hour selection all sort on the raw quality_score number, not the word -- a
    ceiling that only relabelled "excellent" as "fair" while leaving the number at 9.4 would
    still let a flat day win a ranking or an alert.
  - WIND_CEILING, keyed on relation_to_shore + raw speed: strong onshore/cross-shore wind
    caps hard (it wrecks the wave face), strong offshore is left mostly alone (it grooms the
    face and only becomes a problem once very strong). WindQuality.score itself does not
    vary with speed at all above LIGHT_WIND_KMH (app/quality/wind.py) -- a 60 km/h dead-
    offshore gale would otherwise score identically to a 9 km/h breeze.

Both ceiling tables are judgement calls with no ground truth to fit them against, same
caveat as every other heuristic constant in this project -- see docs/DECISIONS.md.
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

# Score -> ladder position, on the 0..10 scale. Judgement calls.
SCORE_THRESHOLDS = [
    (8.0, "excellent"),
    (6.0, "good"),
    (4.0, "fair"),
    (0.0, "poor"),
]

# Maximum quality_score (0..10) a given SURF HEIGHT (metres, the displayed breaking-wave
# number -- app/exposure/apply.py SURF_HEIGHT_FACTOR, NOT the offshore Hs classify_size
# still uses for its own bands) can reach, regardless of how clean everything else is.
# (upper_bound_m, ceiling) pairs, checked in order -- first match wins.
SIZE_CEILING = [
    (0.5, 2.0),
    (0.8, 4.0),
    (1.2, 7.0),
    (2.0, 10.0),
    (float("inf"), 8.0),  # past 2m: big enough to be demanding/messy on this coast, not a 10
]

# Maximum quality_score (0..10) a given wind speed (km/h) + relation_to_shore can reach.
# Onshore/cross-shore wind blows straight into the wave face and is capped hard; offshore
# wind grooms the face and is left alone until it gets strong enough to hold waves up too
# much to ride cleanly. Glassy (<LIGHT_WIND_KMH) is never capped here.
# (upper_bound_kmh, ceiling) pairs, checked in ascending order -- first match wins.
WIND_CEILING_ONSHORE = [(12.0, 10.0), (20.0, 6.0), (30.0, 4.0), (float("inf"), 2.0)]
WIND_CEILING_OFFSHORE = [(35.0, 10.0), (float("inf"), 6.0)]
GUSTY_CEILING_PENALTY = 2.0  # further points subtracted from whichever ceiling applied


@dataclass
class Verdict:
    quality_score: float  # 0..10 -- ranking AND display use this directly
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


def _size_ceiling(surf_height_m: float | None) -> float:
    if surf_height_m is None:
        return 10.0  # no surf-height data -- don't invent a penalty for a missing number
    for upper, ceiling in SIZE_CEILING:
        if surf_height_m < upper:
            return ceiling
    return SIZE_CEILING[-1][1]


def _wind_ceiling(wind: WindQuality) -> float:
    if wind.speed_kmh is None or wind.relation_to_shore == "glassy":
        return 10.0
    table = WIND_CEILING_OFFSHORE if wind.relation_to_shore == "offshore" else WIND_CEILING_ONSHORE
    ceiling = 10.0
    for upper, c in table:
        if wind.speed_kmh < upper:
            ceiling = c
            break
    if wind.gusty and ceiling < 10.0:
        ceiling = max(0.0, ceiling - GUSTY_CEILING_PENALTY)
    return ceiling


def combine(
    size: SizeQuality,
    period: PeriodQuality,
    wind: WindQuality,
    chop: ChopQuality,
    *,
    surf_height_m: float | None = None,
) -> Verdict:
    if size.band == "flat":
        return Verdict(quality_score=0.0, verdict="flat", reasoning="אין מספיק גובה לגלוש")

    weighted = (
        wind.score * WIND_WEIGHT
        + size.score * SIZE_WEIGHT
        + chop.score * CHOP_WEIGHT
        + period.score * PERIOD_WEIGHT
    )
    quality_score = round(weighted * 10, 1)

    size_ceiling = _size_ceiling(surf_height_m)
    wind_ceiling = _wind_ceiling(wind)
    ceiling_reasons = []
    if size_ceiling < quality_score:
        ceiling_reasons.append("גודל קטן מדי")
    if wind_ceiling < quality_score:
        ceiling_reasons.append("רוח חזקה מדי")
    # A ceiling clamp can legitimately drive this to 0.0 (e.g. a gusty gale-force onshore
    # blow) -- that is NOT the same case as the size.band == "flat" early return above, and
    # must not short-circuit to a generic message: _score_to_ladder's own (0.0, "poor")
    # threshold already handles it, and the real wind/chop/period reasoning below is more
    # useful than a canned sentence ("gusty onshore gale" tells you why; "not enough size or
    # too much wind" does not).
    quality_score = max(0.0, round(min(quality_score, size_ceiling, wind_ceiling), 1))
    verdict = _score_to_ladder(quality_score)

    capped_by: list[str] = list(ceiling_reasons)
    if wind.relation_to_shore == "onshore":
        new_verdict = _cap(verdict, "fair")
        if new_verdict != verdict:
            capped_by.append("רוח חופית")
        verdict = new_verdict
    if chop.band == "choppy":
        new_verdict = _cap(verdict, "fair")
        if new_verdict != verdict:
            capped_by.append("גלישה סחופה")
        verdict = new_verdict

    reasoning = _build_reasoning(size, period, wind, chop, capped_by)
    return Verdict(quality_score=quality_score, verdict=verdict, reasoning=reasoning)


_CHOP_HE = {"clean": "נקייה", "mixed": "מעורבת", "choppy": "סחופה"}
_PERIOD_HE = {"weak": "חלש", "workable": "סביר", "good": "טוב"}
_SIZE_HE = {"flat": "שטוח", "small": "קטן", "rideable": "בינוני", "good": "טוב", "big": "גדול"}


def _build_reasoning(
    size: SizeQuality, period: PeriodQuality, wind: WindQuality, chop: ChopQuality, capped_by: list[str]
) -> str:
    """Generated in Hebrew -- this sentence is read directly by the user (in the UI and in
    push notifications), unlike the band/verdict IDENTIFIERS it's built from (size.band,
    chop.band, wind.relation_to_shore etc.), which stay English because tests and other
    code depend on their exact values. See docs/DECISIONS.md, the Hebrew/RTL entry."""
    parts = []

    if wind.relation_to_shore == "glassy":
        parts.append("חלק" + (" אך סוער" if wind.gusty else ""))
    elif wind.relation_to_shore == "offshore":
        parts.append("רוח אופשור נקייה" + (", אך סוער" if wind.gusty else ""))
    elif wind.relation_to_shore == "onshore":
        parts.append("רוח חופית מקלקלת את פני הגל" + (", וגם סוער" if wind.gusty else ""))
    elif wind.relation_to_shore == "cross-shore":
        parts.append("רוח צידית" + (", סוער" if wind.gusty else ""))
    else:
        parts.append("כיוון רוח לא ידוע")

    parts.append(f"גלישה {_CHOP_HE[chop.band]}" if chop.band in _CHOP_HE else "יחס גלישה לא ידוע")
    parts.append(f"מחזור {_PERIOD_HE[period.band]}" if period.band in _PERIOD_HE else "מחזור לא ידוע")
    parts.append(f"גודל {_SIZE_HE.get(size.band, size.band)}")

    reasoning = ", ".join(parts)
    if capped_by:
        reasoning += f" (מוגבל בגלל {' ו-'.join(capped_by)})"
    return reasoning
