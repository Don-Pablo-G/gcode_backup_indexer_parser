"""Tests for installed-instance gcode-index.ini."""

from __future__ import annotations

from pathlib import Path

from gcode_index.instance_ini import (
    INSTANCE_INI_FILENAME,
    InstanceConfig,
    can_index_from_ui_mode,
    load_instance_ini,
    normalize_can_index,
    save_instance_ini,
    ui_mode_from_can_index,
)
from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA


def test_instance_ini_roundtrip(tmp_path: Path):
    path = tmp_path / INSTANCE_INI_FILENAME
    cfg = InstanceConfig(
        backup=r"D:\CNC\Backups",
        target=r"D:\CNC\Index",
        extract=r"D:\CNC\Extracted",
        green_roots=[r"D:\CNC\Catch", r"D:\CNC\USB"],
        yellow_roots=[r"D:\CNC\Extra"],
        language="pl",
        can_index=False,
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
    assert "[capabilities]" in text
    assert "can_index = no" in text
    assert "green_roots" in text
    assert r"D:\CNC\Catch" in text
    assert "extract = " in text
    assert r"D:\CNC\Extracted" in text
    assert "schedule = 1d" in text

    loaded = load_instance_ini(path)
    assert loaded.backup == r"D:\CNC\Backups"
    assert loaded.target == r"D:\CNC\Index"
    assert loaded.extract == r"D:\CNC\Extracted"
    assert loaded.extract_folder() == r"D:\CNC\Extracted"
    assert loaded.green_roots == [r"D:\CNC\Catch", r"D:\CNC\USB"]
    assert loaded.yellow_roots == [r"D:\CNC\Extra"]
    assert loaded.language == "pl"
    assert loaded.can_index is False
    assert loaded.ui_mode == "simple"
    assert loaded.schedule == "1d"
    assert loaded.newest_only is True
    assert loaded.also_excel is False
    assert loaded.geometry == "1400x900"
    assert "VF2" in loaded.notes

    specs = loaded.root_specs()
    assert any(s.provenance == PROVENANCE_BACKUP and "Catch" in s.path for s in specs)
    assert any(s.provenance == PROVENANCE_EXTRA and "Extra" in s.path for s in specs)


def test_can_index_helpers():
    assert normalize_can_index("yes") is True
    assert normalize_can_index("no") is False
    assert normalize_can_index("full") is True
    assert normalize_can_index("simple") is False
    assert can_index_from_ui_mode("full") is True
    assert can_index_from_ui_mode("simple") is False
    assert can_index_from_ui_mode("Pełny") is True
    assert ui_mode_from_can_index(True) == "full"
    assert ui_mode_from_can_index(False) == "simple"


def test_migrate_legacy_ui_mode_to_can_index(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    path.write_text(
        """
[folders]
backup = /bak
target = /db

[ui]
language = en
mode = full
schedule = off
""",
        encoding="utf-8",
    )
    cfg = load_instance_ini(path)
    assert cfg.can_index is True
    assert cfg.ui_mode == "full"

    path.write_text(
        """
[folders]
target = /db

[ui]
mode = simple
""",
        encoding="utf-8",
    )
    cfg = load_instance_ini(path)
    assert cfg.can_index is False
    assert cfg.ui_mode == "simple"


def test_capabilities_can_index_overrides_legacy_mode(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    path.write_text(
        """
[capabilities]
can_index = yes

[ui]
mode = simple
""",
        encoding="utf-8",
    )
    cfg = load_instance_ini(path)
    assert cfg.can_index is True
    assert cfg.ui_mode == "full"

    save_instance_ini(path, config=cfg)
    text = path.read_text(encoding="utf-8")
    assert "can_index = yes" in text
    assert "mode = full" in text


def test_save_ui_mode_kwarg_maps_to_can_index(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    save_instance_ini(path, ui_mode="full", language="en")
    loaded = load_instance_ini(path)
    assert loaded.can_index is True
    assert loaded.ui_mode == "full"
    save_instance_ini(path, can_index=False)
    loaded = load_instance_ini(path)
    assert loaded.can_index is False
    assert loaded.ui_mode == "simple"


def test_instance_ini_extract_falls_back_to_target(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    path.write_text(
        """
[folders]
backup = /bak
target = /db
""",
        encoding="utf-8",
    )
    cfg = load_instance_ini(path)
    assert cfg.extract == ""
    assert cfg.extract_folder() == "/db"


def test_instance_ini_legacy_extract_folder_key(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    path.write_text(
        """
[folders]
backup = /bak
target = /db
extract_folder = /out
""",
        encoding="utf-8",
    )
    cfg = load_instance_ini(path)
    assert cfg.extract == "/out"
    assert cfg.extract_folder() == "/out"


def test_instance_ini_missing_file(tmp_path: Path):
    cfg = load_instance_ini(tmp_path / "missing.ini")
    assert cfg.backup == ""
    assert cfg.green_roots == []
    assert cfg.schedule == "off"
    assert cfg.can_index is False


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
