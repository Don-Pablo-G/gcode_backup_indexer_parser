"""Slim colour legend + More filters geometry / views only_green."""

from __future__ import annotations

from pathlib import Path

from gcode_index.badge_style import override_role_legend_items
from gcode_index.folder_colour_aliases import ColourCatalog, ColourDef
from gcode_index.i18n import t
from gcode_index.models import (
    ROLE_FIXTURE,
    ROLE_PERSONAL,
    ROLE_PROTOTYPE,
    ROLE_SYSTEM_PROGRAMS,
)
from gcode_index.presets import FilterPreset, load_presets, save_presets


def test_override_legend_items_seed_catalogue():
    cat = ColourCatalog()
    items_pl = override_role_legend_items(cat.colours, "pl")
    labels = {label for _sw, label in items_pl}
    assert any("rototyp" in lab or lab == "Prototyp" for lab in labels)
    # Non-override seeds must not appear
    for cid in (ROLE_PERSONAL, ROLE_SYSTEM_PROGRAMS, ROLE_FIXTURE):
        c = cat.get(cid)
        assert c is not None
        assert c.label("pl") not in labels
        assert c.label("en") not in labels
    ids_override = {
        c.id for c in cat.colours if c.can_override_main_state_colour
    }
    assert ROLE_PROTOTYPE in ids_override
    assert len(items_pl) == min(len(ids_override), 6)


def test_override_legend_respects_custom_override_and_cap():
    colours = [
        ColourDef(
            id="personal",
            label_en="Personal",
            label_pl="Osobisty",
            swatch="#AA0000",
            can_override_main_state_colour=False,
        ),
        ColourDef(
            id="sys",
            label_en="System",
            label_pl="System",
            swatch="#00AA00",
            can_override_main_state_colour=True,
        ),
        ColourDef(
            id="proto",
            label_en="Prototype",
            label_pl="Prototyp",
            swatch="#0000AA",
            can_override_main_state_colour=True,
        ),
    ]
    items = override_role_legend_items(colours, "en", cap=1)
    assert len(items) == 1
    assert items[0][1] == "System"
    items2 = override_role_legend_items(colours, "en")
    assert [lab for _s, lab in items2] == ["System", "Prototype"]


def test_legend_and_more_filters_i18n():
    assert t("pl", "colour_legend_overrides") == "Nadpisania:"
    assert t("en", "colour_legend_overrides") == "Overrides:"
    assert "Więcej filtrów" in t("pl", "more_filters")
    assert "More filters" in t("en", "more_filters")
    assert t("pl", "fewer_filters").startswith("Mniej")
    assert t("en", "fewer_filters").startswith("Fewer")
    assert t("pl", "more_filters_classification") == "Klasyfikacja"
    assert t("en", "more_filters_classification") == "Classification"
    assert t("pl", "more_filters_views") == "Widoki"
    assert t("en", "more_filters_views") == "Views"
    assert t("pl", "more_filters_ranges") == "Zakresy"
    assert t("en", "more_filters_ranges") == "Ranges"


def test_views_only_green_roundtrip(tmp_path: Path):
    path = tmp_path / "views.yaml"
    a = FilterPreset(
        name="Greens",
        text="3232",
        only_green=True,
        newest_only=True,
        role="fixture",
    )
    save_presets(path, [a])
    loaded = load_presets(path)
    assert len(loaded) == 1
    assert loaded[0].only_green is True
    assert loaded[0].newest_only is True
    bare = FilterPreset.from_dict({"name": "Legacy", "text": "1"})
    assert bare.only_green is False


def test_more_filters_uses_grid_not_pack():
    """Regression: packing into a grid parent raised TclError on expand."""
    gui = Path(__file__).resolve().parents[1] / "src" / "gcode_index" / "gui.py"
    src = gui.read_text(encoding="utf-8")
    assert "_more_filters_frame.grid(" in src
    assert "_more_filters_frame.grid_remove()" in src
    assert "_more_filters_frame.pack(" not in src
    assert "_more_filters_frame.pack_forget()" not in src
    assert "More filters: indexer + floor client" in src
    assert "override_role_legend_items" in src
    assert "colour_legend_overrides" in src
