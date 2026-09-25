from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap, normalize_folder_name


def test_normalize_strips_spaces_dashes_underscores():
    assert normalize_folder_name("Doosan-D") == "doosand"
    assert normalize_folder_name("doosan duzy") == "doosanduzy"
    assert normalize_folder_name("VF-2 nowa") == "vf2nowa"
    assert normalize_folder_name("SBL 500") == "sbl500"
    assert normalize_folder_name("ST-20Y") == "st20y"


def test_alias_map_known_machines(tmp_path: Path):
    am = AliasMap.load(Path(__file__).resolve().parents[1] / "aliases.yaml")
    assert am.resolve("doosan d").machine_id == "doosan-dnm-6700"
    assert am.resolve("doosan maly").machine_id == "doosan-dnm-400"
    assert am.resolve("puma").machine_id == "puma"
    assert am.resolve("SL-10").machine_id == "haas-sl-10"
    assert am.resolve("VF2 stara").machine_id == "haas-vf-2-stara"
    assert am.resolve("SBL").machine_id == "sbl-500"
    assert am.resolve("SBL").control_family == "sinumerik"
    assert am.resolve("SBL").layout == "manual_nc_folder"
    assert am.resolve("ST20Y").layout == "haas_ngc"
    assert am.resolve("UMC750").machine_id == "haas-umc750"
    assert am.resolve("UMC").machine_id == "haas-umc750"
    assert am.resolve("UMC750SS").machine_id == "haas-umc750"
    assert am.resolve("Haas UMC750").machine_id == "haas-umc750"
    assert am.resolve("VF2S").machine_id == "haas-vf-2"
    assert am.resolve("VF2 old").machine_id == "haas-vf-2"
    assert am.resolve("VF2 nowa").machine_id == "haas-vf-2-nowa"
    assert am.resolve("VF2 stara").machine_id == "haas-vf-2-stara"
    displays = am.known_machine_displays()
    assert any("UMC750" in d and "haas-umc750" in d for d in displays)


def test_unmapped_machine():
    am = AliasMap.load(Path(__file__).resolve().parents[1] / "aliases.yaml")
    info = am.resolve("Mystery Lathe")
    assert not info.mapped
    assert info.machine_id.startswith("unmapped:")


def test_local_aliases_overlay_and_persist(tmp_path: Path):
    from gcode_index.aliases import local_aliases_path_for_target
    from gcode_index.folder_map import partition_folders

    bundled = Path(__file__).resolve().parents[1] / "aliases.yaml"
    target = tmp_path / "index"
    target.mkdir()
    local_path = local_aliases_path_for_target(target)

    am = AliasMap.load(bundled)
    assert not am.resolve("ShopOddMill").mapped
    am.add_local_alias("ShopOddMill", "haas-vf-2", label="HAAS VF-2")
    am.save_local(local_path)
    assert local_path.is_file()

    merged = AliasMap.load_merged(bundled, local_path)
    hit = merged.resolve("ShopOddMill")
    assert hit.mapped
    assert hit.machine_id == "haas-vf-2"
    assert hit.label == "HAAS VF-2"
    assert merged.resolve("VF2S").machine_id == "haas-vf-2"

    part = partition_folders(["ShopOddMill", "Mystery"], merged)
    assert part.needs_manual == ["Mystery"]
    assert any(n == "ShopOddMill" for n, _ in part.auto_matched)


def test_local_alias_edit_remove_restore_bundled(tmp_path: Path):
    bundled = Path(__file__).resolve().parents[1] / "aliases.yaml"
    am = AliasMap.load_merged(bundled, None)
    # Override a bundled key locally
    am.add_local_alias("vf2s", "haas-umc750", label="HAAS UMC750")
    assert am.resolve("VF2S").machine_id == "haas-umc750"
    assert any(k == "vf2s" for k, _ in am.list_local_aliases())

    am.rename_local_alias("vf2s", "VF2S_shop")
    assert any(k == "VF2S_shop" for k, _ in am.list_local_aliases())
    assert am.resolve("VF2S_shop").machine_id == "haas-umc750"

    # Removing local override restores bundled vf2s → haas-vf-2
    am.add_local_alias("vf2s", "haas-umc750")
    assert am.resolve("VF2S").machine_id == "haas-umc750"
    assert am.remove_local_alias("vf2s")
    assert am.resolve("VF2S").machine_id == "haas-vf-2"

    path = tmp_path / "aliases.local.yaml"
    am.save_local(path)
    reloaded = AliasMap.load_merged(bundled, path)
    assert reloaded.resolve("VF2S_shop").machine_id == "haas-umc750"
    assert len(reloaded.catalog_machines()) >= 5


