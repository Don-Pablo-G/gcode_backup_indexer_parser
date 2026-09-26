"""Shop pack sidecar: indexer_settings.yaml."""

from __future__ import annotations

from pathlib import Path

from gcode_index.indexer_settings import (
    INDEXER_SETTINGS_FILENAME,
    IndexerSettings,
    indexer_settings_path_for_target,
    load_indexer_settings,
    save_indexer_settings,
    settings_equal,
)


def test_indexer_settings_roundtrip(tmp_path: Path):
    path = tmp_path / INDEXER_SETTINGS_FILENAME
    settings = IndexerSettings(
        incremental=False,
        also_excel=True,
        newest_only=True,
        include_unknown=False,
        schedule="15m",
        watch_folders=True,
        watch_mode="poll",
        backup_hint=r"\\shop\cnc\backup",
        green_root_hints=[r"\\shop\cnc\catch"],
        yellow_root_hints=[r"\\shop\cnc\extra"],
    )
    save_indexer_settings(path, settings)
    text = path.read_text(encoding="utf-8")
    assert "can_index:" not in text
    assert "ui_mode:" not in text
    assert "schedule: 15m" in text or "schedule: '15m'" in text or 'schedule: "15m"' in text
    assert "watch_folders: true" in text

    loaded = load_indexer_settings(path)
    assert loaded is not None
    assert loaded.incremental is False
    assert loaded.also_excel is True
    assert loaded.newest_only is True
    assert loaded.include_unknown is False
    assert loaded.schedule == "15m"
    assert loaded.watch_folders is True
    assert loaded.watch_mode == "poll"
    assert loaded.backup_hint == r"\\shop\cnc\backup"
    assert loaded.green_root_hints == [r"\\shop\cnc\catch"]
    assert settings_equal(loaded, settings)


def test_load_missing_returns_none(tmp_path: Path):
    assert load_indexer_settings(tmp_path / "nope.yaml") is None
    assert load_indexer_settings(None) is None


def test_ignores_can_index_in_file(tmp_path: Path):
    path = tmp_path / INDEXER_SETTINGS_FILENAME
    path.write_text(
        "can_index: yes\nui_mode: full\nschedule: 1h\nwatch_folders: yes\n",
        encoding="utf-8",
    )
    loaded = load_indexer_settings(path)
    assert loaded is not None
    assert loaded.schedule == "1h"
    assert loaded.watch_folders is True
    # Round-trip must not write can_index
    out = tmp_path / "out.yaml"
    save_indexer_settings(out, loaded)
    assert "can_index:" not in out.read_text(encoding="utf-8")


def test_path_for_target(tmp_path: Path):
    p = indexer_settings_path_for_target(tmp_path)
    assert p.name == INDEXER_SETTINGS_FILENAME
    assert p.parent == tmp_path
