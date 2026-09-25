"""Path / shell helpers shared by GUI (and tests) without requiring tkinter."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

from gcode_index.path_remap import RemapInput, apply_path_remaps, remap_root


def resolve_source_abspath(
    source_path: str,
    backup_root: Optional[str] = None,
    scan_root: Optional[str] = None,
    path_remaps: Optional[Sequence[RemapInput]] = None,
) -> Path:
    """Turn a relative or absolute indexed ``source_path`` into an absolute Path.

    Prefer ``scan_root`` (per-instance root for multi-folder scans), then ``backup_root``.
    Optional ``path_remaps`` rewrite drive/share prefixes (client C:→Z:).
    """
    scan = remap_root(scan_root, path_remaps)
    backup = remap_root(backup_root, path_remaps)
    raw = str(source_path or "")
    # Treat Windows drive paths as absolute even when tests run on POSIX.
    is_win_abs = len(raw) >= 2 and raw[1] == ":"
    if Path(raw).is_absolute() or is_win_abs:
        return Path(apply_path_remaps(raw, path_remaps))
    base = scan or backup
    if base:
        return Path(base) / raw
    return Path(raw).resolve()


def source_exists_on_disk(
    source_path: str,
    backup_root: Optional[str] = None,
    scan_root: Optional[str] = None,
    path_remaps: Optional[Sequence[RemapInput]] = None,
) -> bool:
    """True when the indexed source path resolves to an existing file on disk."""
    raw = str(source_path or "").strip()
    if not raw:
        return False
    try:
        path = resolve_source_abspath(
            raw,
            backup_root,
            scan_root,
            path_remaps=path_remaps,
        )
        return path.is_file()
    except OSError:
        return False


def open_path_in_file_manager(path: Path) -> None:
    """Reveal ``path`` in the OS file manager (select file when possible)."""
    path = path.resolve()
    if sys.platform == "win32":
        # explorer /select,<path> highlights the file in its folder
        subprocess.Popen(["explorer", f"/select,{path}"])  # noqa: S603
        return
    if sys.platform == "darwin":
        if path.is_file():
            subprocess.Popen(["open", "-R", str(path)])  # noqa: S603
        else:
            subprocess.Popen(["open", str(path if path.is_dir() else path.parent)])  # noqa: S603
        return
    # Linux / other: open containing folder (xdg-open cannot select)
    target = path if path.is_dir() else path.parent
    opener = "xdg-open" if os.name != "nt" else "explorer"
    subprocess.Popen([opener, str(target)])  # noqa: S603


def format_eta(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    s = max(0, int(seconds))
    if s < 60:
        return f"~{s}s left"
    m, rem = divmod(s, 60)
    if m < 60:
        return f"~{m}m {rem}s left"
    h, m = divmod(m, 60)
    return f"~{h}h {m}m left"
