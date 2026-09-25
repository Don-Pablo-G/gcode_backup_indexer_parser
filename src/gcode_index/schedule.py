"""Optional automatic re-index schedule (hourly / daily / weekly)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

SCHEDULE_OFF = "off"
SCHEDULE_HOURLY = "hourly"
SCHEDULE_DAILY = "daily"
SCHEDULE_WEEKLY = "weekly"
SCHEDULE_CHOICES = (SCHEDULE_OFF, SCHEDULE_HOURLY, SCHEDULE_DAILY, SCHEDULE_WEEKLY)

_INTERVALS = {
    SCHEDULE_HOURLY: timedelta(hours=1),
    SCHEDULE_DAILY: timedelta(days=1),
    SCHEDULE_WEEKLY: timedelta(days=7),
}


def normalize_schedule(value: Optional[str]) -> str:
    raw = (value or SCHEDULE_OFF).strip().casefold()
    aliases = {
        "off": SCHEDULE_OFF,
        "none": SCHEDULE_OFF,
        "disabled": SCHEDULE_OFF,
        "0": SCHEDULE_OFF,
        "hour": SCHEDULE_HOURLY,
        "hourly": SCHEDULE_HOURLY,
        "1h": SCHEDULE_HOURLY,
        "day": SCHEDULE_DAILY,
        "daily": SCHEDULE_DAILY,
        "1d": SCHEDULE_DAILY,
        "week": SCHEDULE_WEEKLY,
        "weekly": SCHEDULE_WEEKLY,
        "1w": SCHEDULE_WEEKLY,
    }
    return aliases.get(raw, SCHEDULE_OFF if raw not in SCHEDULE_CHOICES else raw)


def schedule_interval(schedule: str) -> Optional[timedelta]:
    return _INTERVALS.get(normalize_schedule(schedule))


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_iso_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def is_schedule_due(
    schedule: str,
    last_run: Optional[datetime | str],
    *,
    now: Optional[datetime] = None,
) -> bool:
    """True when an auto-index should run for the given schedule."""
    code = normalize_schedule(schedule)
    interval = schedule_interval(code)
    if interval is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    previous = (
        last_run
        if isinstance(last_run, datetime)
        else parse_iso_datetime(str(last_run) if last_run else None)
    )
    if previous is None:
        return True
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    return current >= previous + interval


def next_schedule_at(
    schedule: str,
    last_run: Optional[datetime | str],
    *,
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    code = normalize_schedule(schedule)
    interval = schedule_interval(code)
    if interval is None:
        return None
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    previous = (
        last_run
        if isinstance(last_run, datetime)
        else parse_iso_datetime(str(last_run) if last_run else None)
    )
    if previous is None:
        return current
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    nxt = previous + interval
    return nxt if nxt > current else current
