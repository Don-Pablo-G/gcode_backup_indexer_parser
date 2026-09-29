"""Shop defaults sidecar next to the database folder (``indexer_settings.yaml``).

Carries scan toggles, Watch coalesce / safety, and watch defaults with the data pack.
Never stores or forces ``can_index`` — that stays in local ``gcode-index.ini``.

Legacy ``schedule`` keys migrate once into ``watch_coalesce_s`` + ``watch_safety``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

import yaml

from gcode_index.folder_watch import DEFAULT_WATCH_MODE, normalize_watch_mode
from gcode_index.schedule import (
    DEFAULT_WATCH_COALESCE_S,
    SCHEDULE_OFF,
    clamp_watch_coalesce_s,
    migrate_legacy_schedule,
    normalize_watch_safety,
    normalize_watch_safety_at,
)

INDEXER_SETTINGS_FILENAME = "indexer_settings.yaml"


@dataclass
class IndexerSettings:
    """Shared shop defaults loaded when ``target`` points at this folder."""

    incremental: bool = True
    also_excel: bool = False
    newest_only: bool = False
    include_unknown: bool = True
    watch_folders: bool = False
    watch_mode: str = DEFAULT_WATCH_MODE
    # Default yes: omit main backup from live Watch roots (extras still watched).
    watch_exclude_backup: bool = True
    watch_coalesce_s: int = DEFAULT_WATCH_COALESCE_S
    watch_safety: str = SCHEDULE_OFF
    # Optional local HH:MM anchor; blank = interval from last run.
    watch_safety_at: str = ""
    # Optional documented logical roots (UNC/share forms preferred when known)
    backup_hint: str = ""
    green_root_hints: list[str] = field(default_factory=list)
    yellow_root_hints: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.watch_mode = normalize_watch_mode(self.watch_mode)
        self.watch_coalesce_s = clamp_watch_coalesce_s(self.watch_coalesce_s)
        self.watch_safety = normalize_watch_safety(self.watch_safety)
        self.watch_safety_at = normalize_watch_safety_at(self.watch_safety_at)
        self.backup_hint = (self.backup_hint or "").strip()
        self.green_root_hints = _clean_path_list(self.green_root_hints)
        self.yellow_root_hints = _clean_path_list(self.yellow_root_hints)


def _clean_path_list(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        s = str(item or "").strip()
        if not s or s.casefold() in seen:
            continue
        seen.add(s.casefold())
        out.append(s)
    return out


def _truthy(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    raw = str(value).strip().casefold()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "y", "on", "tak"):
        return True
    if raw in ("0", "false", "no", "n", "off", "nie"):
        return False
    return default


def indexer_settings_path_for_target(target: Path | str) -> Path:
    return Path(target) / INDEXER_SETTINGS_FILENAME


def load_indexer_settings(path: Path | str | None) -> Optional[IndexerSettings]:
    """Load sidecar or return ``None`` when missing / unreadable."""
    if path is None:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except OSError:
        return None
    if not isinstance(data, dict):
        return IndexerSettings()
    # Never honour a can_index key if present in an old/hand-edited file
    data.pop("can_index", None)
    data.pop("ui_mode", None)

    has_coalesce = "watch_coalesce_s" in data
    has_safety = "watch_safety" in data
    if has_coalesce or has_safety:
        coalesce_s = (
            clamp_watch_coalesce_s(data.get("watch_coalesce_s"))
            if has_coalesce
            else DEFAULT_WATCH_COALESCE_S
        )
        safety = (
            normalize_watch_safety(str(data.get("watch_safety") or SCHEDULE_OFF))
            if has_safety
            else SCHEDULE_OFF
        )
    else:
        coalesce_s, safety = migrate_legacy_schedule(
            str(data.get("schedule") or SCHEDULE_OFF)
        )

    return IndexerSettings(
        incremental=_truthy(data.get("incremental"), default=True),
        also_excel=_truthy(data.get("also_excel"), default=False),
        newest_only=_truthy(data.get("newest_only"), default=False),
        include_unknown=_truthy(data.get("include_unknown"), default=True),
        watch_folders=_truthy(data.get("watch_folders"), default=False),
        watch_mode=normalize_watch_mode(
            str(data.get("watch_mode") or DEFAULT_WATCH_MODE)
        ),
        # Missing key → yes (exclude backup from Watch), same as ini migrate.
        watch_exclude_backup=_truthy(
            data.get("watch_exclude_backup"), default=True
        ),
        watch_coalesce_s=coalesce_s,
        watch_safety=safety,
        watch_safety_at=normalize_watch_safety_at(
            str(data.get("watch_safety_at") or "")
        ),
        backup_hint=str(data.get("backup_hint") or "").strip(),
        green_root_hints=_clean_path_list(data.get("green_root_hints")),
        yellow_root_hints=_clean_path_list(data.get("yellow_root_hints")),
    )


def save_indexer_settings(
    path: Path | str,
    settings: IndexerSettings,
) -> Path:
    """Write shop defaults sidecar (never includes ``can_index``)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "_comment": (
            "Shop / indexer defaults for this database folder (data pack). "
            "Loaded when target points here. Does NOT set indexer capability "
            "(that stays in local gcode-index.ini next to the exe). "
            "watch_coalesce_s = min quiet seconds; watch_safety = off|15m|1h|…; "
            "watch_safety_at = optional HH:MM local clock anchor (blank = from last run); "
            "watch_exclude_backup = yes omits main backup from live Watch roots"
        ),
        "incremental": bool(settings.incremental),
        "also_excel": bool(settings.also_excel),
        "newest_only": bool(settings.newest_only),
        "include_unknown": bool(settings.include_unknown),
        "watch_folders": bool(settings.watch_folders),
        "watch_mode": normalize_watch_mode(settings.watch_mode),
        "watch_exclude_backup": bool(settings.watch_exclude_backup),
        "watch_coalesce_s": clamp_watch_coalesce_s(settings.watch_coalesce_s),
        "watch_safety": normalize_watch_safety(settings.watch_safety),
        "watch_safety_at": normalize_watch_safety_at(settings.watch_safety_at),
    }
    if settings.backup_hint:
        payload["backup_hint"] = settings.backup_hint
    if settings.green_root_hints:
        payload["green_root_hints"] = list(settings.green_root_hints)
    if settings.yellow_root_hints:
        payload["yellow_root_hints"] = list(settings.yellow_root_hints)
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            payload,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    return p


def settings_equal(a: IndexerSettings, b: IndexerSettings) -> bool:
    for f in fields(IndexerSettings):
        if getattr(a, f.name) != getattr(b, f.name):
            return False
    return True
