"""Praca|Indeks nav (indexer) and preview-pane find."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gcode_index.compare import preview_find_match_starts
from gcode_index.help_docs import read_manual
from gcode_index.i18n import t
from gcode_index.instance_ini import save_instance_ini


def test_preview_find_match_starts_nocase():
    text = "%\nO1234 (PART)\nG0 X0\ng0 x1\nM30\n"
    hits = preview_find_match_starts(text, "g0")
    assert len(hits) == 2
    assert text[hits[0] : hits[0] + 2].casefold() == "g0"
    assert preview_find_match_starts(text, "zzz") == []
    assert preview_find_match_starts(text, "") == []


def test_preview_find_i18n_keys():
    assert t("pl", "preview_find")
    assert t("en", "preview_find")
    assert "1/3" in t("en", "preview_find_status", current=1, total=3)
    assert t("pl", "tab_praca") == "Praca"
    assert t("pl", "tab_indeks") == "Indeks"
    assert t("en", "tab_praca") == "Work"
    assert t("en", "tab_indeks") == "Index"


def test_full_manual_mentions_praca_indeks():
    pl = read_manual("pl", "full")
    en = read_manual("en", "full")
    assert "Praca" in pl and "Indeks" in pl
    assert "Work" in en and "Index" in en
    assert "W podglądzie" in pl
    assert "In preview" in en


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_indexer_has_praca_indeks_and_preview_find(tmp_path: Path, monkeypatch):
    from tests.tk_util import require_working_tk

    require_working_tk()
    ini = tmp_path / "gcode-index.ini"
    save_instance_ini(ini, can_index=True)
    monkeypatch.setenv("GCODE_INDEX_INI", str(ini))

    from gcode_index.gui import IndexerApp

    app = IndexerApp()
    try:
        if app._is_simple():
            app._can_index = True
            app._rebuild(app._snapshot_ui())
        assert not app._is_simple()
        assert getattr(app, "_nav_praca_btn", None) is not None
        assert getattr(app, "_nav_indeks_btn", None) is not None
        assert getattr(app, "_praca_frame", None) is not None
        assert getattr(app, "_indeks_frame", None) is not None
        assert hasattr(app, "preview_find_entry")
        app._show_pelny_view("indeks")
        assert app._pelny_view == "indeks"
        app._show_pelny_view("praca")
        assert app._pelny_view == "praca"
        app.preview_text.configure(state="normal")
        app.preview_text.delete("1.0", "end")
        app.preview_text.insert("1.0", "G0 X0\nG1 X1\nG0 Z0\n")
        app.preview_text.configure(state="disabled")
        app.preview_find_var.set("G0")
        app._preview_find_reapply(keep_index=False)
        assert len(app._preview_find_matches) == 2
        assert app._preview_find_index == 0
        app._preview_find_next()
        assert app._preview_find_index == 1
        app._preview_find_next()
        assert app._preview_find_index == 0
    finally:
        app.destroy()