def test_machines_overview_and_set_aliases_for_machine(tmp_path: Path):
    bundled = Path(__file__).resolve().parents[1] / "aliases.yaml"
    am = AliasMap.load_merged(bundled, None)

    overview = am.machines_overview()
    assert overview
    vf2 = next(r for r in overview if r["machine_id"] == "haas-vf-2")
    assert "vf2s" in [a.casefold() for a in vf2["bundled_aliases"]]
    assert vf2["local_aliases"] == []
    assert not vf2["local_only"]

    am.set_local_aliases_for_machine(
        "haas-vf-2",
        ["ShopVF2", "VF2_shop"],
        label="HAAS VF-2 shop",
        layout="haas_pgm",
    )
    assert am.resolve("ShopVF2").machine_id == "haas-vf-2"
    assert am.resolve("VF2_shop").label == "HAAS VF-2 shop"
    ov2 = next(r for r in am.machines_overview() if r["machine_id"] == "haas-vf-2")
    assert ov2["local_aliases"] == ["ShopVF2", "VF2_shop"]
    # Bundled keys still listed (except those overridden by same normalize)
    assert ov2["bundled_aliases"]

    n = am.remove_local_aliases_for_machine("haas-vf-2")
    assert n == 2
    assert am.resolve("ShopVF2").mapped is False
    # Bundled vf2s restored
    assert am.resolve("VF2S").machine_id == "haas-vf-2"


def test_add_and_remove_local_only_machine(tmp_path: Path):
    bundled = Path(__file__).resolve().parents[1] / "aliases.yaml"
    path = tmp_path / "aliases.local.yaml"
    am = AliasMap.load_merged(bundled, None)

    am.set_local_aliases_for_machine(
        "shop-lathe-1",
        ["LatheOdd", "LATHE_1"],
        label="Shop Lathe 1",
        control_family="fanuc",
        layout="fanuc_all_prog",
    )
    row = next(r for r in am.machines_overview() if r["machine_id"] == "shop-lathe-1")
    assert row["local_only"] is True
    assert row["local_aliases"] == ["LATHE_1", "LatheOdd"]
    assert row["bundled_aliases"] == []

    am.save_local(path)
    reloaded = AliasMap.load_merged(bundled, path)
    assert reloaded.resolve("LatheOdd").machine_id == "shop-lathe-1"
    assert reloaded.resolve("LATHE_1").label == "Shop Lathe 1"

    reloaded.remove_local_aliases_for_machine("shop-lathe-1")
    reloaded.save_local(path)
    gone = AliasMap.load_merged(bundled, path)
    assert not any(r["machine_id"] == "shop-lathe-1" for r in gone.machines_overview())
    assert not gone.resolve("LatheOdd").mapped


def test_set_local_aliases_replaces_prior(tmp_path: Path):
    bundled = Path(__file__).resolve().parents[1] / "aliases.yaml"
    am = AliasMap.load_merged(bundled, None)
    am.set_local_aliases_for_machine("puma", ["ZZ_OldShopMill"])
    am.set_local_aliases_for_machine("puma", ["ZZ_NewShopMill", "ZZ_PumaBay"])
    locals_ = [k for k, e in am.list_local_aliases() if e.get("machine_id") == "puma"]
    assert sorted(locals_, key=str.casefold) == ["ZZ_NewShopMill", "ZZ_PumaBay"]
    assert not am.resolve("ZZ_OldShopMill").mapped
    assert am.resolve("ZZ_NewShopMill").machine_id == "puma"
