"""DST-boundary test in both directions -- prompts/phase-4-alerting.md acceptance check 2.

Real Israeli 2026 transitions, verified directly against zoneinfo rather than guessed (see
the transition-scan in the Phase 4 commit): for a 06:00 local window, the UTC hour changes
between 2026-03-26 (pre-transition, UTC+2) and 2026-03-27 (post-transition, UTC+3) in
spring, and between 2026-10-24 (UTC+3) and 2026-10-25 (post-transition, UTC+2) in autumn.
"""
from datetime import date, time

from app.alerting.timewindow import local_date_range_for_utc_now, window_utc_for_date

SPRING_BEFORE = date(2026, 3, 26)
SPRING_AFTER = date(2026, 3, 27)
FALL_BEFORE = date(2026, 10, 24)
FALL_AFTER = date(2026, 10, 25)


def test_spring_forward_produces_correct_utc_window():
    before = window_utc_for_date(SPRING_BEFORE, time(6, 0), time(9, 0))
    after = window_utc_for_date(SPRING_AFTER, time(6, 0), time(9, 0))

    # Before the transition: UTC+2, so 06:00 local = 04:00 UTC.
    assert before[0].hour == 4
    # After the transition: UTC+3, so 06:00 local = 03:00 UTC -- the UTC hour SHIFTS,
    # which is exactly what a hardcoded fixed offset would get wrong.
    assert after[0].hour == 3


def test_fall_back_produces_correct_utc_window():
    before = window_utc_for_date(FALL_BEFORE, time(6, 0), time(9, 0))
    after = window_utc_for_date(FALL_AFTER, time(6, 0), time(9, 0))

    assert before[0].hour == 3  # still UTC+3
    assert after[0].hour == 4   # back to UTC+2


def test_window_crossing_midnight():
    start, end = window_utc_for_date(date(2026, 6, 1), time(22, 0), time(2, 0))
    assert end > start
    assert (end - start).total_seconds() == 4 * 3600


def test_window_duration_is_correct_on_both_sides_of_spring_forward():
    """A 06:00-09:00 window is still 3 hours of WALL-CLOCK time on both sides of the
    transition -- window_utc_for_date must not silently produce a 2-hour or 4-hour span
    for the day the clocks actually jump."""
    for d in (SPRING_BEFORE, SPRING_AFTER):
        start, end = window_utc_for_date(d, time(6, 0), time(9, 0))
        assert (end - start).total_seconds() == 3 * 3600, f"wrong duration on {d}"


def test_local_date_range_uses_local_date_not_utc_date():
    from datetime import UTC, datetime

    # 22:30 UTC on 2026-06-01 is already 2026-06-02 01:30 in Jerusalem (UTC+3 in summer).
    now_utc = datetime(2026, 6, 1, 22, 30, tzinfo=UTC)
    dates = local_date_range_for_utc_now(now_utc, days_ahead=2)
    assert dates[0] == date(2026, 6, 2)
