"""Helpers for folder-colour swatch / palette input."""

from __future__ import annotations

from gcode_index.folder_colour_aliases import (
    COLOUR_PRESET_SWATCHES,
    normalize_hex_colour,
)


def test_normalize_hex_colour():
    assert normalize_hex_colour("#1a7f37") == "#1A7F37"
    assert normalize_hex_colour("b58900") == "#B58900"
    assert normalize_hex_colour("#abc") == "#AABBCC"
    assert normalize_hex_colour("xyz") == "#888888"
    assert normalize_hex_colour("notahex") == "#888888"
    assert normalize_hex_colour(None) == "#888888"
    assert normalize_hex_colour("", fallback="#112233") == "#112233"


def test_preset_palette_is_valid_hex():
    assert len(COLOUR_PRESET_SWATCHES) >= 6
    for sw in COLOUR_PRESET_SWATCHES:
        assert normalize_hex_colour(sw) == sw.upper()
