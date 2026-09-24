from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

from gcode_index.models import MachineInfo

_PUNCT_RE = re.compile(r"[^a-z0-9]+")

LOCAL_ALIASES_FILENAME = "aliases.local.yaml"


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


def local_aliases_path_for_target(target: Path | str) -> Path:
    """Shop-local alias overlay stored next to the index database."""
    return Path(target) / LOCAL_ALIASES_FILENAME


# Substring / prefix fallbacks (avoid tiny keys like "sl" matching both SL-10 and SL-20).
_MIN_SUBSTRING_ALIAS_LEN = 4
_MIN_PREFIX_ALIAS_LEN = 3


def _machines_from_yaml_data(data: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(data, dict):
        return {}
    machines = data.get("machines") or {}
    if not isinstance(machines, dict):
        raise ValueError("aliases file must have a 'machines' mapping")
    return {str(k): dict(v) if isinstance(v, dict) else {"machine_id": str(v)} for k, v in machines.items()}


class AliasMap:
    def __init__(
        self,
        machines: dict[str, dict[str, Any]],
        *,
        local_keys: Optional[set[str]] = None,
        local_raw: Optional[dict[str, dict[str, Any]]] = None,
    ):
        # Normalized key → entry (merged view used for resolve)
        self._machines = {normalize_folder_name(k): v for k, v in machines.items()}
        # Keys that came from the local overlay (normalized)
        self._local_keys: set[str] = set(local_keys or ())
        # Raw spelling → entry for local file round-trip (preserve folder spelling as key)
        self._local_raw: dict[str, dict[str, Any]] = dict(local_raw or {})

    @classmethod
    def load(cls, path: Optional[Path | str] = None) -> "AliasMap":
        p = Path(path) if path else default_aliases_path()
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        machines = _machines_from_yaml_data(data)
        return cls(machines)

    @classmethod
    def load_merged(
        cls,
        bundled: Optional[Path | str] = None,
        local: Optional[Path | str] = None,
    ) -> "AliasMap":
        """Load bundled aliases, then overlay shop-local aliases (local wins)."""
        base = cls.load(bundled)
        local_path = Path(local) if local else None
        if local_path is None or not local_path.is_file():
            return base
        with local_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        local_raw = _machines_from_yaml_data(data)
        if not local_raw:
            return base
        merged = dict(base._machines)
        local_keys: set[str] = set()
        for raw_key, entry in local_raw.items():
            nk = normalize_folder_name(raw_key)
            merged[nk] = entry
            local_keys.add(nk)
        return cls(merged, local_keys=local_keys, local_raw=local_raw)

    def with_local_file(self, local: Optional[Path | str]) -> "AliasMap":
        """Return a new map with ``local`` aliases overlaid (no-op if missing)."""
        if local is None:
            return self
        local_path = Path(local)
        if not local_path.is_file():
            return self
        with local_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        local_raw = _machines_from_yaml_data(data)
        if not local_raw:
            return self
        merged = dict(self._machines)
        local_keys = set(self._local_keys)
        combined_raw = dict(self._local_raw)
        for raw_key, entry in local_raw.items():
            nk = normalize_folder_name(raw_key)
            merged[nk] = entry
            local_keys.add(nk)
            combined_raw[raw_key] = entry
        return AliasMap(merged, local_keys=local_keys, local_raw=combined_raw)

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

    def add_local_alias(
        self,
        folder_raw: str,
        machine_id: str,
        *,
        label: Optional[str] = None,
        control_family: Optional[str] = None,
        layout: Optional[str] = None,
    ) -> None:
        """Add/update a shop-local alias keyed by the folder name spelling."""
        raw = str(folder_raw).strip()
        mid = str(machine_id).strip()
        if not raw or not mid or mid == "unknown" or mid.startswith("unmapped:"):
            return
        # Prefer catalog metadata when available
        catalog = self.info_for_machine_id(mid, raw)
        entry: dict[str, Any] = {"machine_id": mid}
        lab = (label or (catalog.label if catalog else None) or "").strip()
        if lab:
            entry["label"] = lab
        cf = control_family or (catalog.control_family if catalog else None)
        if cf:
            entry["control_family"] = cf
        lay = layout or (catalog.layout if catalog else None)
        if lay:
            entry["layout"] = lay
        nk = normalize_folder_name(raw)
        self._machines[nk] = entry
        self._local_keys.add(nk)
        # Drop prior local raw keys that normalize to the same spelling
        for old in list(self._local_raw):
            if normalize_folder_name(old) == nk:
                del self._local_raw[old]
        self._local_raw[raw] = entry

    def save_local(self, path: Path | str) -> Path:
        """Write only shop-local aliases (does not touch bundled aliases.yaml)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        machines: dict[str, Any] = {}
        for raw, entry in sorted(self._local_raw.items(), key=lambda kv: kv[0].casefold()):
            machines[raw] = dict(entry)
        payload = {
            "machines": machines,
            "_comment": "Shop-local aliases for this index target. Overlay on bundled aliases.yaml.",
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

    @property
    def local_alias_count(self) -> int:
        return len(self._local_raw)
