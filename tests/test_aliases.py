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
