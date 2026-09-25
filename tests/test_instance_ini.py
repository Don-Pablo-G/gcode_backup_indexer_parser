"""Tests for installed-instance gcode-index.ini."""

from __future__ import annotations

from pathlib import Path

from gcode_index.instance_ini import (
    INSTANCE_INI_FILENAME,
    InstanceConfig,
    load_instance_ini,
    save_instance_ini,
)
from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA


def test_instance_ini_roundtrip(tmp_path: Path):
    path = tmp_path / INSTANCE_INI_FILENAME
    cfg = InstanceConfig(
        backup=r"D:\CNC\Backups",
        target=r"D:\CNC\Index",
        green_roots=[r"D:\CNC\Catch", r"D:\CNC\USB"],
        yellow_roots=[r"D:\CNC\Extra"],
        language="pl",
        ui_mode="simple",
        schedule="daily",
        schedule_last_run="2026-09-25T00:00:00+00:00",
        incremental=True,
        also_excel=False,
        newest_only=True,
        geometry="1400x900",
        notes="VF2 cell PC",
    )
    save_instance_ini(path, config=cfg)
    text = path.read_text(encoding="utf-8")
    assert "G-code Backup Indexer" in text
    assert "green_roots" in text
    assert r"D:\CNC\Catch" in text
    assert "schedule = daily" in text

    loaded = load_instance_ini(path)
    assert loaded.backup == r"D:\CNC\Backups"
    assert loaded.target == r"D:\CNC\Index"
    assert loaded.green_roots == [r"D:\CNC\Catch", r"D:\CNC\USB"]
    assert loaded.yellow_roots == [r"D:\CNC\Extra"]
    assert loaded.language == "pl"
    assert loaded.ui_mode == "simple"
    assert loaded.schedule == "daily"
    assert loaded.newest_only is True
    assert loaded.also_excel is False
    assert loaded.geometry == "1400x900"
    assert "VF2" in loaded.notes

    specs = loaded.root_specs()
    assert any(s.provenance == PROVENANCE_BACKUP and "Catch" in s.path for s in specs)
    assert any(s.provenance == PROVENANCE_EXTRA and "Extra" in s.path for s in specs)


def test_instance_ini_missing_file(tmp_path: Path):
    cfg = load_instance_ini(tmp_path / "missing.ini")
    assert cfg.backup == ""
    assert cfg.green_roots == []
    assert cfg.schedule == "off"


def test_instance_ini_prefixed_paths_in_block(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    path.write_text(
        """
[folders]
backup = /bak
target = /out

[green_roots]
paths =
    green:/catch
    /also_green

[yellow_roots]
paths =
    yellow:/extra
""",
        encoding="utf-8",
    )
    cfg = load_instance_ini(path)
    assert cfg.green_roots == ["/catch", "/also_green"]
    assert cfg.yellow_roots == ["/extra"]
