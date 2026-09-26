"""Saved search / filter presets next to the index database (#2)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

PRESETS_FILENAME = "filter_presets.yaml"


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
            newest_only=bool(data.get("newest_only") or False),
        )


def presets_path_for_target(target: Path | str) -> Path:
    return Path(target) / PRESETS_FILENAME


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
        raw_list = data.get("presets") or []
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


def save_presets(path: Path | str, presets: Iterable[FilterPreset]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cleaned: list[FilterPreset] = []
    seen: set[str] = set()
    for pr in presets:
        name = (pr.name or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(
            FilterPreset(
                name=name,
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
                newest_only=bool(pr.newest_only),
            )
        )
    cleaned.sort(key=lambda pr: pr.name.casefold())
    payload: dict[str, Any] = {
        "presets": [pr.to_dict() for pr in cleaned],
        "_comment": (
            "Named find-bar filter presets for the G-code Backup Indexer GUI. "
            "Saved next to gcode_index.sqlite (shop-local; never written into the backup tree)."
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
    existing = load_presets(path)
    key = preset.name.strip().casefold()
    out = [p for p in existing if p.name.casefold() != key]
    out.append(preset)
    save_presets(path, out)
    return load_presets(path)


def delete_preset(path: Path | str, name: str) -> list[FilterPreset]:
    key = (name or "").strip().casefold()
    existing = load_presets(path)
    out = [p for p in existing if p.name.casefold() != key]
    save_presets(path, out)
    return out


def get_preset(path: Path | str, name: str) -> Optional[FilterPreset]:
    key = (name or "").strip().casefold()
    for p in load_presets(path):
        if p.name.casefold() == key:
            return p
    return None
