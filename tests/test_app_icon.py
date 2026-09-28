"""Tests for packaged app icon resolution (window / tray / About / exe)."""

from __future__ import annotations

from gcode_index.app_icon import (
    resolve_app_ico,
    resolve_app_png,
    resolve_best_png,
)
from gcode_index.tray_ui import _make_icon_image


def test_resolve_app_ico_exists():
    path = resolve_app_ico()
    assert path is not None
    assert path.name == "app.ico"
    assert path.is_file()
    assert path.stat().st_size > 100


def test_resolve_app_png_sizes():
    for size in (16, 32, 64, 128, 256):
        path = resolve_app_png(size)
        assert path is not None, size
        assert path.name == f"app-{size}.png"
        assert path.is_file()


def test_resolve_best_png_prefers_requested():
    path = resolve_best_png(32, 16)
    assert path is not None
    assert path.name == "app-32.png"


def test_tray_icon_loads_packaged_mark():
    img = _make_icon_image()
    assert img.mode == "RGBA"
    # Packaged preference is 32×32 PNG.
    assert img.size == (32, 32)
