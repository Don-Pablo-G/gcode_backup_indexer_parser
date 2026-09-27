"""Dialog shell chrome + status-coloured Add button swatches."""

from __future__ import annotations

import os

import pytest

from gcode_index.badge_style import STATUS_SWATCH
from gcode_index.dialog_shell import (
    DEFAULT_HEIGHT,
    DEFAULT_MIN_HEIGHT,
    DEFAULT_MIN_WIDTH,
    DEFAULT_WIDTH,
    dialog_geometry,
)
from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA
from gcode_index.ui_theme import (
    UI_STATUS_GREEN,
    UI_STATUS_GREEN_TEXT,
    UI_STATUS_YELLOW,
    UI_STATUS_YELLOW_TEXT,
)


def test_status_button_colours_match_flag_discs():
    assert UI_STATUS_GREEN == STATUS_SWATCH[PROVENANCE_BACKUP]
    assert UI_STATUS_YELLOW == STATUS_SWATCH[PROVENANCE_EXTRA]
    assert UI_STATUS_GREEN_TEXT.startswith("#")
    assert UI_STATUS_YELLOW_TEXT.startswith("#")
    # Readable contrast: green uses light text; amber uses dark text.
    assert UI_STATUS_GREEN_TEXT.upper() == "#FFFFFF"
    assert UI_STATUS_YELLOW_TEXT.lower() != "#ffffff"


def test_dialog_geometry_defaults():
    assert dialog_geometry() == f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}"
    assert dialog_geometry(width=800, height=600) == "800x600"
    assert DEFAULT_MIN_WIDTH >= 480
    assert DEFAULT_MIN_HEIGHT >= 280
    assert DEFAULT_WIDTH >= DEFAULT_MIN_WIDTH
    assert DEFAULT_HEIGHT >= DEFAULT_MIN_HEIGHT


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_install_dialog_shell_footer_first():
    from tests.tk_util import require_working_tk

    require_working_tk()
    import tkinter as tk
    from tkinter import ttk

    from gcode_index.dialog_shell import install_dialog_shell

    root = tk.Tk()
    root.withdraw()
    try:
        win = tk.Toplevel(root)
        shell = install_dialog_shell(
            win,
            min_width=500,
            min_height=360,
            width=560,
            height=400,
            scrollable=False,
        )
        ttk.Label(shell.body, text="body").pack()
        ttk.Button(shell.footer, text="Save").pack(side=tk.RIGHT)
        win.update_idletasks()
        assert int(win.winfo_reqwidth()) >= 1
        # Footer reserved at bottom; body expands above it.
        assert shell.footer.winfo_manager() == "pack"
        assert str(shell.footer.pack_info().get("side", "")) == "bottom"
        assert shell.canvas is None
        geom = win.geometry()
        assert geom.startswith("560x400")
        assert win.minsize() == (500, 360)
    finally:
        root.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_install_dialog_shell_scrollable_body():
    from tests.tk_util import require_working_tk

    require_working_tk()
    import tkinter as tk
    from tkinter import ttk

    from gcode_index.dialog_shell import install_dialog_shell

    root = tk.Tk()
    root.withdraw()
    try:
        win = tk.Toplevel(root)
        shell = install_dialog_shell(win, scrollable=True)
        for i in range(40):
            ttk.Label(shell.body, text=f"row {i}").pack(anchor=tk.W)
        ttk.Button(shell.footer, text="Cancel").pack(side=tk.RIGHT)
        win.update_idletasks()
        assert shell.canvas is not None
        assert str(shell.footer.pack_info().get("side", "")) == "bottom"
    finally:
        root.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_add_status_buttons_use_disc_colours(tmp_path, monkeypatch):
    from tests.tk_util import require_working_tk

    require_working_tk()
    from gcode_index.instance_ini import save_instance_ini

    ini = tmp_path / "gcode-index.ini"
    save_instance_ini(
        ini,
        can_index=True,
        backup=str(tmp_path / "backup"),
        target=str(tmp_path / "db"),
    )
    monkeypatch.setenv("GCODE_INDEX_INI", str(ini))
    from gcode_index.gui import IndexerApp
    import tkinter as tk

    app = IndexerApp()
    try:
        if app._is_simple():
            app._can_index = True
            app._rebuild(app._snapshot_ui())
        app._show_pelny_view("indeks", force=True)
        # Expand folders so Add green/yellow exist
        if hasattr(app, "_set_folders_expanded"):
            app._set_folders_expanded(True)
        app.update_idletasks()

        greens: list[tk.Button] = []
        yellows: list[tk.Button] = []

        def walk(w):
            for child in w.winfo_children():
                if isinstance(child, tk.Button):
                    try:
                        text = str(child.cget("text"))
                        bg = str(child.cget("bg")).upper()
                    except tk.TclError:
                        continue
                    if text == app._("add_green_folder"):
                        greens.append(child)
                        assert bg == UI_STATUS_GREEN.upper()
                    elif text == app._("add_yellow_folder"):
                        yellows.append(child)
                        assert bg == UI_STATUS_YELLOW.upper()
                walk(child)

        walk(app)
        assert greens, "Add green button not found"
        assert yellows, "Add yellow button not found"
    finally:
        app.destroy()
