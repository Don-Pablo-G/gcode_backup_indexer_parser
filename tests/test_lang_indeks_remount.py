"""Language rebuild and Praca↔Indeks must keep a populated Indeks pane."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from gcode_index.instance_ini import save_instance_ini


def _flush_idle(app) -> None:
    """Run deferred after(1) / idle callbacks (language rebuild)."""
    app.update_idletasks()
    app.update()
    # Language rebuild is scheduled with after(1, …) — pump until settled.
    deadline = time.monotonic() + 2.0
    while getattr(app, "_lang_switching", False) and time.monotonic() < deadline:
        app.update_idletasks()
        app.update()
        time.sleep(0.01)
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


def _assert_praca_populated(app) -> None:
    praca = getattr(app, "_praca_frame", None)
    assert praca is not None
    assert praca.winfo_exists()
    assert list(praca.winfo_children()), "Praca frame has no children"
    assert praca.winfo_manager(), "Praca frame is not packed under content"


def _make_app(tmp_path: Path, monkeypatch):
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
    if app._is_simple():
        app._can_index = True
        app._rebuild(app._snapshot_ui())
    assert not app._is_simple()
    return app


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_indeks_populated_after_lang_change_and_nav_switch(tmp_path: Path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    try:
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

        app._clear_nav_ignore()
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
def test_lang_flip_on_praca_keeps_praca_then_indeks_ok(tmp_path: Path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    try:
        app._show_pelny_view("praca", force=True)
        assert app._pelny_view == "praca"
        _assert_praca_populated(app)

        start_lang = app._lang
        other = "en" if start_lang == "pl" else "pl"
        app._set_language(other, persist=False)
        _flush_idle(app)
        assert app._lang == other
        assert app._pelny_view == "praca"
        _assert_praca_populated(app)

        app._clear_nav_ignore()
        app._show_pelny_view("indeks")
        assert app._pelny_view == "indeks"
        _assert_indeks_populated(app)
    finally:
        app.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_nav_quarantine_blocks_during_lang_switch(tmp_path: Path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    try:
        app._show_pelny_view("praca", force=True)
        start_lang = app._lang
        other = "en" if start_lang == "pl" else "pl"
        app._set_language(other, persist=False)
        # While switching, user nav must not flip the snapshot view
        assert app._lang_switching is True
        app._show_pelny_view("indeks")  # no force — should be ignored
        assert app._pelny_view == "praca"
        _flush_idle(app)
        assert app._pelny_view == "praca"
        _assert_praca_populated(app)
    finally:
        app.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_rapid_nav_after_lang_keeps_indeks_populated(tmp_path: Path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    try:
        app._show_pelny_view("indeks", force=True)
        other = "en" if app._lang == "pl" else "pl"
        app._set_language(other, persist=False)
        _flush_idle(app)
        # Clear quarantine so deliberate switches work
        app._clear_nav_ignore()
        for _ in range(6):
            app._show_pelny_view("praca")
            app._show_pelny_view("indeks")
        assert app._pelny_view == "indeks"
        _assert_indeks_populated(app)
        content = app._pelny_content
        assert content.winfo_manager()
        assert list(content.winfo_children())
    finally:
        app.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_build_initial_view_indeks(tmp_path: Path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    try:
        snap = app._snapshot_ui()
        snap["pelny_view"] = "indeks"
        app._rebuild(snap)
        assert app._pelny_view == "indeks"
        _assert_indeks_populated(app)
    finally:
        app.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_rebuilding_blocks_user_nav(tmp_path: Path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    try:
        app._show_pelny_view("praca", force=True)
        app._rebuilding = True
        app._show_pelny_view("indeks")  # no force
        assert app._pelny_view == "praca"
        app._rebuilding = False
        app._show_pelny_view("indeks")
        assert app._pelny_view == "indeks"
        _assert_indeks_populated(app)
    finally:
        app._rebuilding = False
        app.destroy()
