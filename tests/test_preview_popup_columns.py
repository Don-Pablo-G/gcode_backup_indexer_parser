"""Preview popup, column visibility, colour legend, language nav lock."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from gcode_index.i18n import t
from gcode_index.instance_ini import load_instance_ini, save_instance_ini


def test_preview_popup_and_columns_i18n():
    for lang in ("pl", "en"):
        assert t(lang, "preview_open")
        assert t(lang, "preview_window_title")
        assert t(lang, "columns_menu")
        assert t(lang, "columns_menu_title")
        assert t(lang, "colour_legend_roles")


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_preview_popup_columns_legend_and_lang_nav_lock(tmp_path: Path, monkeypatch):
    from tests.tk_util import require_working_tk

    require_working_tk()
    ini = tmp_path / "gcode-index.ini"
    save_instance_ini(
        ini,
        can_index=True,
        backup=str(tmp_path / "backup"),
        target=str(tmp_path / "db"),
        pelny_view="praca",
        hidden_columns=["location"],
    )
    monkeypatch.setenv("GCODE_INDEX_INI", str(ini))

    from gcode_index.gui import IndexerApp, RESULT_COLUMNS

    app = IndexerApp()
    try:
        if app._is_simple():
            app._can_index = True
            app._rebuild(app._snapshot_ui())
        assert not app._is_simple()
        assert app._pelny_view == "praca"
        assert "location" in app._hidden_columns
        visible = list(app.tree.cget("displaycolumns"))
        if visible == ("#all",) or visible == "#all":
            # ttk may report #all when all shown except we hid one — force apply
            app._apply_column_visibility()
            visible = list(app.tree.cget("displaycolumns"))
        assert "location" not in visible
        assert "program" in visible

        # Full-width results: no paned preview dock
        assert getattr(app, "_results_pane", None) is None
        assert not app._preview_widgets_alive()

        app._open_preview_popup()
        assert app._preview_widgets_alive()
        assert app._preview_win is not None
        app._close_preview_popup(persist=False)
        assert not app._preview_widgets_alive()

        app._set_column_visible("path", False)
        assert "path" in app._hidden_columns
        app._set_column_visible("path", True)
        assert "path" not in app._hidden_columns

        # Cannot hide the last visible column
        for col in RESULT_COLUMNS:
            if col != "program":
                app._hidden_columns.add(col)
        app._set_column_visible("program", False)
        assert "program" not in app._hidden_columns

        # Language change must not activate Indeks (ghost click guard)
        app._show_pelny_view("praca", force=True)
        assert app._pelny_view == "praca"
        snap_view = app._pelny_view
        app._set_language("en" if app._lang == "pl" else "pl", persist=False)
        # Simulate ghost Indeks click during the idle gap
        app._show_pelny_view("indeks")
        assert app._pelny_view == snap_view  # ignored while lang_switching
        app.update_idletasks()
        app.update()
        assert app._pelny_view == "praca"
        # Post-rebuild nav ignore absorbs click-through
        app._show_pelny_view("indeks")
        assert app._pelny_view == "praca"
        # After ignore window, real switch works
        app._nav_ignore_until = 0.0
        app._clear_nav_ignore()
        app._show_pelny_view("indeks")
        assert app._pelny_view == "indeks"

        # Persist hidden columns + preview geometry into ini
        app._hidden_columns = {"control", "type"}
        app._preview_geometry = "700x500+10+10"
        app._save_instance_ini()
        loaded = load_instance_ini(ini)
        assert set(loaded.hidden_columns) == {"control", "type"}
        assert loaded.preview_geometry == "700x500+10+10"
    finally:
        try:
            app._close_preview_popup(persist=False)
        except Exception:  # noqa: BLE001
            pass
        app.destroy()
