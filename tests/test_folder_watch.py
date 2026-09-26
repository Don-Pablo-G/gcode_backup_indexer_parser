"""Tests for folder watcher stamps, hybrid mode, and indexer lock."""

from __future__ import annotations

import os
import socket
import time
from pathlib import Path

from gcode_index.folder_watch import (
    METHOD_EVENTS,
    METHOD_POLL,
    WATCH_MODE_HYBRID,
    WATCH_MODE_POLL,
    FolderWatcher,
    events_backend_available,
    is_indexable_path,
    is_network_path,
    is_unc_path,
    normalize_watch_mode,
    short_root_label,
    watch_method_for_path,
)
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


def test_normalize_watch_mode():
    assert normalize_watch_mode("hybrid") == WATCH_MODE_HYBRID
    assert normalize_watch_mode("Auto") == WATCH_MODE_HYBRID
    assert normalize_watch_mode("hybryda") == WATCH_MODE_HYBRID
    assert normalize_watch_mode("poll") == WATCH_MODE_POLL
    assert normalize_watch_mode("safe") == WATCH_MODE_POLL
    assert normalize_watch_mode("") == WATCH_MODE_HYBRID


def test_is_network_and_unc():
    assert is_unc_path(r"\\server\share\path")
    assert is_unc_path("//server/share/path")
    assert is_network_path(r"\\server\share\CNC")
    assert is_network_path("//nas/backup")
    assert not is_network_path("/tmp/local")
    assert not is_network_path(r"C:\CNC\Backups")  # non-Windows: letter ≠ remote


def test_watch_method_for_path_hybrid_vs_poll(tmp_path: Path):
    local = tmp_path / "bak"
    local.mkdir()
    unc = r"\\fileserver\cnc\share"
    assert (
        watch_method_for_path(local, WATCH_MODE_HYBRID, events_available=True)
        == METHOD_EVENTS
    )
    assert (
        watch_method_for_path(unc, WATCH_MODE_HYBRID, events_available=True)
        == METHOD_POLL
    )
    assert watch_method_for_path(local, WATCH_MODE_POLL) == METHOD_POLL
    assert (
        watch_method_for_path(local, WATCH_MODE_HYBRID, events_available=False)
        == METHOD_POLL
    )


def test_short_root_label_unc():
    assert short_root_label(r"\\srv\share\deep\path").startswith("\\\\srv\\share")


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
        mode=WATCH_MODE_POLL,
    )
    watcher.set_roots([root])
    assert watcher.seed() == 1
    assert watcher.stamp_count == 1
    assert watcher.last_poll_at is not None
    assert watcher.root_methods()[0][1] == METHOD_POLL
    watcher.start()
    try:
        (root / "new.nc").write_bytes(b"b")
        deadline = time.time() + 3.0
        while not hits and time.time() < deadline:
            time.sleep(0.1)
        assert hits, "watcher should fire after new file + debounce"
        assert watcher.stamp_count == 2
        assert watcher.last_change_at is not None
        deadline2 = time.time() + 2.0
        while not polls and time.time() < deadline2:
            time.sleep(0.1)
        assert polls, "on_poll should fire"
    finally:
        watcher.stop()


def test_hybrid_assigns_events_for_local(tmp_path: Path):
    root = tmp_path / "bak"
    root.mkdir()
    (root / "a.nc").write_bytes(b"x")
    watcher = FolderWatcher(
        on_change=lambda: None,
        mode=WATCH_MODE_HYBRID,
        poll_s=0.5,
        debounce_s=0.3,
    )
    watcher.set_roots([root, r"\\server\share"])
    assert any(
        "server" in lab.casefold() and meth == METHOD_POLL
        for lab, meth in watcher.root_methods()
    )
    if events_backend_available():
        assert any(m == METHOD_EVENTS for _, m in watcher.root_methods())
    watcher.set_mode(WATCH_MODE_POLL)
    assert all(m == METHOD_POLL for _, m in watcher.root_methods())


def test_hybrid_events_fire_on_local_change(tmp_path: Path):
    if not events_backend_available():
        return
    root = tmp_path / "bak"
    root.mkdir()
    (root / "old.nc").write_bytes(b"a")
    hits: list[int] = []
    watcher = FolderWatcher(
        on_change=lambda: hits.append(1),
        poll_s=2.0,  # slow poll — rely on events
        debounce_s=0.4,
        mode=WATCH_MODE_HYBRID,
    )
    watcher.set_roots([root])
    assert watcher.event_roots()
    watcher.seed()
    watcher.start()
    try:
        time.sleep(0.3)  # let observer settle
        (root / "new.nc").write_bytes(b"b")
        deadline = time.time() + 4.0
        while not hits and time.time() < deadline:
            time.sleep(0.1)
        assert hits, "hybrid events should fire after local file create + debounce"
        assert watcher.last_event_at is not None
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
        mode=WATCH_MODE_POLL,
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
    assert "{root}" in t("pl", "watch_strip_root_events")
    assert "Auto" in t("pl", "watch_mode_hybrid")
    assert "Poll only" in t("en", "watch_mode_poll")


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


def test_instance_ini_watch_folders_and_mode(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    cfg = InstanceConfig(
        watch_folders=True, incremental=True, watch_mode=WATCH_MODE_POLL
    )
    save_instance_ini(path, config=cfg)
    loaded = load_instance_ini(path)
    assert loaded.watch_folders is True
    assert loaded.watch_mode == WATCH_MODE_POLL
    text = path.read_text(encoding="utf-8")
    assert "watch_folders = yes" in text
    assert "watch_mode = poll" in text
    assert "OS events" in text

    path.write_text(
        "[scan]\nwatch_folders = yes\nwatch_mode = auto\n",
        encoding="utf-8",
    )
    loaded2 = load_instance_ini(path)
    assert loaded2.watch_mode == WATCH_MODE_HYBRID


def test_watch_i18n():
    assert "Obserwuj" in t("pl", "watch_folders")
    assert "Watch" in t("en", "watch_folders")
    assert "Wykryto" in t("pl", "watch_trigger")
    assert "Tylko poll" in t("pl", "watch_mode_poll")
