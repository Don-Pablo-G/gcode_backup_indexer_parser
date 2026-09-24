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


# Substring / prefix fallbacks (avoid tiny keys like "sl" matching both SL-10 and SL-20).
_MIN_SUBSTRING_ALIAS_LEN = 4
_MIN_PREFIX_ALIAS_LEN = 3


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

    def _info_from_entry(self, entry: dict[str, Any], machine_folder_raw: str) -> MachineInfo:
        return MachineInfo(
            machine_id=str(entry["machine_id"]),
            label=entry.get("label"),
            control_family=entry.get("control_family"),
            layout=entry.get("layout"),
            machine_folder_raw=machine_folder_raw,
            mapped=True,
        )

    def _lookup_fuzzy(self, key: str) -> Optional[dict[str, Any]]:
        """Longest alias contained in key, else longest alias that is a prefix of key."""
        best_key = ""
        for ak in self._machines:
            if len(ak) < _MIN_SUBSTRING_ALIAS_LEN:
                continue
            if ak in key and len(ak) > len(best_key):
                best_key = ak
        if best_key:
            return self._machines[best_key]

        # Prefix: "VF2S" / "VF2 old" → vf2; prefer longer (vf2nowa before vf2)
        best_key = ""
        for ak in self._machines:
            if len(ak) < _MIN_PREFIX_ALIAS_LEN:
                continue
            if key.startswith(ak) and len(ak) > len(best_key):
                best_key = ak
        if best_key:
            return self._machines[best_key]
        return None

    def resolve(self, machine_folder_raw: str) -> MachineInfo:
        key = normalize_folder_name(machine_folder_raw)
        entry = self._machines.get(key)
        if entry is None:
            entry = self._lookup_fuzzy(key)
        if entry is None:
            return MachineInfo(
                machine_id=f"unmapped:{machine_folder_raw}",
                machine_folder_raw=machine_folder_raw,
                mapped=False,
            )
        return self._info_from_entry(entry, machine_folder_raw)

    def known_machine_displays(self) -> list[str]:
        """Unique ``Label (machine_id)`` strings for GUI filters (alias catalog)."""
        seen: set[str] = set()
        out: list[str] = []
        rows: list[tuple[str, str]] = []
        for entry in self._machines.values():
            mid = str(entry.get("machine_id") or "").strip()
            if not mid or mid in seen:
                continue
            seen.add(mid)
            label = str(entry.get("label") or "").strip()
            rows.append((label or mid, mid))
        rows.sort(key=lambda t: t[0].casefold())
        for label, mid in rows:
            display = f"{label} ({mid})" if label and label != mid else mid
            out.append(display)
        return out

    def info_for_machine_id(
        self,
        machine_id: str,
        machine_folder_raw: str,
    ) -> Optional[MachineInfo]:
        """Look up catalog fields (label/control/layout) by ``machine_id``."""
        mid = str(machine_id or "").strip()
        if not mid:
            return None
        for entry in self._machines.values():
            if str(entry.get("machine_id") or "").strip() == mid:
                return self._info_from_entry(entry, machine_folder_raw)
        return None
