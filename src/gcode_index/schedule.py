"""Flexible auto-index schedule: off | Ns | Nm | Nh | Nd.

Legacy presets ``hourly`` / ``daily`` / ``weekly`` normalize to ``1h`` / ``1d`` / ``7d``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

SCHEDULE_OFF = "off"
UNIT_SECONDS = "s"
UNIT_MINUTES = "m"
UNIT_HOURS = "h"
UNIT_DAYS = "d"
SCHEDULE_UNITS = (UNIT_SECONDS, UNIT_MINUTES, UNIT_HOURS, UNIT_DAYS)

# Minimums — avoid thrashing the indexer / NAS
MIN_BY_UNIT = {
    UNIT_SECONDS: 10,
    UNIT_MINUTES: 1,
    UNIT_HOURS: 1,
    UNIT_DAYS: 1,
}
MAX_AMOUNT = 9999

# Legacy preset names still accepted on load / old UI settings
SCHEDULE_HOURLY = "1h"
SCHEDULE_DAILY = "1d"
SCHEDULE_WEEKLY = "7d"

_LEGACY = {
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

_UNIT_ALIASES = {
    "s": UNIT_SECONDS,
    "sec": UNIT_SECONDS,
    "secs": UNIT_SECONDS,
    "second": UNIT_SECONDS,
    "seconds": UNIT_SECONDS,
    "m": UNIT_MINUTES,
    "min": UNIT_MINUTES,
    "mins": UNIT_MINUTES,
    "minute": UNIT_MINUTES,
    "minutes": UNIT_MINUTES,
    "h": UNIT_HOURS,
    "hr": UNIT_HOURS,
    "hrs": UNIT_HOURS,
    "hour": UNIT_HOURS,
    "hours": UNIT_HOURS,
    "d": UNIT_DAYS,
    "day": UNIT_DAYS,
    "days": UNIT_DAYS,
}

_FLEX_RE = re.compile(
    r"^\s*(\d+)\s*([a-zA-Z]+)?\s*$",
)


def clamp_amount(amount: int, unit: str) -> int:
    unit_n = (unit or UNIT_MINUTES).strip().casefold()
    unit_n = _UNIT_ALIASES.get(unit_n, unit_n)
    if unit_n not in MIN_BY_UNIT:
        unit_n = UNIT_MINUTES
    lo = MIN_BY_UNIT[unit_n]
    try:
        n = int(amount)
    except (TypeError, ValueError):
        n = lo
    return max(lo, min(MAX_AMOUNT, n))


def format_schedule(amount: int, unit: str) -> str:
    """Build canonical ``15m`` / ``off`` string."""
    unit_n = (unit or "").strip().casefold()
    if unit_n in ("", "off", "none", "disabled"):
        return SCHEDULE_OFF
    unit_n = _UNIT_ALIASES.get(unit_n, unit_n)
    if unit_n not in MIN_BY_UNIT:
        return SCHEDULE_OFF
    n = clamp_amount(amount, unit_n)
    return f"{n}{unit_n}"


def parse_schedule(value: Optional[str]) -> tuple[int, str] | None:
    """Return ``(amount, unit)`` or ``None`` when schedule is off/invalid."""
    code = normalize_schedule(value)
    if code == SCHEDULE_OFF:
        return None
    m = re.fullmatch(r"(\d+)([smhd])", code)
    if not m:
        return None
    return int(m.group(1)), m.group(2)


def normalize_schedule(value: Optional[str]) -> str:
    """Canonical form: ``off`` or ``{n}{s|m|h|d}`` (clamped)."""
    raw = (value or SCHEDULE_OFF).strip().casefold()
    if not raw:
        return SCHEDULE_OFF
    if raw in _LEGACY:
        return _LEGACY[raw]

    m = _FLEX_RE.match(raw)
    if not m:
        # Also accept "every 15 minutes" style leftovers → off
        return SCHEDULE_OFF
    amount_s, unit_raw = m.group(1), (m.group(2) or "m")
    unit = _UNIT_ALIASES.get(unit_raw.casefold())
    if unit is None:
        return SCHEDULE_OFF
    return format_schedule(int(amount_s), unit)


def schedule_interval(schedule: str) -> Optional[timedelta]:
    parsed = parse_schedule(schedule)
    if parsed is None:
        return None
    amount, unit = parsed
    if unit == UNIT_SECONDS:
        return timedelta(seconds=amount)
    if unit == UNIT_MINUTES:
        return timedelta(minutes=amount)
    if unit == UNIT_HOURS:
        return timedelta(hours=amount)
    if unit == UNIT_DAYS:
        return timedelta(days=amount)
    return None


def schedule_poll_ms(schedule: str) -> int:
    """How often the GUI should re-check due status while a schedule is armed."""
    interval = schedule_interval(schedule)
    if interval is None:
        return 30_000
    secs = max(1.0, interval.total_seconds())
    if secs <= 60:
        # Half the interval, but at least 1s and at most 5s
        return int(max(1.0, min(5.0, secs / 2.0)) * 1000)
    if secs <= 3600:
        return 15_000
    return 30_000


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
    interval = schedule_interval(schedule)
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
    interval = schedule_interval(schedule)
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
