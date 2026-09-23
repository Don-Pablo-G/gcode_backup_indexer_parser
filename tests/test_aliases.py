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


def test_unmapped_machine():
    am = AliasMap.load(Path(__file__).resolve().parents[1] / "aliases.yaml")
    info = am.resolve("Mystery Lathe")
    assert not info.mapped
    assert info.machine_id.startswith("unmapped:")
