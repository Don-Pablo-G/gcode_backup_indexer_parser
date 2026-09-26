"""Persistent index-run history (sidecar next to the DB).

The GUI rebuilds ``gcode_index.sqlite`` on each scan, so run history lives in
``scan_history.json`` beside the database and survives wipes. Useful for
troubleshooting network spikes / long incremental runs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from gcode_index.models import ScanResult
from gcode_index.scan_cache import ScanCache

log = logging.getLogger("gcode_index.scan_history")

HISTORY_FILENAME = "scan_history.json"
DEFAULT_HISTORY_LIMIT = 40


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class ScanHistoryEntry:
    """One completed index run (best-available stats)."""

    run_id: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_s: float = 0.0
    backup_root: str = ""
    instance_count: int = 0
    file_count: int = 0
    files_indexed: int = 0
    files_cached: int = 0
    files_skipped: int = 0
    files_error: int = 0
    files_added: int = 0
    files_updated: int = 0
    files_removed: int = 0
    unknown_folders: int = 0
    incremental: bool = False
    auto: bool = False
    note: str = ""

    def duration_label(self) -> str:
        s = max(0.0, float(self.duration_s))
        if s < 60:
            return f"{s:.1f}s"
        m, rem = divmod(int(round(s)), 60)
        if m < 60:
            return f"{m}m {rem}s"
        h, m = divmod(m, 60)
        return f"{h}h {m}m"


def history_path_for_target(target: Path | str) -> Path:
    return Path(target) / HISTORY_FILENAME


def load_scan_history(
    path: Path | str,
    *,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> list[ScanHistoryEntry]:
    p = Path(path)
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("load scan history failed: %s", p)
        return []
    items = raw.get("runs") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    out: list[ScanHistoryEntry] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            out.append(
                ScanHistoryEntry(
                    run_id=str(item.get("run_id") or ""),
                    started_at=str(item.get("started_at") or ""),
                    finished_at=str(item.get("finished_at") or ""),
                    duration_s=float(item.get("duration_s") or 0.0),
                    backup_root=str(item.get("backup_root") or ""),
                    instance_count=int(item.get("instance_count") or 0),
                    file_count=int(item.get("file_count") or 0),
                    files_indexed=int(item.get("files_indexed") or 0),
                    files_cached=int(item.get("files_cached") or 0),
                    files_skipped=int(item.get("files_skipped") or 0),
                    files_error=int(item.get("files_error") or 0),
                    files_added=int(item.get("files_added") or 0),
                    files_updated=int(item.get("files_updated") or 0),
                    files_removed=int(item.get("files_removed") or 0),
                    unknown_folders=int(item.get("unknown_folders") or 0),
                    incremental=bool(item.get("incremental")),
                    auto=bool(item.get("auto")),
                    note=str(item.get("note") or ""),
                )
            )
        except (TypeError, ValueError):
            continue
    # Newest first
    out.sort(key=lambda e: e.finished_at or e.started_at, reverse=True)
    return out[: max(1, int(limit))]


def save_scan_history(
    path: Path | str,
    entries: Iterable[ScanHistoryEntry],
    *,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        list(entries),
        key=lambda e: e.finished_at or e.started_at,
        reverse=True,
    )[: max(1, int(limit))]
    payload: dict[str, Any] = {
        "version": 1,
        "updated_at": _iso_now(),
        "runs": [asdict(e) for e in ordered],
    }
    p.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return p


def append_scan_history(
    target: Path | str,
    entry: ScanHistoryEntry,
    *,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> Path:
    path = history_path_for_target(target)
    existing = load_scan_history(path, limit=limit * 2)
    # Dedup by run_id when present
    if entry.run_id:
        existing = [e for e in existing if e.run_id != entry.run_id]
    existing.insert(0, entry)
    return save_scan_history(path, existing, limit=limit)


def build_history_entry(
    *,
    run_id: str,
    backup_root: str,
    result: ScanResult,
    started_at: datetime,
    finished_at: Optional[datetime] = None,
    prior_paths: Optional[set[str]] = None,
    incremental: bool = False,
    auto: bool = False,
) -> ScanHistoryEntry:
    """Compute best-available added/updated/removed stats for one run."""
    finished = finished_at or datetime.now(timezone.utc)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=timezone.utc)
    duration = max(0.0, (finished - started_at).total_seconds())

    indexed = 0
    cached = 0
    skipped = 0
    errors = 0
    current_paths: set[str] = set()
    indexed_paths: set[str] = set()
    for fs in result.files_seen:
        path = (fs.source_path or "").strip()
        st = (fs.status or "").strip().casefold()
        if path and st in ("indexed", "cached"):
            current_paths.add(path.casefold())
        if st == "indexed":
            indexed += 1
            if path:
                indexed_paths.add(path.casefold())
        elif st == "cached":
            cached += 1
        elif st == "skipped":
            skipped += 1
        elif st == "error":
            errors += 1

    prior = {p.casefold() for p in (prior_paths or set()) if p}
    if prior:
        added = len(indexed_paths - prior)
        updated = len(indexed_paths & prior)
        removed = len(prior - current_paths)
    else:
        # Full scan / no prior: treat indexed as "added" for lack of better signal
        added = indexed
        updated = 0
        removed = 0

    return ScanHistoryEntry(
        run_id=run_id,
        started_at=started_at.isoformat(),
        finished_at=finished.isoformat(),
        duration_s=duration,
        backup_root=backup_root,
        instance_count=len(result.instances),
        file_count=len(result.files_seen),
        files_indexed=indexed,
        files_cached=cached,
        files_skipped=skipped,
        files_error=errors,
        files_added=added,
        files_updated=updated,
        files_removed=removed,
        unknown_folders=len(result.unknowns),
        incremental=bool(incremental),
        auto=bool(auto),
    )


def prior_paths_from_cache(cache: Optional[ScanCache]) -> set[str]:
    """Paths known from the previous index (for added/updated/removed)."""
    if cache is None:
        return set()
    out: set[str] = set()
    for (_root, source_path), _hit in cache.by_key.items():
        if source_path:
            out.add(str(source_path).casefold())
    return out
