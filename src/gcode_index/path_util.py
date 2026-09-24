"""Path / shell helpers shared by GUI (and tests) without requiring tkinter."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def resolve_source_abspath(source_path: str, backup_root: Optional[str]) -> Path:
    """Turn a relative or absolute indexed ``source_path`` into an absolute Path."""
    p = Path(source_path)
    if p.is_absolute():
        return p
    if backup_root:
        return Path(backup_root) / p
    return p.resolve()


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
