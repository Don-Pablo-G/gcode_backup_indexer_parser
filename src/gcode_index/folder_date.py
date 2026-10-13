"""Work Date from ``DD.MM.YYYY`` first path segment under a scan root.

Locked rules (0.2.126):

- Valid first segment → ``backup_date`` = that calendar day (UTC midnight),
  ``date_source=folder``.
- Main backup, invalid/missing → ``backup_date`` unknown (not birth),
  ``date_source=unknown``.
- Green/trusted/extra roots, invalid/missing → keep birth/mtime for
  ``backup_date``, ``date_source`` birth|mtime.
- ``file_ctime`` always stores real file birth (or mtime fallback).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal, Optional, Tuple

from gcode_index.date_format import parse_display_date

MissingFolderPolicy = Literal["unknown", "birth"]

DATE_SOURCE_FOLDER = "folder"
DATE_SOURCE_UNKNOWN = "unknown"


def first_segment_under_root(source_path: str) -> Optional[str]:
    """First path component of a root-relative ``source_path``, or None."""
    raw = (source_path or "").replace("\\", "/").strip().lstrip("/")
    if not raw:
        return None
    # Absolute / drive paths: no reliable "under root" segment
    if len(raw) >= 2 and raw[1] == ":":
        return None
    if raw.startswith("/"):
        return None
    part = raw.split("/", 1)[0].strip()
    return part or None


def parse_folder_date_name(name: Optional[str]) -> Optional[datetime]:
    """Parse a folder name as ``DD.MM.YYYY`` → UTC midnight, else None.

    Only dotted/slashed/dashed day-first forms accepted by
    :func:`parse_display_date` count; ISO ``YYYY-MM-DD`` folder names are
    also accepted there for robustness.
    """
    if not name:
        return None
    d: Optional[date] = parse_display_date(str(name).strip())
    if d is None:
        return None
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def resolve_work_date(
    *,
    source_path: str,
    date_folder_raw: Optional[str],
    file_ctime: datetime,
    birth_source: str,
    missing_folder_policy: MissingFolderPolicy,
) -> Tuple[Optional[datetime], str, Optional[str]]:
    """Resolve Work Date from the first segment under the scan root.

    Returns ``(backup_date | None, date_source, first_segment)``.
    ``None`` backup_date means unknown (main-backup policy).
    """
    segment = first_segment_under_root(source_path)
    if segment is None and date_folder_raw:
        segment = str(date_folder_raw).strip() or None

    folder_dt = parse_folder_date_name(segment)
    if folder_dt is not None:
        return folder_dt, DATE_SOURCE_FOLDER, segment

    if missing_folder_policy == "unknown":
        return None, DATE_SOURCE_UNKNOWN, segment

    src = birth_source if birth_source in ("birth", "mtime") else "birth"
    return file_ctime, src, segment


def apply_work_dates(
    instances: list,
    *,
    missing_folder_policy: MissingFolderPolicy,
) -> None:
    """Mutate instances: set ``backup_date`` / ``date_source``; keep ``file_ctime``."""
    for inst in instances:
        birth_source = (
            inst.date_source if inst.date_source in ("birth", "mtime") else "birth"
        )
        birth = getattr(inst, "file_ctime", None)
        if birth is None:
            birth = inst.backup_date
        if birth is None:
            continue

        backup_date, date_source, segment = resolve_work_date(
            source_path=str(inst.source_path or ""),
            date_folder_raw=inst.date_folder_raw,
            file_ctime=birth,
            birth_source=birth_source,
            missing_folder_policy=missing_folder_policy,
        )
        inst.file_ctime = birth
        inst.backup_date = backup_date  # type: ignore[assignment]
        inst.date_source = date_source
        if segment and not inst.date_folder_raw:
            inst.date_folder_raw = segment
