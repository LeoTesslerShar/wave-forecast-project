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
# Five bands, per the user's own preferred set (ankle/knee/waist/shoulder/head) rather than
# the finer 10-band "above X" scale this started with -- simpler is what was asked for.
BODY_REFERENCE_BANDS = [
    (0.40, "קרסול"),
    (0.70, "ברך"),
    (1.10, "מותן"),
    (1.60, "כתף"),
    (float("inf"), "ראש"),
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
