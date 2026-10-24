"""Shared time conventions: all schedule times are minutes since local midnight.

A simulated day runs from local midnight to the next local midnight in
LOCAL_TIMEZONE, regardless of when the app is started.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

LOCAL_TIMEZONE = ZoneInfo("Europe/London")


def day_bounds(
    day: date | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return (midnight, next midnight) for day.

    Defaults to the simulated day: tomorrow in LOCAL_TIMEZONE, relative to
    `now` (or the current time). Running at 15:00 on the 24th simulates
    00:00 on the 25th to 00:00 on the 26th.
    """
    if day is None:
        today = (now or datetime.now(LOCAL_TIMEZONE)).astimezone(LOCAL_TIMEZONE).date()
        day = today + timedelta(days=1)

    start = datetime.combine(day, time.min, tzinfo=LOCAL_TIMEZONE)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=LOCAL_TIMEZONE)
    return start, end


def minutes_since_midnight(moment: datetime, day_start: datetime) -> int:
    """Wall-clock minutes from day_start (local midnight) to moment."""
    local = moment.astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)
    return int((local - day_start.replace(tzinfo=None)).total_seconds() // 60)


def at_minute(day_start: datetime, minute: int) -> datetime:
    """The tz-aware local datetime at `minute` (0-1439) on day_start's date."""
    if not 0 <= minute < 24 * 60:
        raise ValueError("Schedule times must be minutes after midnight (0-1439).")

    return datetime.combine(
        day_start.date(),
        time(hour=minute // 60, minute=minute % 60),
        tzinfo=LOCAL_TIMEZONE,
    )
