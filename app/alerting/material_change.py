"""Material-change detection -- prompts/phase-4-alerting.md section 3, rule 2. "A forecast
drifting 1.4m -> 1.45m is not news. A 1.4m -> 2.2m upgrade is." Every threshold here is a
named constant, defined once, defended in docs/DECISIONS.md.
"""
from dataclasses import dataclass
from datetime import datetime

# Bigger than the offshore forecast's own measured uncertainty (~0.19-0.25m 90% interval,
# docs/BIAS_ANALYSIS.md) -- a change smaller than the model's own noise floor is not real
# news, it is the model wobbling within its known error band.
HEIGHT_MATERIAL_CHANGE_M = 0.3

# The window's start or end moving by more than this many hours changes when someone would
# actually need to show up -- material regardless of height.
WINDOW_SHIFT_MATERIAL_HOURS = 1.0


@dataclass
class Snapshot:
    """What was actually communicated in an alert -- stored verbatim in
    AlertSent.conditions_snapshot so the NEXT evaluation has real numbers to diff against,
    not a boolean."""

    window_start: datetime
    window_end: datetime
    height_estimate_m: float
    height_range_m: tuple[float, float]
    quality_verdict: str
    quality_score: float
    operating_point: str
    effective_threshold_m: float | None

    def to_dict(self) -> dict:
        return {
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "height_estimate_m": self.height_estimate_m,
            "height_range_m": list(self.height_range_m),
            "quality_verdict": self.quality_verdict,
            "quality_score": self.quality_score,
            "operating_point": self.operating_point,
            "effective_threshold_m": self.effective_threshold_m,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Snapshot":
        return cls(
            window_start=datetime.fromisoformat(d["window_start"]),
            window_end=datetime.fromisoformat(d["window_end"]),
            height_estimate_m=d["height_estimate_m"],
            height_range_m=tuple(d["height_range_m"]),
            quality_verdict=d["quality_verdict"],
            quality_score=d["quality_score"],
            operating_point=d["operating_point"],
            effective_threshold_m=d.get("effective_threshold_m"),
        )


def is_material_change(old: Snapshot, new: Snapshot) -> tuple[bool, str]:
    if old.quality_verdict != new.quality_verdict:
        return True, f"verdict changed from {old.quality_verdict} to {new.quality_verdict}"

    height_delta = abs(old.height_estimate_m - new.height_estimate_m)
    if height_delta >= HEIGHT_MATERIAL_CHANGE_M:
        return True, f"height estimate changed by {height_delta:.2f}m"

    start_shift = abs((old.window_start - new.window_start).total_seconds()) / 3600
    if start_shift >= WINDOW_SHIFT_MATERIAL_HOURS:
        return True, f"window start shifted by {start_shift:.1f}h"

    end_shift = abs((old.window_end - new.window_end).total_seconds()) / 3600
    if end_shift >= WINDOW_SHIFT_MATERIAL_HOURS:
        return True, f"window end shifted by {end_shift:.1f}h"

    return False, ""
