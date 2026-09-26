"""Reuse unchanged source files across scans (#9 incremental)."""

from __future__ import annotations

import sqlite3
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from gcode_index.birthtime import file_mtime
from gcode_index.models import FileSeen, ProgramInstance


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


@dataclass
class CachedSource:
    """Prior index rows for one source file (keyed by scan_root + relative path)."""

    source_path: str
    scan_root: str
    size: Optional[int]
    mtime: Optional[datetime]
    source_type: Optional[str]
    instances: list[ProgramInstance] = field(default_factory=list)


@dataclass
class ScanCache:
    """Lookup of previously indexed sources for incremental scan."""

    by_key: dict[tuple[str, str], CachedSource] = field(default_factory=dict)

    def get(self, scan_root: str, source_path: str) -> Optional[CachedSource]:
        return self.by_key.get((scan_root or "", source_path))

    def try_reuse(
        self,
        path: Path,
        *,
        scan_root: str,
        source_path: str,
    ) -> Optional[tuple[list[ProgramInstance], FileSeen]]:
        """If ``path`` matches a cached stamp, return deep-copied instances + FileSeen."""
        hit = self.get(scan_root, source_path)
        if hit is None or hit.size is None:
            return None
        try:
            st = path.stat()
        except OSError:
            return None
        if int(st.st_size) != int(hit.size):
            return None
        if hit.mtime is not None:
            cur = file_mtime(path)
            if abs((cur - hit.mtime).total_seconds()) > 1.5:
                return None
        instances = deepcopy(hit.instances)
        seen = FileSeen(
            source_path=source_path,
            source_type=hit.source_type,
            size=hit.size,
            mtime=hit.mtime or file_mtime(path),
            status="cached",
            note=f"unchanged ({len(instances)} programs reused)",
        )
        return instances, seen


def load_scan_cache(conn: sqlite3.Connection) -> ScanCache:
    """Build a cache from the latest ``index_runs`` rows in ``conn``."""
    conn.row_factory = sqlite3.Row
    run = conn.execute(
        "SELECT run_id FROM index_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    cache = ScanCache()
    if run is None:
        return cache
    run_id = run["run_id"]

    # Prefer files_seen stamps when present; fall back to instance aggregates
    stamps: dict[tuple[str, str], tuple[Optional[int], Optional[datetime], Optional[str]]] = {}
    # We don't store scan_root on files_seen — join via instances
    for row in conn.execute(
        """
        SELECT source_path, source_type, size, mtime
        FROM files_seen
        WHERE run_id = ? AND status IN ('indexed', 'cached')
        """,
        (run_id,),
    ):
        # Temporary key without scan_root; refined when we see instances
        key = ("", row["source_path"] or "")
        stamps[key] = (
            row["size"],
            _parse_iso(row["mtime"]),
            row["source_type"],
        )

    grouped: dict[tuple[str, str], CachedSource] = {}
    for row in conn.execute(
        """
        SELECT program_number, part_number, machine_id, machine_label,
               machine_folder_raw, date_folder_raw, backup_date, date_source,
               source_path, line_start, line_end, byte_start, byte_end,
               source_type, folder_path, control_family, source_mtime, source_size,
               content_sha256, program_sha256, parser_id, parser_version, parse_status,
               error_message, header_kind, provenance, scan_root, programmer
        FROM program_instances
        WHERE run_id = ?
        """,
        (run_id,),
    ):
        root = str(row["scan_root"] or "")
        sp = str(row["source_path"] or "")
        key = (root, sp)
        if key not in grouped:
            size = row["source_size"]
            mtime = _parse_iso(row["source_mtime"])
            stype = row["source_type"]
            # Prefer files_seen stamp if path matches (scan_root-agnostic fallback)
            fs = stamps.get(("", sp))
            if fs is not None:
                if fs[0] is not None:
                    size = fs[0]
                if fs[1] is not None:
                    mtime = fs[1]
                if fs[2]:
                    stype = fs[2]
            grouped[key] = CachedSource(
                source_path=sp,
                scan_root=root,
                size=int(size) if size is not None else None,
                mtime=mtime,
                source_type=stype,
                instances=[],
            )
        backup_date = _parse_iso(row["backup_date"]) or datetime.now(timezone.utc)
        keys = row.keys()
        prog_sha = row["program_sha256"] if "program_sha256" in keys else None
        grouped[key].instances.append(
            ProgramInstance(
                program_number=str(row["program_number"] or ""),
                part_number=row["part_number"],
                machine_id=str(row["machine_id"] or "unknown"),
                machine_label=row["machine_label"],
                machine_folder_raw=row["machine_folder_raw"],
                date_folder_raw=row["date_folder_raw"],
                backup_date=backup_date,
                date_source=str(row["date_source"] or "mtime"),
                source_path=sp,
                line_start=row["line_start"],
                line_end=row["line_end"],
                byte_start=row["byte_start"],
                byte_end=row["byte_end"],
                source_type=str(row["source_type"] or ""),
                folder_path=row["folder_path"],
                control_family=row["control_family"],
                source_mtime=_parse_iso(row["source_mtime"]),
                source_size=row["source_size"],
                content_sha256=row["content_sha256"],
                program_sha256=prog_sha,
                parser_id=row["parser_id"],
                parser_version=row["parser_version"],
                parse_status=str(row["parse_status"] or "ok"),
                error_message=row["error_message"],
                header_kind=row["header_kind"],
                provenance=str(row["provenance"] or "backup"),
                scan_root=row["scan_root"],
                programmer=row["programmer"],
            )
        )

    cache.by_key = grouped
    return cache
