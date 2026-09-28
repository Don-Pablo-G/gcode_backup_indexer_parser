"""Exclude main backup folder from live Watch roots (default on)."""

from __future__ import annotations

from pathlib import Path

from gcode_index.folder_watch import collect_watch_roots
from gcode_index.i18n import t
from gcode_index.indexer_settings import (
    IndexerSettings,
    load_indexer_settings,
    save_indexer_settings,
)
from gcode_index.instance_ini import InstanceConfig, load_instance_ini, save_instance_ini


def test_collect_watch_roots_excludes_backup_by_default():
    backup = Path("/bak")
    green = Path("/green")
    yellow = Path("/yellow")
    roots = collect_watch_roots(backup, [green, yellow])
    assert roots == [green, yellow]
    assert backup not in roots


def test_collect_watch_roots_includes_backup_when_exclude_off():
    backup = Path("/bak")
    green = Path("/green")
    roots = collect_watch_roots(backup, [green], exclude_backup=False)
    assert roots == [backup, green]


def test_collect_watch_roots_extras_only_when_backup_empty():
    assert collect_watch_roots("", ["/a", "/b"]) == [Path("/a"), Path("/b")]
    assert collect_watch_roots(None, [], exclude_backup=False) == []
    assert collect_watch_roots("/bak", [], exclude_backup=True) == []
    assert collect_watch_roots("/bak", [], exclude_backup=False) == [Path("/bak")]


def test_collect_watch_roots_dedupes_extras():
    roots = collect_watch_roots("/bak", ["/a", "/a", Path("/b")], exclude_backup=True)
    assert roots == [Path("/a"), Path("/b")]


def test_instance_ini_default_and_missing_key_is_yes(tmp_path: Path):
    assert InstanceConfig().watch_exclude_backup is True

    path = tmp_path / "gcode-index.ini"
    path.write_text(
        "[folders]\nbackup = /bak\ntarget = /db\n\n"
        "[scan]\nincremental = yes\nwatch_folders = yes\nwatch_mode = hybrid\n",
        encoding="utf-8",
    )
    loaded = load_instance_ini(path)
    assert loaded.watch_exclude_backup is True

    path.write_text(
        "[folders]\nbackup = /bak\ntarget = /db\n\n"
        "[scan]\nwatch_exclude_backup = no\n",
        encoding="utf-8",
    )
    loaded = load_instance_ini(path)
    assert loaded.watch_exclude_backup is False


def test_instance_ini_roundtrip_watch_exclude_backup(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    cfg = InstanceConfig(
        backup="/bak",
        target="/db",
        watch_exclude_backup=False,
    )
    save_instance_ini(path, config=cfg)
    text = path.read_text(encoding="utf-8")
    assert "watch_exclude_backup = no" in text
    loaded = load_instance_ini(path)
    assert loaded.watch_exclude_backup is False

    cfg2 = InstanceConfig(backup="/bak", target="/db", watch_exclude_backup=True)
    save_instance_ini(path, config=cfg2)
    assert "watch_exclude_backup = yes" in path.read_text(encoding="utf-8")
    assert load_instance_ini(path).watch_exclude_backup is True


def test_indexer_settings_default_and_missing_key(tmp_path: Path):
    assert IndexerSettings().watch_exclude_backup is True
    path = tmp_path / "indexer_settings.yaml"
    path.write_text("watch_folders: yes\nwatch_mode: poll\n", encoding="utf-8")
    loaded = load_indexer_settings(path)
    assert loaded is not None
    assert loaded.watch_exclude_backup is True

    path.write_text("watch_exclude_backup: no\n", encoding="utf-8")
    loaded = load_indexer_settings(path)
    assert loaded is not None
    assert loaded.watch_exclude_backup is False

    save_indexer_settings(path, IndexerSettings(watch_exclude_backup=True))
    text = path.read_text(encoding="utf-8")
    assert "watch_exclude_backup: true" in text


def test_i18n_watch_exclude_backup_labels():
    assert "kopii" in t("pl", "watch_exclude_backup").casefold()
    assert "backup" in t("en", "watch_exclude_backup").casefold()
    assert t("pl", "watch_exclude_backup_hint")
    assert t("en", "watch_exclude_backup_hint")
