"""Shared Toplevel chrome: fixed footer + optional scrollable body.

Packs the footer to ``BOTTOM`` first so Save / Cancel (or Close) stay visible
when content is tall or the window is near ``minsize``. Body either expands
as a plain frame (tree/list UIs that scroll themselves) or sits inside a
vertical Canvas when ``scrollable=True``.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Optional

# Sensible defaults for a ~1280×720 usable laptop desktop.
DEFAULT_MIN_WIDTH = 640
DEFAULT_MIN_HEIGHT = 420
DEFAULT_WIDTH = 720
DEFAULT_HEIGHT = 520


@dataclass(frozen=True)
class DialogShell:
    """Chrome pieces returned by :func:`install_dialog_shell`."""

    body: ttk.Frame
    footer: ttk.Frame
    canvas: Optional[tk.Canvas] = None


def dialog_geometry(
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> str:
    """Initial ``WxH`` geometry string (no position)."""
    return f"{int(width)}x{int(height)}"


def install_dialog_shell(
    win: tk.Toplevel,
    *,
    min_width: int = DEFAULT_MIN_WIDTH,
    min_height: int = DEFAULT_MIN_HEIGHT,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    scrollable: bool = False,
    padx: int = 12,
    pady: int = 12,
) -> DialogShell:
    """Apply minsize / geometry and return ``(body, footer)`` frames.

    Footer is always packed to the bottom first (never clipped by body growth).
    When ``scrollable`` is True, ``body`` is an inner frame inside a Canvas;
    otherwise ``body`` is a plain expanding frame.
    """
    win.minsize(int(min_width), int(min_height))
    win.geometry(dialog_geometry(width=width, height=height))

    footer = ttk.Frame(win)
    footer.pack(side=tk.BOTTOM, fill=tk.X, padx=padx, pady=pady)

    if not scrollable:
        body = ttk.Frame(win)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=padx, pady=(pady, 0))
        return DialogShell(body=body, footer=footer, canvas=None)

    outer = ttk.Frame(win)
    outer.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=padx, pady=(pady, 0))
    canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0)
    vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    body = ttk.Frame(canvas)
    window_id = canvas.create_window((0, 0), window=body, anchor=tk.NW)

    def _sync_scrollregion(_event=None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _stretch_inner(event) -> None:
        canvas.itemconfigure(window_id, width=max(int(event.width), 1))

    body.bind("<Configure>", _sync_scrollregion)
    canvas.bind("<Configure>", _stretch_inner)

    def _on_mousewheel(event) -> str:
        delta = getattr(event, "delta", 0) or 0
        if delta:
            canvas.yview_scroll(int(-1 * (delta / 120)), "units")
        else:
            num = getattr(event, "num", 0)
            if num == 4:
                canvas.yview_scroll(-1, "units")
            elif num == 5:
                canvas.yview_scroll(1, "units")
        return "break"

    def _bind_wheel(_event=None) -> None:
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)

    def _unbind_wheel(_event=None) -> None:
        try:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")
        except tk.TclError:
            pass

    # Bind wheel only while the pointer is over this dialog's scroll area.
    canvas.bind("<Enter>", _bind_wheel)
    canvas.bind("<Leave>", _unbind_wheel)
    body.bind("<Enter>", _bind_wheel)
    body.bind("<Leave>", _unbind_wheel)
    win.bind("<Destroy>", _unbind_wheel, add="+")

    return DialogShell(body=body, footer=footer, canvas=canvas)
