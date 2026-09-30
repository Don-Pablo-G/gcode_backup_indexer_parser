"""Option B compact find bar — Filtry popover + dense QUERY/ACTIONS."""

from __future__ import annotations

from pathlib import Path

from gcode_index.i18n import t

GUI = Path(__file__).resolve().parents[1] / "src" / "gcode_index" / "gui.py"


def test_filters_popover_i18n():
    assert "Filtry" in t("pl", "filters_menu")
    assert "Filters" in t("en", "filters_menu")
    assert t("pl", "filters_menu_title") == "Filtry"
    assert t("en", "filters_menu_title") == "Filters"
    assert "Aktywne" in t("pl", "filters_active_tip", list="x")
    assert "Active" in t("en", "filters_active_tip", list="x")
    assert t("pl", "include_unknown_off_short")
    assert t("en", "include_unknown_off_short")


def test_find_bar_compact_layout_wire():
    src = GUI.read_text(encoding="utf-8")
    assert "Dense find bar: QUERY + ACTIONS" in src
    assert "_open_filters_popover" in src
    assert "_close_filters_popover" in src
    assert "_filters_active_count" in src
    assert "_update_filters_button" in src
    # Shape checkboxes live in the popover, not a permanent SHAPE band
    assert "shape_row1" not in src
    assert "shape_row2" not in src
    # Pipeline / collapse helpers unchanged
    assert "collapse_hide_duplicates" in src
    # Popover open state is transient (not written to ini)
    assert "filters_popover_open" not in src
    assert 'parser.get("session", "more_filters"' in (
        Path(__file__).resolve().parents[1]
        / "src"
        / "gcode_index"
        / "instance_ini.py"
    ).read_text(encoding="utf-8")
