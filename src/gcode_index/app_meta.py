"""Resolve display version / build id for the GUI title bar."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from gcode_index import __version__


def _candidate_version_files() -> list[Path]:
    out: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        out.append(exe_dir / "VERSION.txt")
        # onedir/_internal layout sometimes keeps sibling VERSION at bundle root
        out.append(exe_dir.parent / "VERSION.txt")
    out.append(Path.cwd() / "VERSION.txt")
    here = Path(__file__).resolve().parent
    # Editable / repo: rarely present; build script writes next to the exe
    out.append(here.parents[1] / "VERSION.txt")
    return out


def _parse_version_file(path: Path) -> tuple[Optional[str], Optional[str]]:
    if not path.is_file():
        return None, None
    ver: Optional[str] = None
    build: Optional[str] = None
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip().casefold()
            val = val.strip()
            if key == "version" and val:
                ver = val
            elif key == "build" and val:
                build = val
    except OSError:
        return None, None
    return ver, build


def resolve_app_meta() -> tuple[str, Optional[str]]:
    """Return ``(version, build_id_or_None)``.

    Build id prefers ``VERSION.txt`` next to the frozen exe (written by
    ``scripts/build_windows.bat`` as ``b<N>``), then ``GCODE_INDEX_BUILD``.
    """
    env_build = (os.environ.get("GCODE_INDEX_BUILD") or "").strip() or None
    file_ver: Optional[str] = None
    file_build: Optional[str] = None
    for path in _candidate_version_files():
        file_ver, file_build = _parse_version_file(path)
        if file_ver or file_build:
            break
    version = (file_ver or __version__).strip()
    build = file_build or env_build
    return version, build


def format_version_build(*, version: Optional[str] = None, build: Optional[str] = None) -> str:
    """``0.2.40-b56`` or bare version when build is unknown."""
    ver, bld = resolve_app_meta()
    if version is not None:
        ver = version
    if build is not None:
        bld = build
    ver = (ver or __version__).strip()
    bld = (bld or "").strip()
    if bld:
        return f"{ver}-{bld}"
    return ver


def window_title(app_name: str) -> str:
    """Main window title including version-build stamp."""
    stamp = format_version_build()
    name = (app_name or "").strip() or "G-code Backup Indexer"
    return f"{name} — {stamp}"
