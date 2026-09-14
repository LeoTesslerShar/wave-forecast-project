"""Per-hour matching against a Subscription's criteria, and clustering the qualifying
hours into contiguous windows -- prompts/phase-4-alerting.md sections 1, 3, 6.
"""
from dataclasses import dataclass
from datetime import datetime

from app.alerting.calibration import DEFAULT_OPERATING_POINT, OPERATING_POINTS
from app.models import Forecast, Subscription
from app.schemas import QualityOut


def direction_in_range(direction: float, dir_min: float, dir_max: float) -> bool:
    """True if `direction` falls in [dir_min, dir_max], wrapping across 0/360 when
    dir_max < dir_min (e.g. min=300, max=30 means "300 through 360 through 30")."""
    direction = direction % 360
    dir_min = dir_min % 360
    dir_max = dir_max % 360
    if dir_min <= dir_max:
        return dir_min <= direction <= dir_max
    return direction >= dir_min or direction <= dir_max


@dataclass
class HourMatch:
    hour: QualityOut
    qualifies: bool
    effective_min_height: float | None


def hour_qualifies(forecast: Forecast, hour: QualityOut, sub: Subscription) -> HourMatch:
    """`forecast` is the same row `hour` (the Phase 3 QualityOut) was built from -- carries
    the raw swell direction, which QualityOut does not re-expose on its own."""
    offset = OPERATING_POINTS.get(sub.operating_point, OPERATING_POINTS[DEFAULT_OPERATING_POINT])
    effective_min = (sub.min_height - offset) if sub.min_height is not None else None

    estimate = hour.size.wave_height_estimate
    if estimate is None:
        return HourMatch(hour=hour, qualifies=False, effective_min_height=effective_min)

    if effective_min is not None and estimate < effective_min:
        return HourMatch(hour=hour, qualifies=False, effective_min_height=effective_min)
    if sub.max_height is not None and estimate > sub.max_height:
        return HourMatch(hour=hour, qualifies=False, effective_min_height=effective_min)

    if sub.swell_dir_min is not None and sub.swell_dir_max is not None:
        direction = forecast.swell_wave_direction or forecast.wave_direction
        if direction is None or not direction_in_range(direction, sub.swell_dir_min, sub.swell_dir_max):
            return HourMatch(hour=hour, qualifies=False, effective_min_height=effective_min)

    return HourMatch(hour=hour, qualifies=True, effective_min_height=effective_min)


@dataclass
class Cluster:
    hours: list[HourMatch]

    @property
    def start(self) -> datetime:
        return self.hours[0].hour.valid_at

    @property
    def end(self) -> datetime:
        return self.hours[-1].hour.valid_at

    @property
    def avg_quality_score(self) -> float:
        return sum(h.hour.quality_score for h in self.hours) / len(self.hours)


def cluster_qualifying_hours(matches: list[HourMatch]) -> list[Cluster]:
    """Contiguous qualifying hours become one cluster -- section 3, "six good hours on
    Tuesday is one alert about a Tuesday window, not six hourly alerts." Contiguity means
    consecutive valid_at hours with no gap; matches must already be sorted by valid_at."""
    clusters: list[Cluster] = []
    current: list[HourMatch] = []
    prev_hour: datetime | None = None

    for m in matches:
        if not m.qualifies:
            if current:
                clusters.append(Cluster(hours=current))
                current = []
            prev_hour = None
            continue
        if current and prev_hour is not None:
            gap_hours = (m.hour.valid_at - prev_hour).total_seconds() / 3600
            if gap_hours > 1.0:
                clusters.append(Cluster(hours=current))
                current = []
        current.append(m)
        prev_hour = m.hour.valid_at

    if current:
        clusters.append(Cluster(hours=current))
    return clusters


def best_cluster(clusters: list[Cluster]) -> Cluster | None:
    if not clusters:
        return None
    return max(clusters, key=lambda c: (c.avg_quality_score, len(c.hours)))
