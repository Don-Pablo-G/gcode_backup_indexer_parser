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


def windows_explorer_select_params(path: Path | str) -> str:
    """Build ``explorer.exe`` parameters that reveal ``path`` (spaces-safe).

    Explorer parses its *raw* command line. Passing a single argv
    ``/select,C:\\path with spaces\\file`` via ``subprocess`` list form makes
    ``list2cmdline`` wrap the whole token in quotes; Explorer then ignores it
    and silently opens Documents. Quote **only** the path:
    ``/select,"C:\\path with spaces\\file"``.
    """
    win = os.path.normpath(str(path)).replace("/", "\\")
    # A trailing backslash would escape the closing quote.
    if len(win) >= 2 and win.endswith("\\") and not win.endswith(":\\"):
        win = win.rstrip("\\")
    win = win.replace('"', "")
    return f'/select,"{win}"'


def _windows_shell_execute_explorer(params: str) -> None:
    """Launch ``explorer.exe`` with raw ``params`` (for tests to monkeypatch)."""
    import ctypes

    rc = int(
        ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None, "open", "explorer.exe", params, None, 1
        )
    )
    if rc <= 32:
        raise OSError(f"ShellExecute explorer failed ({rc})")


def open_path_in_file_manager(path: Path) -> None:
    """Reveal ``path`` in the OS file manager (select file when possible)."""
    path = path.resolve()
    if sys.platform == "win32":
        params = windows_explorer_select_params(path)
        # ShellExecuteW passes lpParameters verbatim (no list2cmdline wrapping).
        try:
            _windows_shell_execute_explorer(params)
            return
        except (AttributeError, OSError, ValueError):
            # Fallback: open the parent folder (argv quoting handles spaces).
            target = path if path.is_dir() else path.parent
            subprocess.Popen(  # noqa: S603
                ["explorer", os.path.normpath(str(target))]
            )
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
