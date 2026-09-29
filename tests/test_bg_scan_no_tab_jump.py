"""Background auto-scans must not steal Praca | Indeks nav."""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUI_PATH = ROOT / "src" / "gcode_index" / "gui.py"


def test_start_scan_wires_switch_view_not_auto():
    """Source contract: auto scans keep nav; manual may jump to Indeks."""
    text = GUI_PATH.read_text(encoding="utf-8")
    assert "def _show_progress(self, visible: bool, *, switch_view: bool = True)" in text
    assert re.search(
        r"self\._show_progress\(\s*True\s*,\s*switch_view\s*=\s*not\s+auto\s*\)",
        text,
    )
    # Background entry still uses auto=True (Watch / coalesce / safety).
    assert "_start_scan(auto=True)" in text


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_show_progress_auto_keeps_praca_view(tmp_path: Path, monkeypatch):
    from tests.tk_util import require_working_tk

    require_working_tk()
    from gcode_index.instance_ini import save_instance_ini

    ini = tmp_path / "gcode-index.ini"
    bak = tmp_path / "backup"
    db = tmp_path / "db"
    bak.mkdir()
    db.mkdir()
    save_instance_ini(ini, can_index=True, backup=str(bak), target=str(db))
    monkeypatch.setenv("GCODE_INDEX_INI", str(ini))
    from gcode_index.gui import IndexerApp

    app = IndexerApp()
    try:
        if app._is_simple():
            app._can_index = True
            app._rebuild(app._snapshot_ui())
        app._show_pelny_view("praca", force=True)
        assert app._pelny_view == "praca"
        jumped: list[bool] = []

        with mock.patch.object(
            app, "_goto_indeks_tab", side_effect=lambda: jumped.append(True)
        ):
            # Hide then show so pack path runs.
            app._show_progress(False)
            app._show_progress(True, switch_view=False)
        assert jumped == []
        assert app._pelny_view == "praca"

        with mock.patch.object(
            app, "_goto_indeks_tab", side_effect=lambda: jumped.append(True)
        ):
            app._show_progress(False)
            app._show_progress(True, switch_view=True)
        assert jumped == [True]
    finally:
        app.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_start_scan_auto_does_not_goto_indeks(tmp_path: Path, monkeypatch):
    from tests.tk_util import require_working_tk

    require_working_tk()
    from gcode_index.instance_ini import save_instance_ini

    ini = tmp_path / "gcode-index.ini"
    bak = tmp_path / "backup"
    db = tmp_path / "db"
    bak.mkdir()
    db.mkdir()
    save_instance_ini(ini, can_index=True, backup=str(bak), target=str(db))
    monkeypatch.setenv("GCODE_INDEX_INI", str(ini))
    from gcode_index.gui import IndexerApp

    app = IndexerApp()
    try:
        if app._is_simple():
            app._can_index = True
            app._rebuild(app._snapshot_ui())
        app._show_pelny_view("praca", force=True)
        jumped: list[str] = []
        real_show = app._show_progress

        def _wrap_show(visible, *, switch_view=True):
            if visible:
                jumped.append("switch" if switch_view else "stay")
            return real_show(visible, switch_view=switch_view)

        with (
            mock.patch.object(app, "_show_progress", side_effect=_wrap_show),
            mock.patch.object(app, "_persist_ui_settings"),
            mock.patch.object(app, "_persist_extra_roots"),
            mock.patch.object(app, "_maybe_auto_collapse_folders"),
            mock.patch("threading.Thread") as thr,
        ):
            thr.return_value.start = lambda: None
            app._start_scan(auto=True)
            app.update_idletasks()

        assert "stay" in jumped
        assert "switch" not in jumped
        assert app._pelny_view == "praca"

        jumped.clear()
        app._scan_busy = False
        with (
            mock.patch.object(app, "_show_progress", side_effect=_wrap_show),
            mock.patch.object(app, "_persist_ui_settings"),
            mock.patch.object(app, "_persist_extra_roots"),
            mock.patch.object(app, "_maybe_auto_collapse_folders"),
            mock.patch("threading.Thread") as thr,
            mock.patch(
                "gcode_index.gui.discover_machine_folders", return_value=[]
            ),
            mock.patch(
                "gcode_index.gui.partition_folders",
                return_value=mock.Mock(needs_manual=False, manual_count=0),
            ),
        ):
            thr.return_value.start = lambda: None
            app._start_scan(auto=False)
            app.update_idletasks()

        assert "switch" in jumped
    finally:
        app._scan_busy = False
        app.destroy()
