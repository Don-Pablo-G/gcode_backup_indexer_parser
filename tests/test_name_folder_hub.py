"""Nazwy folderów hub: id suggest, chip i18n, create+bind catalogue paths."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.folder_colour_aliases import (
    ColourCatalog,
    ColourDef,
    FolderColourAliasMap,
    load_colour_catalog,
    save_colour_catalog,
)
from gcode_index.i18n import t
from gcode_index.odbiorca_aliases import (
    OdbiorcaCatalog,
    OdbiorcaDef,
    load_odbiorca_catalog,
    save_odbiorca_catalog,
)


def test_suggest_id_from_folder_spelling():
    from gcode_index.gui import FolderNameBrowserDialog

    assert FolderNameBrowserDialog._suggest_id("Acme Corp") == "acme_corp"
    assert FolderNameBrowserDialog._suggest_id("  VF-2SS ") == "vf_2ss"
    assert FolderNameBrowserDialog._suggest_id("12Parts") == "n_12parts"
    assert FolderNameBrowserDialog._suggest_id("!!!") == "item"


def test_hub_chip_i18n_pl_en():
    assert "VF2" in t("pl", "name_browser_chip_machine", value="VF2")
    assert t("pl", "name_browser_chip_machine", value="VF2").startswith("maszyna:")
    assert t("en", "name_browser_chip_machine", value="VF2").startswith("machine:")
    assert "fixture" in t("pl", "name_browser_chip_role", value="fixture")
    assert t("pl", "name_browser_chip_role", value="x").startswith("funkcja:")
    assert t("en", "name_browser_chip_role", value="x").startswith("function:")
    assert t("pl", "name_browser_chip_odbiorca", value="Acme").startswith("odbiorca:")
    assert t("en", "name_browser_chip_odbiorca", value="Acme").startswith("recipient:")
    assert "Nowy odbiorca" in t("pl", "name_hub_odbiorca_new")
    assert "New machine" in t("en", "name_hub_machine_new")


def test_hub_create_machine_and_alias_from_name(tmp_path: Path):
    """Hub 'new machine from name' writes local alias with spelling as first alias."""
    aliases = AliasMap({})
    spelling = "Puma2100Y"
    mid = "puma2100y"
    aliases.add_local_alias(
        spelling,
        mid,
        label="Puma 2100Y",
        control_family="fanuc",
        layout="fanuc_all_fldr",
    )
    out = aliases.save_local(tmp_path / "aliases.local.yaml")
    loaded = AliasMap.load(out)
    info = loaded.resolve(spelling)
    assert info.mapped
    assert info.machine_id == mid
    assert (info.label or "").startswith("Puma")


def test_hub_create_role_and_exact_alias(tmp_path: Path):
    path = tmp_path / "folder_colour_aliases.yaml"
    catalog = ColourCatalog()
    spelling = "Uchwyty"
    role_id = "uchwyty"
    new_def = ColourDef(
        id=role_id,
        label_pl=spelling,
        label_en=spelling,
        swatch="#888888",
        meaning_pl="",
        meaning_en="",
        badge="●",
        builtin=False,
    )
    colour_map = FolderColourAliasMap(
        list(catalog.rules), known_ids=catalog.colour_ids | {role_id}
    )
    colour_map.upsert_exact_role(spelling, role_id)
    catalog = ColourCatalog(
        colours=list(catalog.colours) + [new_def],
        rules=list(colour_map.rules),
    )
    save_colour_catalog(path, catalog)
    loaded = load_colour_catalog(path)
    assert loaded.get(role_id) is not None
    amap = FolderColourAliasMap(loaded.rules, known_ids=loaded.colour_ids)
    rule = amap.rule_for_name(spelling)
    assert rule is not None
    assert rule.colour == role_id
    assert rule.exact is True


def test_hub_create_odbiorca_and_exact_alias(tmp_path: Path):
    path = tmp_path / "odbiorcy.yaml"
    spelling = "Acme Polska"
    oid = "acme_polska"
    cmap = OdbiorcaCatalog().alias_map()
    cmap.upsert_exact(spelling, oid)
    cat = OdbiorcaCatalog(
        odbiorcy=[OdbiorcaDef(id=oid, label_pl=spelling, label_en=spelling)],
        rules=list(cmap.rules),
    )
    save_odbiorca_catalog(path, cat)
    loaded = load_odbiorca_catalog(path)
    assert loaded.get(oid) is not None
    rule = loaded.alias_map().rule_for_name(spelling)
    assert rule is not None
    assert rule.odbiorca_id == oid
    assert rule.exact is True
