"""Tests for Windows autostart helpers, tray availability, and desktop ini prefs."""

from __future__ import annotations

from pathlib import Path

from gcode_index.autostart_win import (
    VIA_STARTUP,
    VIA_TASK,
    is_windows,
    normalize_autostart_via,
    sync_autostart,
)
from gcode_index.i18n import t
from gcode_index.instance_ini import InstanceConfig, load_instance_ini, save_instance_ini
from gcode_index.tray_ui import tray_available


def test_normalize_autostart_via():
    assert normalize_autostart_via(None) == VIA_STARTUP
    assert normalize_autostart_via("") == VIA_STARTUP
    assert normalize_autostart_via("startup") == VIA_STARTUP
    assert normalize_autostart_via("task") == VIA_TASK
    assert normalize_autostart_via("Scheduler") == VIA_TASK
    assert normalize_autostart_via("harmonogram") == VIA_TASK
    assert normalize_autostart_via("schtasks") == VIA_TASK


def test_sync_autostart_noop_off_non_windows():
    if is_windows():
        return
    ok, msg = sync_autostart(enabled=False, via=VIA_STARTUP)
    # remove paths return True/"already removed" or Not on Windows for path None
    assert isinstance(ok, bool)
    assert isinstance(msg, str)


def test_sync_autostart_install_fails_gracefully_off_windows():
    if is_windows():
        return
    ok, msg = sync_autostart(enabled=True, via=VIA_STARTUP)
    assert ok is False
    assert "Windows" in msg


def test_desktop_ini_roundtrip(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    cfg = InstanceConfig(
        autostart=True,
        autostart_via="task",
        close_to_tray=False,
        minimize_to_tray=True,
    )
    save_instance_ini(path, config=cfg)
    text = path.read_text(encoding="utf-8")
    assert "[desktop]" in text
    assert "autostart = yes" in text
    assert "autostart_via = task" in text
    assert "close_to_tray = no" in text
    assert "minimize_to_tray = yes" in text

    loaded = load_instance_ini(path)
    assert loaded.autostart is True
    assert loaded.autostart_via == VIA_TASK
    assert loaded.close_to_tray is False
    assert loaded.minimize_to_tray is True


def test_desktop_ini_defaults_without_section(tmp_path: Path):
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
    assert cfg.autostart is False
    assert cfg.autostart_via == VIA_STARTUP
    assert cfg.close_to_tray is True
    assert cfg.minimize_to_tray is True


def test_tray_available_is_bool():
    assert isinstance(tray_available(), bool)


def test_desktop_i18n_pl_en():
    assert "Autostart" in t("pl", "autostart")
    assert "logon" in t("en", "autostart").casefold() or "Start" in t("en", "autostart")
    assert "zasobnika" in t("pl", "close_to_tray").casefold()
    assert "tray" in t("en", "close_to_tray").casefold()
    assert "Obserwacja" in t("pl", "watch_strip")
    assert "Watch" in t("en", "watch_strip")
    assert "blokada" in t("pl", "watch_strip_lock_us").casefold()
