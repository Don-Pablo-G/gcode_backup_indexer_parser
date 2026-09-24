"""Persist and apply user folder→machine assignments for a backup tree.

Assignments are keyed by **machine folder name** (the top branch under each
date folder), not full paths — e.g. ``VF2S`` under any date maps the same way.
The map wins over ``aliases.yaml`` fuzzy matching when present.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from gcode_index.aliases import AliasMap, normalize_folder_name
from gcode_index.models import MachineInfo

MAP_FILENAME = "machine_folders.yaml"
UNKNOWN_ID = "unknown"
UNKNOWN_LABEL = "MACHINE UNKNOWN"


@dataclass
class FolderAssignment:
    folder_raw: str
    machine_id: str
    label: Optional[str] = None


@dataclass
class FolderMachineMap:
    """folder_raw → assignment (also indexed by normalized key)."""

    assignments: dict[str, FolderAssignment] = field(default_factory=dict)
    backup_root: Optional[str] = None

    def _store(self, assignment: FolderAssignment) -> None:
        self.assignments[assignment.folder_raw] = assignment

    def set(
        self,
        folder_raw: str,
        machine_id: str,
        label: Optional[str] = None,
    ) -> None:
        folder_raw = str(folder_raw).strip()
        if not folder_raw:
            return
        self._store(
            FolderAssignment(
                folder_raw=folder_raw,
                machine_id=str(machine_id).strip() or UNKNOWN_ID,
                label=(label.strip() if label else None),
            )
        )

    def get(self, folder_raw: str) -> Optional[FolderAssignment]:
        raw = str(folder_raw).strip()
        if raw in self.assignments:
            return self.assignments[raw]
        key = normalize_folder_name(raw)
        for a in self.assignments.values():
            if normalize_folder_name(a.folder_raw) == key:
                return a
        return None

    def resolve(
        self,
        folder_raw: str,
        aliases: Optional[AliasMap] = None,
    ) -> Optional[MachineInfo]:
        """Return MachineInfo if this folder is in the map; else None (caller falls back)."""
        hit = self.get(folder_raw)
        if hit is None:
            return None
        mid = hit.machine_id
        if mid == UNKNOWN_ID or mid.startswith("unmapped:"):
            return MachineInfo(
                machine_id=UNKNOWN_ID,
                label=hit.label or UNKNOWN_LABEL,
                machine_folder_raw=folder_raw,
                mapped=False,
            )
        if aliases is not None:
            catalog = aliases.info_for_machine_id(mid, folder_raw)
            if catalog is not None:
                if hit.label:
                    catalog.label = hit.label
                return catalog
        return MachineInfo(
            machine_id=mid,
            label=hit.label or mid,
            machine_folder_raw=folder_raw,
            mapped=True,
        )

    def to_dict(self) -> dict[str, Any]:
        folders: dict[str, Any] = {}
        for a in sorted(self.assignments.values(), key=lambda x: x.folder_raw.casefold()):
            entry: dict[str, Any] = {"machine_id": a.machine_id}
            if a.label:
                entry["label"] = a.label
            folders[a.folder_raw] = entry
        out: dict[str, Any] = {"folders": folders}
        if self.backup_root:
            out["backup_root"] = self.backup_root
        return out

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "FolderMachineMap":
        m = cls()
        if not data:
            return m
        m.backup_root = data.get("backup_root")
        folders = data.get("folders") or {}
        if isinstance(folders, dict):
            for raw, entry in folders.items():
                if isinstance(entry, str):
                    m.set(str(raw), entry)
                elif isinstance(entry, dict):
                    m.set(
                        str(raw),
                        str(entry.get("machine_id") or UNKNOWN_ID),
                        label=entry.get("label"),
                    )
        return m

    def save(self, path: Path | str) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                self.to_dict(),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        return p

    @classmethod
    def load(cls, path: Path | str) -> "FolderMachineMap":
        p = Path(path)
        if not p.is_file():
            return cls()
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return cls()
        return cls.from_dict(data)


def map_path_for_target(target: Path | str) -> Path:
    return Path(target) / MAP_FILENAME


def discover_machine_folders(backup_root: Path | str) -> list[str]:
    """Unique top-level machine folder names under each date directory.

    Layout: ``<backup>/<date>/<machine>/…`` — returns sorted unique ``<machine>`` names.
    Ignores files sitting directly under date folders.
    """
    root = Path(backup_root)
    if not root.is_dir():
        return []
    seen: set[str] = set()
    names: list[str] = []
    for date_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for machine_dir in sorted(p for p in date_dir.iterdir() if p.is_dir()):
            name = machine_dir.name
            key = normalize_folder_name(name)
            # Prefer first spelling seen for a normalized key
            if key in seen:
                continue
            seen.add(key)
            names.append(name)
    return names


def suggest_assignments(
    folders: Iterable[str],
    aliases: AliasMap,
    existing: Optional[FolderMachineMap] = None,
) -> FolderMachineMap:
    """Build a map: existing assignments win, else alias suggest, else UNKNOWN."""
    out = FolderMachineMap()
    if existing and existing.backup_root:
        out.backup_root = existing.backup_root
    for folder in folders:
        if existing is not None:
            prev = existing.get(folder)
            if prev is not None:
                out.set(folder, prev.machine_id, prev.label)
                continue
        info = aliases.resolve(folder)
        if info.mapped:
            out.set(folder, info.machine_id, info.label)
        else:
            out.set(folder, UNKNOWN_ID, UNKNOWN_LABEL)
    return out


def display_for_machine(machine_id: str, label: Optional[str] = None) -> str:
    lab = (label or "").strip()
    mid = (machine_id or "").strip() or UNKNOWN_ID
    if mid == UNKNOWN_ID:
        return f"{UNKNOWN_LABEL} ({UNKNOWN_ID})"
    if lab and lab != mid:
        return f"{lab} ({mid})"
    return mid


def parse_machine_display(display: str) -> tuple[str, Optional[str]]:
    """Parse ``Label (machine_id)`` → (machine_id, label)."""
    s = (display or "").strip()
    if not s:
        return UNKNOWN_ID, UNKNOWN_LABEL
    if s.endswith(")") and "(" in s:
        inner = s[s.rfind("(") + 1 : -1].strip()
        label = s[: s.rfind("(")].strip()
        if inner:
            return inner, label or None
    if s in {UNKNOWN_ID, UNKNOWN_LABEL}:
        return UNKNOWN_ID, UNKNOWN_LABEL
    return s, None
