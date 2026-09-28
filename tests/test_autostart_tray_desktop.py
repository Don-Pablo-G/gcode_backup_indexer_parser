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
    assert cfg.close_to_tray is False
    assert cfg.minimize_to_tray is False


def test_desktop_ini_preserves_explicit_yes(tmp_path: Path):
    """Existing indexer installs that already had tray on keep yes after upgrade."""
    path = tmp_path / "gcode-index.ini"
    path.write_text(
        """
[desktop]
autostart = yes
autostart_via = startup
close_to_tray = yes
minimize_to_tray = yes
""",
        encoding="utf-8",
    )
    cfg = load_instance_ini(path)
    assert cfg.autostart is True
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
    assert t("pl", "menu_settings") == "Ustawienia"
    assert t("en", "menu_settings") == "Settings"
    assert "Ustawienia" in t("pl", "settings_open")
    assert "Settings" in t("en", "settings_open")


def test_tray_gates_not_tied_to_is_simple():
    """Close/minimize→tray must work in all modes (no can_index / _is_simple gate)."""
    from pathlib import Path

    gui_path = Path(__file__).resolve().parents[1] / "src" / "gcode_index" / "gui.py"
    text = gui_path.read_text(encoding="utf-8")

    def _method_body(name: str) -> str:
        marker = f"    def {name}("
        start = text.index(marker)
        rest = text[start + len(marker) :]
        # Next top-level method at same indent
        next_def = rest.find("\n    def ")
        assert next_def > 0
        return rest[:next_def]

    close_src = _method_body("_on_close")
    minimize_src = _method_body("_on_minimize_event")
    assert "_is_simple" not in close_src
    assert "_is_simple" not in minimize_src
    assert "close_to_tray_var" in close_src
    assert "minimize_to_tray_var" in minimize_src
