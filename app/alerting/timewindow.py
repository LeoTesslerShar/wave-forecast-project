"""Local time window -> UTC conversion, DST-safe -- prompts/phase-4-alerting.md section 4.

Uses zoneinfo, never a fixed UTC offset. Israel's DST transitions (clocks change in late
March and late October) would silently break a hardcoded +2/+3 offset twice a year, and the
failure would look exactly like "the 07:00 alert fired at 06:00" -- the prompt's own
example of what this must not do. `datetime.combine(date, time, tzinfo=ZoneInfo(...))`
resolves the correct offset for that SPECIFIC date, which is what makes this safe across
a transition.
"""
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

JERUSALEM = ZoneInfo("Asia/Jerusalem")


def window_utc_for_date(target_date: date, start: time, end: time) -> tuple[datetime, datetime]:
    """The subscription's local time window, resolved to UTC for one specific calendar
    date. `end <= start` means the window crosses midnight (e.g. 22:00-02:00)."""
    start_local = datetime.combine(target_date, start, tzinfo=JERUSALEM)
    end_date = target_date if end > start else target_date + timedelta(days=1)
    end_local = datetime.combine(end_date, end, tzinfo=JERUSALEM)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def local_date_range_for_utc_now(now_utc: datetime, days_ahead: int) -> list[date]:
    """The local calendar dates to evaluate, starting today (local), for `days_ahead` more
    days. Uses the LOCAL date, not the UTC date -- near midnight UTC these can differ by a
    day, and a subscription's "today" means the surfer's today, not UTC's."""
    today_local = now_utc.astimezone(JERUSALEM).date()
    return [today_local + timedelta(days=i) for i in range(days_ahead + 1)]
