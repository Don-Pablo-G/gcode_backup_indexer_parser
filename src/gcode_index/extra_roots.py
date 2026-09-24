"""Persist optional extra scan-root folders next to the index database."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

EXTRA_ROOTS_FILENAME = "extra_scan_roots.yaml"


def extra_roots_path_for_target(target: Path | str) -> Path:
    return Path(target) / EXTRA_ROOTS_FILENAME


def load_extra_roots(path: Path | str) -> list[str]:
    p = Path(path)
    if not p.is_file():
        return []
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if isinstance(data, list):
        roots = data
    elif isinstance(data, dict):
        roots = data.get("roots") or data.get("extra_roots") or []
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in roots:
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def save_extra_roots(path: Path | str, roots: Iterable[str]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in roots:
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        cleaned.append(s)
    payload: dict[str, Any] = {
        "roots": cleaned,
        "_comment": (
            "Extra folders scanned in addition to the main backup. "
            "Programs from these roots are tagged provenance=extra (yellow flag)."
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


def normalize_extra_roots(
    roots: Iterable[str],
    *,
    backup_root: Optional[str] = None,
) -> list[Path]:
    """Drop missing / duplicate / same-as-backup paths; return existing dirs."""
    out: list[Path] = []
    seen: set[str] = set()
    bak = None
    if backup_root:
        try:
            bak = str(Path(backup_root).resolve())
            seen.add(bak)
        except OSError:
            bak = str(backup_root)
            seen.add(bak)
    for raw in roots:
        p = Path(str(raw).strip())
        if not p.is_dir():
            continue
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out
