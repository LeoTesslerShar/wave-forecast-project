"""The calibrated threshold -- prompts/phase-4-alerting.md section 6. Does NOT correct the
displayed forecast height. It only widens or narrows which forecasts trigger an alert,
using the real GO/DON'T-GO table measured in docs/BIAS_ANALYSIS.md (the same table, not
invented numbers) to say honestly what that widening costs and buys.

`docs/BIAS_ANALYSIS.md` found the model under-calls the top of the surfable range: at a
1.5m bar it misses 20.8% of real sessions; at 1.0m, 13.1%. A naive `height >= threshold`
check inherits that miss rate. The fix here is not to nudge the displayed height -- no
correction survived Phase 3's own testing in the surfable range -- it is to also alert
slightly BELOW the user's stated bar, and say so plainly when that's what fired.
"""
from dataclasses import dataclass

# docs/BIAS_ANALYSIS.md "GO/DON'T-GO accuracy" table -- deployment 9, n=8212 hours.
# (threshold_m, missed_sessions_pct, wasted_trips_pct)
BIAS_TABLE = [
    (0.6, 3.9, 13.3),
    (0.8, 6.9, 12.7),
    (1.0, 13.1, 8.0),
    (1.2, 16.8, 8.1),
    (1.5, 20.8, 6.8),
]

# How far below the user's stated minimum height each operating point also alerts.
# Judgement calls, not measured -- docs/DECISIONS.md. balanced/generous are roughly half
# and the full width of the offshore forecast's own measured 90% spread
# (~0.19-0.25m, docs/BIAS_ANALYSIS.md), i.e. "lean into the model's own uncertainty band."
OPERATING_POINTS = {
    "strict": 0.0,
    "balanced": 0.15,
    "generous": 0.25,
}
DEFAULT_OPERATING_POINT = "balanced"


def _interpolate(threshold_m: float, column: int) -> float:
    """Piecewise-linear interpolation across BIAS_TABLE, clamped at the ends (no
    extrapolation beyond the measured range -- 0.6-1.5m is what was actually measured)."""
    xs = [row[0] for row in BIAS_TABLE]
    ys = [row[column] for row in BIAS_TABLE]
    if threshold_m <= xs[0]:
        return ys[0]
    if threshold_m >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= threshold_m <= xs[i + 1]:
            frac = (threshold_m - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + frac * (ys[i + 1] - ys[i])
    return ys[-1]  # unreachable, satisfies type checkers


def missed_rate_pct(threshold_m: float) -> float:
    return round(_interpolate(threshold_m, 1), 1)


def wasted_rate_pct(threshold_m: float) -> float:
    return round(_interpolate(threshold_m, 2), 1)


@dataclass
class OperatingPointEffect:
    operating_point: str
    user_threshold_m: float
    effective_threshold_m: float
    extra_sessions_caught_pct: float  # vs alerting only at the literal user threshold
    extra_false_alarms_pct: float
    description: str


def describe_operating_point(user_threshold_m: float, operating_point: str) -> OperatingPointEffect:
    offset = OPERATING_POINTS.get(operating_point, OPERATING_POINTS[DEFAULT_OPERATING_POINT])
    effective = max(0.0, user_threshold_m - offset)

    missed_at_user = missed_rate_pct(user_threshold_m)
    missed_at_effective = missed_rate_pct(effective)
    wasted_at_user = wasted_rate_pct(user_threshold_m)
    wasted_at_effective = wasted_rate_pct(effective)

    extra_caught = round(max(0.0, missed_at_user - missed_at_effective), 1)
    extra_wasted = round(max(0.0, wasted_at_effective - wasted_at_user), 1)

    if operating_point == "strict":
        description = (
            f"strict: alerts only at your literal {user_threshold_m:.2f}m bar -- "
            f"the model misses roughly {missed_at_user:.0f}% of real sessions at that bar "
            f"(docs/BIAS_ANALYSIS.md)."
        )
    else:
        description = (
            f"{operating_point}: also alerts down to {effective:.2f}m (your {user_threshold_m:.2f}m "
            f"bar minus {offset:.2f}m) -- catches roughly {extra_caught:.0f}% more real sessions at "
            f"your bar, at the cost of roughly {extra_wasted:.0f}% more trips that don't pan out "
            f"(interpolated from the measured GO/DON'T-GO table, docs/BIAS_ANALYSIS.md)."
        )

    return OperatingPointEffect(
        operating_point=operating_point,
        user_threshold_m=user_threshold_m,
        effective_threshold_m=round(effective, 2),
        extra_sessions_caught_pct=extra_caught,
        extra_false_alarms_pct=extra_wasted,
        description=description,
    )
