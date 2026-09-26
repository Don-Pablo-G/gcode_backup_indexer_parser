"""Source column always shows ✓ or BRAK/MISSING; filter/column persist."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gcode_index.instance_ini import (
    INSTANCE_INI_FILENAME,
    InstanceConfig,
    load_instance_ini,
    save_instance_ini,
)
from gcode_index.i18n import t


def test_badge_ok_i18n():
    assert t("pl", "badge_ok") == "✓"
    assert t("en", "badge_ok") == "✓"
    assert t("pl", "badge_missing") == "BRAK"
    assert t("en", "badge_missing") == "MISSING"


def test_filter_odbiorca_roundtrip(tmp_path: Path):
    path = tmp_path / INSTANCE_INI_FILENAME
    cfg = InstanceConfig(
        backup="/bak",
        target="/out",
        filter_odbiorca="acme_sp",
        hidden_columns=["control", "location"],
        column_widths={"program": 140, "path": 400},
    )
    save_instance_ini(path, config=cfg)
    text = path.read_text(encoding="utf-8")
    assert "odbiorca = acme_sp" in text
    loaded = load_instance_ini(path)
    assert loaded.filter_odbiorca == "acme_sp"
    assert set(loaded.hidden_columns) == {"control", "location"}
    assert loaded.column_widths.get("program") == 140


def test_filter_odbiorca_missing_token(tmp_path: Path):
    path = tmp_path / INSTANCE_INI_FILENAME
    path.write_text("[filters]\nodbiorca = __missing__\n", encoding="utf-8")
    loaded = load_instance_ini(path)
    assert loaded.filter_odbiorca == "__missing__"


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_source_column_always_ok_or_brak(tmp_path: Path, monkeypatch):
    from tests.tk_util import require_working_tk

    require_working_tk()
    ini = tmp_path / "gcode-index.ini"
    bak = tmp_path / "backup"
    db = tmp_path / "db"
    bak.mkdir()
    db.mkdir()
    present = bak / "15.09.2026" / "VF2S" / "a.nc"
    present.parent.mkdir(parents=True)
    present.write_text("%\nO1001\n%\n", encoding="utf-8")
    save_instance_ini(ini, can_index=True, backup=str(bak), target=str(db))
    monkeypatch.setenv("GCODE_INDEX_INI", str(ini))

    from gcode_index.gui import IndexerApp

    app = IndexerApp()
    try:
        if app._is_simple():
            app._can_index = True
            app._rebuild(app._snapshot_ui())
        # Synthetic rows: one present, one missing
        rows = [
            {
                "backup_date": "2026-09-15",
                "machine_label": "VF-2",
                "machine_id": "haas-vf-2",
                "program_number": "1001",
                "part_number": "",
                "source_path": str(present.relative_to(bak)).replace("\\", "/"),
                "source_type": "loose_nc",
                "control_family": "haas",
                "provenance": "backup",
                "role": None,
                "odbiorca_id": None,
                "programmer": None,
                "source_size": 12,
                "scan_root": str(bak),
                "line_start": None,
                "line_end": None,
                "byte_start": None,
                "byte_end": None,
                "folder_path": "",
            },
            {
                "backup_date": "2026-09-15",
                "machine_label": "VF-2",
                "machine_id": "haas-vf-2",
                "program_number": "1002",
                "part_number": "",
                "source_path": "gone/missing.nc",
                "source_type": "loose_nc",
                "control_family": "haas",
                "provenance": "backup",
                "role": None,
                "odbiorca_id": None,
                "programmer": None,
                "source_size": 0,
                "scan_root": str(bak),
                "line_start": None,
                "line_end": None,
                "byte_start": None,
                "byte_end": None,
                "folder_path": "",
            },
        ]
        app.backup_var.set(str(bak))
        app._fill_tree(rows)
        kids = app.tree.get_children()
        assert len(kids) == 2
        vals0 = app.tree.item(kids[0], "values")
        vals1 = app.tree.item(kids[1], "values")
        # column order: flag, src, program, …
        src0, src1 = vals0[1], vals1[1]
        ok = app._("badge_ok")
        missing = app._("badge_missing")
        assert src0 == ok
        assert src1 == missing
        assert src0  # never blank when present
        assert src1  # never blank when missing
    finally:
        app.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_snapshot_restores_odbiorca_and_hidden_columns(tmp_path: Path, monkeypatch):
    from tests.tk_util import require_working_tk

    require_working_tk()
    ini = tmp_path / "gcode-index.ini"
    save_instance_ini(
        ini,
        can_index=True,
        backup=str(tmp_path / "backup"),
        target=str(tmp_path / "db"),
        filter_odbiorca="__missing__",
        hidden_columns=["control", "location"],
        column_widths={"program": 155},
    )
    monkeypatch.setenv("GCODE_INDEX_INI", str(ini))
    from gcode_index.gui import IndexerApp

    app = IndexerApp()
    try:
        if app._is_simple():
            app._can_index = True
            app._rebuild(app._snapshot_ui())
        assert "__missing__" in (
            app._odbiorca_filter_for_ini(),
            "",
        ) or app.odbiorca_var.get() == app._("odbiorca_missing")
        # Force missing filter + hide columns, snapshot, language rebuild
        app.odbiorca_var.set(app._("odbiorca_missing"))
        app._hidden_columns = {"control", "location"}
        app._column_widths["program"] = 155
        app._apply_column_visibility()
        snap = app._snapshot_ui()
        assert snap["odbiorca"] == "__missing__"
        assert set(snap["hidden_columns"]) == {"control", "location"}
        other = "en" if app._lang == "pl" else "pl"
        app._set_language(other, persist=False)
        app.update_idletasks()
        app.update()
        import time

        deadline = time.monotonic() + 2.0
        while getattr(app, "_lang_switching", False) and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        app.update()
        assert app._odbiorca_filter_for_ini() == "__missing__"
        assert set(app._hidden_columns) >= {"control", "location"} or set(
            app._hidden_columns
        ) == {"control", "location"}
        assert int(app._column_widths.get("program", 0)) == 155
    finally:
        app.destroy()
