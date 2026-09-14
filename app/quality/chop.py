"""Chop ratio -- prompts/phase-3-quality.md section 2. Free: swell_wave_height and
wind_wave_height are already ingested (Phase 1) and unused until now.

Low ratio = clean groundswell face even at modest size. High ratio = wind-driven slop even
at a "good" total height -- this probably separates good/bad days better than total height
alone, since it's the one component directly measuring wave ORGANISATION rather than size.
"""
from dataclasses import dataclass

# Judgement calls, no ground truth to tune against (docs/DECISIONS.md).
CLEAN_MAX_RATIO = 0.3
CHOPPY_MIN_RATIO = 0.6


@dataclass
class ChopQuality:
    ratio: float | None
    band: str  # "clean" | "mixed" | "choppy"
    score: float  # 0..1


def classify_chop(swell_wave_height: float | None, wind_wave_height: float | None) -> ChopQuality:
    if swell_wave_height is None or wind_wave_height is None:
        return ChopQuality(ratio=None, band="unknown", score=0.5)

    total = swell_wave_height + wind_wave_height
    if total <= 0:
        # No energy at all -- there's no chop because there's no wave, not because it's clean.
        return ChopQuality(ratio=0.0, band="unknown", score=0.5)

    ratio = round(wind_wave_height / total, 3)
    score = round(max(0.0, 1 - ratio), 3)

    if ratio <= CLEAN_MAX_RATIO:
        band = "clean"
    elif ratio < CHOPPY_MIN_RATIO:
        band = "mixed"
    else:
        band = "choppy"

    return ChopQuality(ratio=ratio, band=band, score=score)
