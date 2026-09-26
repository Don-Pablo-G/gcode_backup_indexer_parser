"""Language rebuild and Praca↔Indeks must keep a populated Indeks pane."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gcode_index.instance_ini import save_instance_ini


def _flush_idle(app) -> None:
    """Run deferred after_idle callbacks (language rebuild)."""
    app.update_idletasks()
    app.update()


def _assert_indeks_populated(app) -> None:
    indeks = getattr(app, "_indeks_frame", None)
    assert indeks is not None
    assert indeks.winfo_exists()
    children = list(indeks.winfo_children())
    assert children, "Indeks frame has no children (toolbar/panels missing)"
    assert indeks.winfo_manager(), "Indeks frame is not packed under content"
    content = getattr(app, "_pelny_content", None)
    assert content is not None
    assert content.winfo_manager(), "Pelny content host is not packed"
    assert getattr(app, "_actions_frame", None) is not None
    assert app._actions_frame.winfo_exists()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_indeks_populated_after_lang_change_and_nav_switch(tmp_path: Path, monkeypatch):
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
        assert not app._is_simple()

        app._show_pelny_view("indeks")
        assert app._pelny_view == "indeks"
        _assert_indeks_populated(app)

        app._show_pelny_view("praca")
        assert app._pelny_view == "praca"
        app._show_pelny_view("indeks")
        assert app._pelny_view == "indeks"
        _assert_indeks_populated(app)

        start_lang = app._lang
        other = "en" if start_lang == "pl" else "pl"
        app._set_language(other, persist=False)
        _flush_idle(app)
        assert app._lang == other
        assert app._pelny_view == "indeks"
        _assert_indeks_populated(app)

        app._show_pelny_view("praca")
        app._show_pelny_view("indeks")
        _assert_indeks_populated(app)

        # Second language flip while already on Indeks
        app._set_language(start_lang, persist=False)
        _flush_idle(app)
        assert app._lang == start_lang
        assert app._pelny_view == "indeks"
        _assert_indeks_populated(app)
    finally:
        app.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_build_initial_view_indeks(tmp_path: Path, monkeypatch):
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
        snap = app._snapshot_ui()
        snap["pelny_view"] = "indeks"
        app._rebuild(snap)
        assert app._pelny_view == "indeks"
        _assert_indeks_populated(app)
    finally:
        app.destroy()
