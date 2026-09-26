"""Saved search / filter views (presets) next to the index database.

Prefer ``views.yaml`` (data-pack sidecar). Legacy ``filter_presets.yaml`` is
still loaded when ``views.yaml`` is absent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

VIEWS_FILENAME = "views.yaml"
PRESETS_FILENAME = "filter_presets.yaml"  # legacy name; still read as fallback


@dataclass
class FilterPreset:
    """One named snapshot of the find-bar filters."""

    name: str
    text: str = ""
    machines: list[str] = field(default_factory=list)
    date_from: str = ""
    date_to: str = ""
    size_min: str = ""
    size_max: str = ""
    mtime_from: str = ""
    mtime_to: str = ""
    source_type: str = "(all)"
    control: str = "(all)"
    provenance: str = "(all)"
    programmer: str = "(all)"
    role: str = "(all)"
    odbiorca: str = "(all)"
    newest_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FilterPreset":
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("preset name is empty")
        machines_raw = data.get("machines") or []
        if isinstance(machines_raw, str):
            machines = [machines_raw] if machines_raw.strip() else []
        else:
            machines = [str(m).strip() for m in machines_raw if str(m).strip()]
        return cls(
            name=name,
            text=str(data.get("text") or ""),
            machines=machines,
            date_from=str(data.get("date_from") or ""),
            date_to=str(data.get("date_to") or ""),
            size_min=str(data.get("size_min") or ""),
            size_max=str(data.get("size_max") or ""),
            mtime_from=str(data.get("mtime_from") or ""),
            mtime_to=str(data.get("mtime_to") or ""),
            source_type=str(data.get("source_type") or "(all)"),
            control=str(data.get("control") or "(all)"),
            provenance=str(data.get("provenance") or "(all)"),
            programmer=str(data.get("programmer") or "(all)"),
            role=str(data.get("role") or "(all)"),
            odbiorca=str(data.get("odbiorca") or "(all)"),
            newest_only=bool(data.get("newest_only") or False),
        )


def _clean_preset(pr: FilterPreset) -> FilterPreset:
    return FilterPreset(
        name=(pr.name or "").strip(),
        text=pr.text or "",
        machines=list(pr.machines or []),
        date_from=pr.date_from or "",
        date_to=pr.date_to or "",
        size_min=getattr(pr, "size_min", "") or "",
        size_max=getattr(pr, "size_max", "") or "",
        mtime_from=getattr(pr, "mtime_from", "") or "",
        mtime_to=getattr(pr, "mtime_to", "") or "",
        source_type=pr.source_type or "(all)",
        control=pr.control or "(all)",
        provenance=pr.provenance or "(all)",
        programmer=pr.programmer or "(all)",
        role=getattr(pr, "role", "") or "(all)",
        odbiorca=getattr(pr, "odbiorca", "") or "(all)",
        newest_only=bool(pr.newest_only),
    )


def views_path_for_target(target: Path | str) -> Path:
    return Path(target) / VIEWS_FILENAME


def presets_path_for_target(target: Path | str) -> Path:
    """Path used for *saving* views — always ``views.yaml`` next to the DB."""
    return views_path_for_target(target)


def legacy_presets_path_for_target(target: Path | str) -> Path:
    return Path(target) / PRESETS_FILENAME


def resolve_presets_path_for_load(target: Path | str) -> Optional[Path]:
    """Prefer ``views.yaml``; fall back to legacy ``filter_presets.yaml``."""
    views = views_path_for_target(target)
    if views.is_file():
        return views
    legacy = legacy_presets_path_for_target(target)
    if legacy.is_file():
        return legacy
    return None


def _save_path_for(path: Path | str) -> Path:
    """Normalize a presets path so new writes land on ``views.yaml`` when possible."""
    p = Path(path)
    if p.is_dir():
        return views_path_for_target(p)
    if p.name in (VIEWS_FILENAME, PRESETS_FILENAME):
        return views_path_for_target(p.parent)
    return p


def _load_existing_for(path: Path | str) -> list[FilterPreset]:
    p = Path(path)
    if p.is_dir():
        return load_presets_for_target(p)
    if p.name in (VIEWS_FILENAME, PRESETS_FILENAME):
        return load_presets_for_target(p.parent)
    return load_presets(p)


def load_presets(path: Path | str) -> list[FilterPreset]:
    p = Path(path)
    if not p.is_file():
        return []
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw_list: list[Any]
    if isinstance(data, list):
        raw_list = data
    elif isinstance(data, dict):
        raw_list = data.get("presets") or data.get("views") or []
    else:
        return []
    out: list[FilterPreset] = []
    seen: set[str] = set()
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        try:
            preset = FilterPreset.from_dict(item)
        except ValueError:
            continue
        key = preset.name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(preset)
    out.sort(key=lambda pr: pr.name.casefold())
    return out


def load_presets_for_target(target: Path | str) -> list[FilterPreset]:
    path = resolve_presets_path_for_load(target)
    if path is None:
        return []
    return load_presets(path)


def save_presets(path: Path | str, presets: Iterable[FilterPreset]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cleaned: list[FilterPreset] = []
    seen: set[str] = set()
    for pr in presets:
        item = _clean_preset(pr)
        if not item.name:
            continue
        key = item.name.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    cleaned.sort(key=lambda pr: pr.name.casefold())
    payload: dict[str, Any] = {
        "views": [pr.to_dict() for pr in cleaned],
        # Keep ``presets`` key for older readers of the same file shape
        "presets": [pr.to_dict() for pr in cleaned],
        "_comment": (
            "Named find-bar filter views for the G-code Backup Indexer GUI. "
            "Saved as views.yaml next to gcode_index.sqlite "
            "(shop-local; never written into the backup tree)."
        ),
    }
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            payload,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    return p


def upsert_preset(path: Path | str, preset: FilterPreset) -> list[FilterPreset]:
    """Insert or replace a preset by name (case-insensitive). Returns full list."""
    save_path = _save_path_for(path)
    existing = _load_existing_for(path)
    key = preset.name.strip().casefold()
    out = [pr for pr in existing if pr.name.casefold() != key]
    out.append(preset)
    save_presets(save_path, out)
    return load_presets(save_path)


def delete_preset(path: Path | str, name: str) -> list[FilterPreset]:
    key = (name or "").strip().casefold()
    save_path = _save_path_for(path)
    existing = _load_existing_for(path)
    out = [pr for pr in existing if pr.name.casefold() != key]
    save_presets(save_path, out)
    return load_presets(save_path)


def get_preset(path: Path | str, name: str) -> Optional[FilterPreset]:
    key = (name or "").strip().casefold()
    for pr in _load_existing_for(path):
        if pr.name.casefold() == key:
            return pr
    return None
