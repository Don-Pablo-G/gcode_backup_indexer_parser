"""Tests for folder watcher stamps and indexer lock."""

from __future__ import annotations

import os
import socket
import time
from pathlib import Path

from gcode_index.folder_watch import FolderWatcher, is_indexable_path, stamp_tree
from gcode_index.indexer_lock import (
    is_lock_stale,
    lock_path_for_target,
    read_lock,
    release_lock,
    try_acquire_lock,
    we_hold_lock,
)
from gcode_index.instance_ini import InstanceConfig, load_instance_ini, save_instance_ini
from gcode_index.i18n import t


def test_is_indexable_path(tmp_path: Path):
    assert is_indexable_path(tmp_path / "a.nc") is False  # missing file
    nc = tmp_path / "a.nc"
    nc.write_bytes(b"%\nO1\n%\n")
    assert is_indexable_path(nc)
    copy = tmp_path / "a.nc.copy"
    copy.write_bytes(b"x")
    assert is_indexable_path(copy)
    pgm = tmp_path / "D.PGM"
    pgm.write_bytes(b"%\n")
    assert is_indexable_path(pgm)
    txt = tmp_path / "ALL-FLDR.TXT"
    txt.write_text("x", encoding="utf-8")
    assert is_indexable_path(txt)
    other = tmp_path / "notes.txt"
    other.write_text("x", encoding="utf-8")
    assert not is_indexable_path(other)


def test_stamp_tree_and_watcher_detects_new_file(tmp_path: Path):
    root = tmp_path / "bak"
    root.mkdir()
    (root / "old.nc").write_bytes(b"a")
    hits: list[int] = []
    polls: list[int] = []

    watcher = FolderWatcher(
        on_change=lambda: hits.append(1),
        poll_s=0.2,
        debounce_s=0.3,
        on_poll=lambda: polls.append(1),
    )
    watcher.set_roots([root])
    assert watcher.seed() == 1
    assert watcher.stamp_count == 1
    assert watcher.last_poll_at is not None
    watcher.start()
    try:
        (root / "new.nc").write_bytes(b"b")
        deadline = time.time() + 3.0
        while not hits and time.time() < deadline:
            time.sleep(0.1)
        assert hits, "watcher should fire after new file + debounce"
        assert watcher.stamp_count == 2
        assert watcher.last_change_at is not None
        # At least one poll callback after start
        deadline2 = time.time() + 2.0
        while not polls and time.time() < deadline2:
            time.sleep(0.1)
        assert polls, "on_poll should fire"
    finally:
        watcher.stop()


def test_watcher_on_poll_updates_last_poll(tmp_path: Path):
    root = tmp_path / "bak"
    root.mkdir()
    (root / "a.nc").write_bytes(b"x")
    seen: list[int] = []
    watcher = FolderWatcher(
        on_change=lambda: None,
        poll_s=0.15,
        debounce_s=0.2,
        on_poll=lambda: seen.append(watcher.stamp_count),
    )
    watcher.set_roots([root])
    watcher.seed()
    first = watcher.last_poll_at
    watcher.start()
    try:
        deadline = time.time() + 2.0
        while len(seen) < 1 and time.time() < deadline:
            time.sleep(0.05)
        assert seen
        assert watcher.last_poll_at is not None
        assert watcher.last_poll_at >= first  # type: ignore[operator]
        assert watcher.stamp_count == 1
    finally:
        watcher.stop()


def test_watch_strip_i18n():
    assert "{when}" in t("pl", "watch_strip_poll")
    assert "{n}" in t("en", "watch_strip_files")
    assert "ten PC" in t("pl", "watch_strip_lock_us")
    assert "this PC" in t("en", "watch_strip_lock_us")


def test_indexer_lock_roundtrip(tmp_path: Path):
    target = tmp_path / "db"
    target.mkdir()
    ok, info = try_acquire_lock(target, purpose="watch")
    assert ok
    assert info is not None
    assert we_hold_lock(target)
    assert lock_path_for_target(target).is_file()
    loaded = read_lock(target)
    assert loaded is not None
    assert loaded.host == socket.gethostname()
    assert loaded.pid == os.getpid()
    release_lock(target)
    assert read_lock(target) is None


def test_indexer_lock_blocks_second_holder(tmp_path: Path):
    target = tmp_path / "db"
    target.mkdir()
    path = lock_path_for_target(target)
    path.write_text(
        "host=OTHER-PC\npid=1\nstarted_at=2099-01-01T00:00:00+00:00\npurpose=watch\n",
        encoding="utf-8",
    )
    ok, holder = try_acquire_lock(target, purpose="watch")
    assert not ok
    assert holder is not None
    assert holder.host == "OTHER-PC"


def test_stale_lock_from_dead_same_host(tmp_path: Path):
    from gcode_index.indexer_lock import LockInfo

    dead = LockInfo(
        host=socket.gethostname(),
        pid=999_999_999,
        started_at="2000-01-01T00:00:00+00:00",
        purpose="watch",
    )
    assert is_lock_stale(dead)


def test_instance_ini_watch_folders(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    cfg = InstanceConfig(watch_folders=True, incremental=True)
    save_instance_ini(path, config=cfg)
    loaded = load_instance_ini(path)
    assert loaded.watch_folders is True
    text = path.read_text(encoding="utf-8")
    assert "watch_folders = yes" in text


def test_watch_i18n():
    assert "Obserwuj" in t("pl", "watch_folders")
    assert "Watch" in t("en", "watch_folders")
    assert "Wykryto" in t("pl", "watch_trigger")
