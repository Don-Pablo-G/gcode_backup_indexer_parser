"""Indeks thin bar + Mapowanie / Skan i obserwacja / Raporty settings windows."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gcode_index.i18n import STRINGS, t
from gcode_index.instance_ini import save_instance_ini


DOOR_KEYS = (
    "indeks_door_mapping",
    "indeks_door_scan_watch",
    "indeks_door_reports",
    "indeks_win_mapping_title",
    "indeks_win_scan_watch_title",
    "indeks_win_reports_title",
)


def test_indeks_doorway_i18n_parity():
    pl = set(STRINGS["pl"])
    en = set(STRINGS["en"])
    for key in DOOR_KEYS:
        assert key in pl and key in en
    assert t("pl", "indeks_door_mapping") == "Mapowanie…"
    assert t("en", "indeks_door_mapping") == "Mapping…"
    assert t("pl", "indeks_door_scan_watch") == "Skan i obserwacja…"
    assert t("en", "indeks_door_scan_watch") == "Scan & watch…"
    assert t("pl", "indeks_door_reports") == "Raporty…"
    assert t("en", "indeks_door_reports") == "Reports…"
    assert t("pl", "run_scan") == "Uruchom skan"
    assert "✓" not in t("pl", "run_scan")  # sanity


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_indeks_bar_has_doorways_no_checkboxes(tmp_path: Path, monkeypatch):
    from tests.tk_util import require_working_tk

    require_working_tk()
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
    from tkinter import ttk

    app = IndexerApp()
    try:
        if app._is_simple():
            app._can_index = True
            app._rebuild(app._snapshot_ui())
        app._show_pelny_view("indeks", force=True)
        assert app._actions_frame is not None
        # Collect button labels under actions
        labels: list[str] = []
        check_count = 0

        def walk(w):
            nonlocal check_count
            for child in w.winfo_children():
                if isinstance(child, ttk.Checkbutton) or isinstance(child, tk.Checkbutton):
                    check_count += 1
                try:
                    text = str(child.cget("text"))
                except tk.TclError:
                    text = ""
                if text:
                    labels.append(text)
                walk(child)

        walk(app._actions_frame)
        assert check_count == 0, "Indeks bar must not show checkboxes"
        assert app._("indeks_door_mapping") in labels
        assert app._("indeks_door_scan_watch") in labels
        assert app._("indeks_door_reports") in labels
        assert app._("run_scan") in labels
        assert app._("prepare_indexer") in labels
        # Clear filters stays on Praca find bar, not Indeks actions
        assert app._("clear_filters") not in labels
    finally:
        app.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_indeks_settings_windows_open(tmp_path: Path, monkeypatch):
    from tests.tk_util import require_working_tk

    require_working_tk()
    ini = tmp_path / "gcode-index.ini"
    save_instance_ini(
        ini,
        can_index=True,
        backup=str(tmp_path / "backup"),
        target=str(tmp_path / "db"),
    )
    monkeypatch.setenv("GCODE_INDEX_INI", str(ini))
    from gcode_index.gui import IndexerApp

    app = IndexerApp()
    try:
        if app._is_simple():
            app._can_index = True
            app._rebuild(app._snapshot_ui())
        app._show_pelny_view("indeks", force=True)
        app._open_indeks_mapping_window()
        app.update()
        app._open_indeks_scan_watch_window()
        app.update()
        app._open_indeks_reports_window()
        app.update()
        # Destroy open toplevels
        for w in list(app.winfo_children()):
            try:
                if w.winfo_class() == "Toplevel":
                    w.destroy()
            except Exception:
                pass
    finally:
        app.destroy()
