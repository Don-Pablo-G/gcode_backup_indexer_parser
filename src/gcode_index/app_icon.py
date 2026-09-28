"""Resolve packaged app icon paths (ICO + PNG sizes) for window / tray / About."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Preferred PNG sizes we ship under ``gcode_index/data/``.
_PNG_SIZES = (16, 32, 64, 128, 256)


def _package_data_dir() -> Path:
    return Path(__file__).resolve().parent / "data"


def _candidate_roots() -> list[Path]:
    """Dirs that may contain ``app.ico`` / ``app-N.png``."""
    roots: list[Path] = []
    pkg_data = _package_data_dir()
    roots.append(pkg_data)
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass) / "gcode_index" / "data")
            roots.append(Path(meipass) / "data")
        exe_dir = Path(sys.executable).resolve().parent
        roots.append(exe_dir / "_internal" / "gcode_index" / "data")
        roots.append(exe_dir / "gcode_index" / "data")
        roots.append(exe_dir)
    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def resolve_app_ico() -> Optional[Path]:
    """Multi-size Windows ICO used for the exe and ``iconbitmap``."""
    for root in _candidate_roots():
        path = root / "app.ico"
        if path.is_file():
            return path
    return None


def resolve_app_png(size: int) -> Optional[Path]:
    """Exact ``app-{size}.png`` if present."""
    name = f"app-{size}.png"
    for root in _candidate_roots():
        path = root / name
        if path.is_file():
            return path
    return None


def resolve_best_png(*prefer: int) -> Optional[Path]:
    """First existing PNG among ``prefer``, then any shipped size (largest last)."""
    order = list(prefer) + [s for s in _PNG_SIZES if s not in prefer]
    for size in order:
        path = resolve_app_png(size)
        if path is not None:
            return path
    return None


def apply_tk_window_icon(root) -> None:
    """Set the Tk window / taskbar icon from packaged assets.

    Keeps a PhotoImage reference on ``root`` so Tk does not GC the image.
    Failures are silent — default Tk icon is acceptable as fallback.
    """
    import tkinter as tk

    ico = resolve_app_ico()
    if ico is not None and sys.platform == "win32":
        try:
            root.iconbitmap(default=str(ico))
        except tk.TclError:
            try:
                root.iconbitmap(str(ico))
            except tk.TclError:
                pass

    png = resolve_best_png(32, 64, 256, 128, 16)
    if png is None:
        return
    photo = None
    try:
        from PIL import Image, ImageTk

        im = Image.open(png).convert("RGBA")
        photo = ImageTk.PhotoImage(im, master=root)
    except Exception:  # noqa: BLE001
        try:
            photo = tk.PhotoImage(file=str(png), master=root)
        except tk.TclError:
            photo = None
    if photo is None:
        return
    try:
        root.iconphoto(True, photo)
        # Prevent GC of the PhotoImage
        root._gcode_app_icon_photo = photo  # type: ignore[attr-defined]
    except tk.TclError:
        pass
