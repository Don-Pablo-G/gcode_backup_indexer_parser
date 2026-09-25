"""DD.MM.YYYY helpers shared by GUI date filters and the calendar popup."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional


def parse_display_date(raw: str) -> Optional[date]:
    """Parse ``DD.MM.YYYY`` / ``YYYY-MM-DD`` / ISO → ``date``, else None."""
    s = (raw or "").strip()
    if not s:
        return None
    if len(s) == 10 and s[2] in ".-/" and s[5] in ".-/":
        dd, mm, yyyy = s[0:2], s[3:5], s[6:10]
        if yyyy.isdigit() and mm.isdigit() and dd.isdigit():
            try:
                return date(int(yyyy), int(mm), int(dd))
            except ValueError:
                return None
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def format_display_date_dmy(d: date) -> str:
    return d.strftime("%d.%m.%Y")
