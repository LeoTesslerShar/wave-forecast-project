"""The "body reference" / Hawaiian scale -- describing wave height against a standing
surfer (ankle, knee, waist, ...) rather than a metric number. A widely-used surf-community
convention, not this project's invention, but the exact metre boundaries between bands are
a judgement call with no ground truth to fit them against -- same caveat as every other
heuristic constant here (see docs/DECISIONS.md).

Operates on SURF HEIGHT (the displayed breaking-wave number, app/exposure/apply.py
SURF_HEIGHT_FACTOR), not the offshore Hs app/quality/size.py's own bands use -- this is
about what a surfer standing at the beach would call it, the same convention surf_height
itself exists for.
"""
from dataclasses import dataclass

# (upper_bound_m, hebrew_label) pairs, checked in ascending order -- first match wins.
BODY_REFERENCE_BANDS = [
    (0.30, "קרסול"),
    (0.45, "מעל קרסול"),
    (0.60, "ברך"),
    (0.75, "מעל ברך"),
    (0.90, "מותניים"),
    (1.10, "מעל מותניים"),
    (1.40, "חזה"),
    (1.70, "כתפיים"),
    (2.00, "ראש"),
    (float("inf"), "מעל הראש"),
]


@dataclass
class BodyReference:
    label: str  # Hebrew -- see module docstring
    method: str = "unvalidated_heuristic"


def classify_body_reference(surf_height_m: float | None) -> BodyReference:
    if surf_height_m is None:
        return BodyReference(label="אין נתונים")
    for upper, label in BODY_REFERENCE_BANDS:
        if surf_height_m < upper:
            return BodyReference(label=label)
    return BodyReference(label=BODY_REFERENCE_BANDS[-1][1])
