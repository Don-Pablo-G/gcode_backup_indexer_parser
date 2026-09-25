"""Single-instance guard (POSIX lock-file path used in CI)."""

from __future__ import annotations

import sys
import time

from gcode_index.single_instance import (
    signal_existing_instance,
    try_acquire,
)


def test_single_instance_second_acquire_fails():
    first = try_acquire()
    assert first is not None
    assert first.owned
    try:
        second = try_acquire()
        assert second is None
    finally:
        first.release()
    # After release, a new acquire should succeed again
    third = try_acquire()
    assert third is not None
    third.release()


def test_signal_existing_triggers_callback():
    if sys.platform == "win32":
        # Event path is covered on Windows builds; keep Linux CI reliable.
        pass
    hits: list[int] = []
    guard = try_acquire()
    assert guard is not None
    try:
        guard.watch_activation(lambda: hits.append(1))
        assert signal_existing_instance() is True
        deadline = time.time() + 3.0
        while not hits and time.time() < deadline:
            time.sleep(0.05)
        assert hits, "activation watcher should fire after signal"
    finally:
        guard.release()
