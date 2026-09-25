"""Persist optional extra scan-root folders next to the index database.

Each root carries a provenance flag:
- ``backup`` (green) — treat like machine/backup (loose .nc catch folders)
- ``extra`` (yellow) — additional folders not from the machine backup

Legacy ``extra_scan_roots.yaml`` with a plain string list is still loaded as yellow.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Union

import yaml

from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA, PROVENANCE_VALUES

EXTRA_ROOTS_FILENAME = "extra_scan_roots.yaml"

RootInput = Union[str, Path, "ScanRootSpec", dict[str, Any]]


@dataclass(frozen=True)
class ScanRootSpec:
    """One additional folder to scan with an explicit green/yellow flag."""

    path: str
    provenance: str = PROVENANCE_EXTRA

    def __post_init__(self) -> None:
        prov = (self.provenance or PROVENANCE_EXTRA).strip().casefold()
        if prov in ("green", "backup", "machine", "ran"):
            object.__setattr__(self, "provenance", PROVENANCE_BACKUP)
        elif prov in ("yellow", "extra", "other"):
            object.__setattr__(self, "provenance", PROVENANCE_EXTRA)
        elif prov not in PROVENANCE_VALUES:
            object.__setattr__(self, "provenance", PROVENANCE_EXTRA)


def extra_roots_path_for_target(target: Path | str) -> Path:
    return Path(target) / EXTRA_ROOTS_FILENAME


def _coerce_spec(item: Any) -> Optional[ScanRootSpec]:
    if item is None:
        return None
    if isinstance(item, ScanRootSpec):
        path = str(item.path).strip()
        if not path:
            return None
        return ScanRootSpec(path=path, provenance=item.provenance)
    if isinstance(item, (str, Path)):
        path = str(item).strip()
        if not path:
            return None
        return ScanRootSpec(path=path, provenance=PROVENANCE_EXTRA)
    if isinstance(item, dict):
        path = str(item.get("path") or item.get("root") or "").strip()
        if not path:
            return None
        prov = item.get("provenance") or item.get("flag") or PROVENANCE_EXTRA
        return ScanRootSpec(path=path, provenance=str(prov))
    return None


def load_scan_roots(path: Path | str) -> list[ScanRootSpec]:
    """Load typed scan roots (green + yellow)."""
    p = Path(path)
    if not p.is_file():
        return []
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw_items: list[Any] = []
    if isinstance(data, list):
        raw_items = list(data)
    elif isinstance(data, dict):
        roots = data.get("roots") or data.get("extra_roots") or []
        if isinstance(roots, list):
            raw_items.extend(roots)
        # Optional dedicated green list (also accepted on load)
        greens = data.get("green_roots") or data.get("backup_roots") or []
        if isinstance(greens, list):
            for g in greens:
                if isinstance(g, (str, Path)):
                    raw_items.append({"path": str(g), "provenance": PROVENANCE_BACKUP})
                else:
                    raw_items.append(g)
    out: list[ScanRootSpec] = []
    seen: set[str] = set()
    for item in raw_items:
        spec = _coerce_spec(item)
        if spec is None:
            continue
        key = spec.path.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(spec)
    return out


def load_extra_roots(path: Path | str) -> list[str]:
    """Backward-compatible: paths only (all roots, any flag)."""
    return [s.path for s in load_scan_roots(path)]


def save_scan_roots(path: Path | str, roots: Iterable[RootInput]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in roots:
        spec = _coerce_spec(item)
        if spec is None:
            continue
        key = spec.path.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({"path": spec.path, "provenance": spec.provenance})
    payload: dict[str, Any] = {
        "roots": cleaned,
        "_comment": (
            "Additional folders scanned with the main backup. "
            "provenance=backup → green flag (treat as on-machine / catch .nc); "
            "provenance=extra → yellow flag (not from machine backup)."
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


def save_extra_roots(path: Path | str, roots: Iterable[str]) -> Path:
    """Backward-compatible writer: all paths saved as yellow (extra)."""
    return save_scan_roots(
        path, [ScanRootSpec(path=str(r), provenance=PROVENANCE_EXTRA) for r in roots]
    )


def normalize_scan_roots(
    roots: Iterable[RootInput],
    *,
    backup_root: Optional[str] = None,
) -> list[tuple[Path, str]]:
    """Return ``(path, provenance)`` for existing unique dirs (not the backup root)."""
    out: list[tuple[Path, str]] = []
    seen: set[str] = set()
    if backup_root:
        try:
            seen.add(str(Path(backup_root).resolve()))
        except OSError:
            seen.add(str(backup_root))
    for item in roots:
        spec = _coerce_spec(item)
        if spec is None:
            continue
        p = Path(spec.path)
        if not p.is_dir():
            continue
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append((p, spec.provenance))
    return out


def normalize_extra_roots(
    roots: Iterable[str],
    *,
    backup_root: Optional[str] = None,
) -> list[Path]:
    """Legacy helper: yellow-only paths as ``Path`` list."""
    specs = [ScanRootSpec(path=str(r), provenance=PROVENANCE_EXTRA) for r in roots]
    return [p for p, _prov in normalize_scan_roots(specs, backup_root=backup_root)]


def format_root_label(spec: ScanRootSpec, *, green_tag: str, yellow_tag: str) -> str:
    tag = green_tag if spec.provenance == PROVENANCE_BACKUP else yellow_tag
    return f"{tag}  {spec.path}"


def parse_root_label(label: str) -> Optional[ScanRootSpec]:
    """Parse a listbox label produced by ``format_root_label``."""
    raw = (label or "").strip()
    if not raw:
        return None
    # "🟢  path" / "[G]  path" / "zielona  path"
    parts = raw.split(None, 1)
    if len(parts) == 1:
        return ScanRootSpec(path=parts[0], provenance=PROVENANCE_EXTRA)
    tag, path = parts[0].strip().casefold(), parts[1].strip()
    if tag in ("🟢", "[g]", "g", "green", "zielona", "backup"):
        return ScanRootSpec(path=path, provenance=PROVENANCE_BACKUP)
    if tag in ("🟡", "[y]", "y", "yellow", "żółta", "zolta", "extra"):
        return ScanRootSpec(path=path, provenance=PROVENANCE_EXTRA)
    # Unknown tag — treat whole string as path (yellow)
    return ScanRootSpec(path=raw, provenance=PROVENANCE_EXTRA)
