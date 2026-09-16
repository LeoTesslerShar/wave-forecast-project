"""Which board types this surf is realistically rideable on -- a judgement call with no
ground truth to fit against, same caveat as every other heuristic constant in this project
(see docs/DECISIONS.md). Operates on SURF HEIGHT (the displayed breaking-wave number) and
period, not offshore Hs -- board choice is about the wave a surfer actually meets.

Reasoning, stated plainly since it's not derived from anything measured:
  - Very small surf has too little push for a short/performance board to plane on --
    longboards and soft-tops (more volume, easier paddle-in) are what's actually rideable.
  - Mid-size, workable-period surf is the "anything goes" range.
  - Big and/or fast (short-period) surf gets too steep and quick for a longboard to turn in
    time -- shortboards only. A long period at real size is still manageable on a longboard
    (more time per wave), so period, not just height, gates this band.
"""
from dataclasses import dataclass

SOFT_TOP = "סופט טופ"
LONGBOARD = "לוח ארוך"
SHORTBOARD = "לוח קצר"

SMALL_MAX_M = 0.5  # below this: too weak to plane a shortboard
BIG_MIN_M = 1.3  # at/above this: too steep/fast for a longboard, UNLESS period is long
LONG_PERIOD_S = 9.0  # a long-period big day still has enough time-per-wave for a longboard


@dataclass
class BoardRecommendation:
    boards: list[str]  # Hebrew labels, best-first
    method: str = "unvalidated_heuristic"


def recommend_boards(surf_height_m: float | None, period_s: float | None) -> BoardRecommendation:
    if surf_height_m is None:
        return BoardRecommendation(boards=[])
    if surf_height_m < SMALL_MAX_M:
        return BoardRecommendation(boards=[LONGBOARD, SOFT_TOP])
    if surf_height_m < BIG_MIN_M:
        return BoardRecommendation(boards=[SHORTBOARD, LONGBOARD, SOFT_TOP])
    if period_s is not None and period_s >= LONG_PERIOD_S:
        return BoardRecommendation(boards=[SHORTBOARD, LONGBOARD])
    return BoardRecommendation(boards=[SHORTBOARD])
