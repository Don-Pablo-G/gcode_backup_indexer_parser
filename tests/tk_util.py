"""Helpers for optional Tk GUI tests (skip when Tcl/Tk cannot initialize)."""

from __future__ import annotations

import os

import pytest


def require_working_tk():
    """Import tkinter and prove a root can be created; skip otherwise.

    GitHub ``windows-latest`` Python often ships a broken Tcl (``tcl_findLibrary``)
    even though ``import tkinter`` succeeds — so DISPLAY/nt checks are not enough.
    """
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
    except tk.TclError as exc:
        pytest.skip(f"Tk/Tcl not usable in this environment: {exc}")
    return tk


def skip_without_display_or_working_tk():
    """Skip on headless Linux; on Windows still require a working Tk."""
    if not os.environ.get("DISPLAY") and os.name != "nt":
        pytest.skip("No DISPLAY for Tk on this Linux host")
    return require_working_tk()
