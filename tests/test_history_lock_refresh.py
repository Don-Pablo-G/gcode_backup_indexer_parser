"""Tests for scan history, operator lock, and search auto-refresh prefs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gcode_index.instance_ini import InstanceConfig, load_instance_ini, save_instance_ini
from gcode_index.models import FileSeen, ProgramInstance, ScanResult
from gcode_index.operator_lock import (
    is_settings_locked,
    lock_file_beside,
    settings_locked_from_ini_value,
)
from gcode_index.scan_cache import CachedSource, ScanCache
from gcode_index.scan_history import (
    append_scan_history,
    build_history_entry,
    history_path_for_target,
    load_scan_history,
    prior_paths_from_cache,
)
from gcode_index.i18n import t


def _inst(path: str = "/a.nc") -> ProgramInstance:
    return ProgramInstance(
        program_number="O1",
        part_number=None,
        machine_id="vf2",
        backup_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        date_source="mtime",
        source_path=path,
        source_type="loose_nc",
    )


def test_build_history_entry_stats():
    prior = {"/old.nc", "/keep.nc"}
    result = ScanResult(
        instances=[_inst("/keep.nc"), _inst("/new.nc")],
        files_seen=[
            FileSeen("/keep.nc", "loose_nc", 10, None, "indexed", ""),
            FileSeen("/new.nc", "loose_nc", 10, None, "indexed", ""),
            FileSeen("/cached.nc", "loose_nc", 10, None, "cached", ""),
        ],
    )
    started = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 9, 26, 10, 0, 12, tzinfo=timezone.utc)
    entry = build_history_entry(
        run_id="abc",
        backup_root="/bak",
        result=result,
        started_at=started,
        finished_at=finished,
        prior_paths=prior,
        incremental=True,
        auto=True,
    )
    assert entry.duration_s == 12.0
    assert entry.files_added == 1  # new.nc
    assert entry.files_updated == 1  # keep.nc
    assert entry.files_removed == 1  # old.nc gone
    assert entry.files_cached == 1
    assert entry.incremental is True
    assert entry.auto is True
    assert "12" in entry.duration_label()


def test_scan_history_sidecar_roundtrip(tmp_path: Path):
    target = tmp_path / "db"
    target.mkdir()
    entry = build_history_entry(
        run_id="run1",
        backup_root="/bak",
        result=ScanResult(instances=[], files_seen=[]),
        started_at=datetime.now(timezone.utc),
        incremental=False,
    )
    path = append_scan_history(target, entry, limit=5)
    assert path == history_path_for_target(target)
    assert path.is_file()
    loaded = load_scan_history(path)
    assert len(loaded) == 1
    assert loaded[0].run_id == "run1"


def test_prior_paths_from_cache():
    cache = ScanCache(
        by_key={
            ("", "/a.nc"): CachedSource("/a.nc", "", 1, None, "loose_nc", []),
            ("root", "/b.nc"): CachedSource("/b.nc", "root", 2, None, "loose_nc", []),
        }
    )
    paths = prior_paths_from_cache(cache)
    assert "/a.nc" in paths
    assert "/b.nc" in paths
    assert prior_paths_from_cache(None) == set()


def test_operator_lock_file(tmp_path: Path):
    ini = tmp_path / "gcode-index.ini"
    ini.write_text("[capabilities]\ncan_index = yes\n", encoding="utf-8")
    assert lock_file_beside(ini) is None
    assert not is_settings_locked(ini_path=ini, settings_locked_flag=False)
    (tmp_path / "operator.lock").write_text("", encoding="utf-8")
    assert lock_file_beside(ini) is not None
    assert is_settings_locked(ini_path=ini, settings_locked_flag=False)


def test_settings_locked_forces_can_index_no(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    path.write_text(
        "[capabilities]\ncan_index = yes\nsettings_locked = yes\n",
        encoding="utf-8",
    )
    cfg = load_instance_ini(path)
    assert cfg.settings_locked is True
    assert cfg.can_index is False
    assert settings_locked_from_ini_value("yes") is True


def test_operator_lock_file_overrides_ini_can_index(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    path.write_text("[capabilities]\ncan_index = yes\n", encoding="utf-8")
    (tmp_path / "can_index.lock").write_text("locked\n", encoding="utf-8")
    cfg = load_instance_ini(path)
    assert cfg.can_index is False
    assert cfg.settings_locked is True


def test_search_auto_refresh_ini_roundtrip(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    cfg = InstanceConfig(
        search_auto_refresh=True,
        search_auto_refresh_s=15,
        can_index=False,
    )
    save_instance_ini(path, config=cfg)
    text = path.read_text(encoding="utf-8")
    assert "search_auto_refresh = yes" in text
    assert "search_auto_refresh_s = 15" in text
    assert "settings_locked" in text
    loaded = load_instance_ini(path)
    assert loaded.search_auto_refresh is True
    assert loaded.search_auto_refresh_s == 15


def test_save_respects_lock_file(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    (tmp_path / "operator.lock").write_text("", encoding="utf-8")
    save_instance_ini(path, can_index=True, settings_locked=False)
    loaded = load_instance_ini(path)
    assert loaded.can_index is False
    assert loaded.settings_locked is True


def test_history_i18n():
    assert "Historia" in t("pl", "scan_history")
    assert "Scan history" in t("en", "scan_history")
    assert "Odświeżaj" in t("pl", "search_auto_refresh")
    assert "Auto-refresh" in t("en", "search_auto_refresh")
