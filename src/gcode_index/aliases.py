from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

from gcode_index.models import MachineInfo

_PUNCT_RE = re.compile(r"[^a-z0-9]+")


def normalize_folder_name(raw: str) -> str:
    """Lowercase, strip spaces/-/_, then strip remaining punctuation."""
    s = raw.strip().lower()
    s = s.replace(" ", "").replace("-", "").replace("_", "")
    s = _PUNCT_RE.sub("", s)
    return s


def default_aliases_path() -> Path:
    """Bundled aliases.yaml next to package, PyInstaller bundle, or repo root."""
    pkg = Path(__file__).resolve().parent
    candidates = [
        pkg / "data" / "aliases.yaml",
        pkg.parent.parent / "aliases.yaml",
        Path.cwd() / "aliases.yaml",
    ]
    # PyInstaller onedir/onefile: data files land under sys._MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        candidates = [
            meipass / "gcode_index" / "data" / "aliases.yaml",
            meipass / "aliases.yaml",
            *candidates,
        ]
    for c in candidates:
        if c.is_file():
            return c
    return pkg / "data" / "aliases.yaml"


class AliasMap:
    def __init__(self, machines: dict[str, dict[str, Any]]):
        self._machines = {normalize_folder_name(k): v for k, v in machines.items()}

    @classmethod
    def load(cls, path: Optional[Path | str] = None) -> "AliasMap":
        p = Path(path) if path else default_aliases_path()
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        machines = data.get("machines") or {}
        if not isinstance(machines, dict):
            raise ValueError(f"aliases file {p} must have a 'machines' mapping")
        return cls(machines)

    def resolve(self, machine_folder_raw: str) -> MachineInfo:
        key = normalize_folder_name(machine_folder_raw)
        entry = self._machines.get(key)
        if entry is None:
            return MachineInfo(
                machine_id=f"unmapped:{machine_folder_raw}",
                machine_folder_raw=machine_folder_raw,
                mapped=False,
            )
        return MachineInfo(
            machine_id=str(entry["machine_id"]),
            label=entry.get("label"),
            control_family=entry.get("control_family"),
            layout=entry.get("layout"),
            machine_folder_raw=machine_folder_raw,
            mapped=True,
        )
