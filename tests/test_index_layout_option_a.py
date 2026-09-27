"""Indexer Indeks Option A: no remap in folders, discs, scan-order bar."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gcode_index.badge_style import DOT_LARGE, STATUS_SWATCH
from gcode_index.extra_roots import (
    ScanRootSpec,
    format_root_label,
    parse_root_label,
)
from gcode_index.i18n import STRINGS, t
from gcode_index.instance_ini import save_instance_ini
from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA


def test_tag_i18n_uses_flag_disc():
    assert t("pl", "tag_green") == DOT_LARGE
    assert t("pl", "tag_yellow") == DOT_LARGE
    assert t("en", "tag_green") == DOT_LARGE
    assert "indeks_step_config" in STRINGS["pl"]
    assert "indeks_step_run" in STRINGS["en"]
    assert t("pl", "folders_step").startswith("1")
    assert t("pl", "indeks_step_config").startswith("2")
    assert t("pl", "indeks_step_run").startswith("3")


def test_format_root_label_uses_disc_not_brackets():
    green = format_root_label(
        ScanRootSpec(path=r"D:\catch", provenance=PROVENANCE_BACKUP),
        green_tag="[G]",
        yellow_tag="[Y]",
    )
    yellow = format_root_label(
        ScanRootSpec(path=r"D:\extra", provenance=PROVENANCE_EXTRA),
        green_tag="[G]",
        yellow_tag="[Y]",
    )
    assert green.startswith(DOT_LARGE)
    assert yellow.startswith(DOT_LARGE)
    assert "[G]" not in green and "[Y]" not in yellow
    assert r"D:\catch" in green
    # Legacy bracket labels still parse
    assert parse_root_label("[G]  D:\\old").provenance == PROVENANCE_BACKUP
    assert parse_root_label("[Y]  D:\\old").provenance == PROVENANCE_EXTRA


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_indexer_folders_drop_remap_grow_extras_scan_right(tmp_path: Path, monkeypatch):
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
        app._set_folders_expanded(True)
        app.update_idletasks()

        # Indexer folders expander must NOT host path remap
        assert hasattr(app, "_folders_expanded_frame")
        frame_text = str(app._folders_expanded_frame.cget("text"))
        assert frame_text == app._("folders_step")
        remap_label = app._("path_remap")
        found_remap_in_folders = False

        def walk_folders(w):
            nonlocal found_remap_in_folders
            for child in w.winfo_children():
                try:
                    text = str(child.cget("text"))
                except tk.TclError:
                    text = ""
                if text == remap_label:
                    found_remap_in_folders = True
                walk_folders(child)

        walk_folders(app._folders_expanded_frame)
        assert not found_remap_in_folders

        # Extras list taller + coloured discs
        assert hasattr(app, "extra_list")
        assert int(app.extra_list.cget("height")) >= 6
        specs = [
            ScanRootSpec(path=str(tmp_path / "g"), provenance=PROVENANCE_BACKUP),
            ScanRootSpec(path=str(tmp_path / "y"), provenance=PROVENANCE_EXTRA),
        ]
        app._fill_extra_list(specs)
        assert app.extra_list.size() == 2
        assert DOT_LARGE in app.extra_list.get(0)
        assert "[G]" not in app.extra_list.get(0)
        fg0 = app.extra_list.itemcget(0, "foreground")
        fg1 = app.extra_list.itemcget(1, "foreground")
        assert fg0.lower() == STATUS_SWATCH[PROVENANCE_BACKUP].lower()
        assert fg1.lower() == STATUS_SWATCH[PROVENANCE_EXTRA].lower()
        # Round-trip provenance via in-memory specs (disc glyph alone is ambiguous)
        assert [s.provenance for s in app._scan_root_specs()] == [
            PROVENANCE_BACKUP,
            PROVENANCE_EXTRA,
        ]

        # Scan button packed RIGHT; step cues present
        assert app.scan_btn is not None
        pack = app.scan_btn.pack_info()
        assert str(pack.get("side", "")).lower() == "right"

        labels: list[str] = []

        def walk_actions(w):
            for child in w.winfo_children():
                try:
                    text = str(child.cget("text"))
                except tk.TclError:
                    text = ""
                if text:
                    labels.append(text)
                walk_actions(child)

        walk_actions(app._actions_frame)
        assert app._("indeks_step_config") in labels
        assert app._("indeks_step_run") in labels
        assert app._("run_scan") in labels
        assert app._("indeks_door_mapping") in labels
    finally:
        app.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_floor_simple_keeps_path_remap_in_folders(tmp_path: Path, monkeypatch):
    from tests.tk_util import require_working_tk

    require_working_tk()
    ini = tmp_path / "gcode-index.ini"
    save_instance_ini(
        ini,
        can_index=False,
        backup="",
        target=str(tmp_path / "db"),
    )
    monkeypatch.setenv("GCODE_INDEX_INI", str(ini))
    from gcode_index.gui import IndexerApp
    import tkinter as tk

    app = IndexerApp()
    try:
        assert app._is_simple()
        app._set_folders_expanded(True)
        app.update_idletasks()
        remap_label = app._("path_remap")
        found = False

        def walk(w):
            nonlocal found
            for child in w.winfo_children():
                try:
                    text = str(child.cget("text"))
                except tk.TclError:
                    text = ""
                if text == remap_label:
                    found = True
                walk(child)

        walk(app._folders_expanded_frame)
        assert found, "Floor Zmień… must still host path remap"
    finally:
        app.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_mapping_window_hosts_path_remap(tmp_path: Path, monkeypatch):
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

    app = IndexerApp()
    try:
        if app._is_simple():
            app._can_index = True
            app._rebuild(app._snapshot_ui())
        app._show_pelny_view("indeks", force=True)
        app._open_indeks_mapping_window()
        app.update_idletasks()
        remap_label = app._("path_remap")
        found = False
        for w in app.winfo_children():
            try:
                if w.winfo_class() != "Toplevel":
                    continue
            except tk.TclError:
                continue

            def walk(widget):
                nonlocal found
                for child in widget.winfo_children():
                    try:
                        text = str(child.cget("text"))
                    except tk.TclError:
                        text = ""
                    if text == remap_label:
                        found = True
                    walk(child)

            walk(w)
        assert found, "Mapowanie… must host path remap"
    finally:
        app.destroy()
