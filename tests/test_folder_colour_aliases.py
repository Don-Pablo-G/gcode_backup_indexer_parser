"""Folder colour aliases: green/yellow/red overrides + exclude."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.folder_colour_aliases import (
    FolderColourAliasMap,
    FolderColourRule,
    load_folder_colour_rules,
    save_folder_colour_rules,
)
from gcode_index.models import (
    COLOUR_EXCLUDE,
    PROVENANCE_BACKUP,
    PROVENANCE_EXTRA,
    PROVENANCE_WIP,
)
from gcode_index.scanner import scan_backup_tree, scan_with_extra_roots

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"


def _write_nc(path: Path, ono: str = "O5001") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"%\n{ono} (COLOUR)\nG0\n%\n", encoding="utf-8")
    return path


def test_yaml_roundtrip(tmp_path: Path):
    path = tmp_path / "folder_colour_aliases.yaml"
    save_folder_colour_rules(
        path,
        [
            FolderColourRule(alias="Pawel", colour="red"),
            FolderColourRule(alias="scrap", colour="exclude"),
            FolderColourRule(alias="catch", colour="yellow"),
        ],
    )
    loaded = load_folder_colour_rules(path)
    assert len(loaded) == 3
    by = {r.alias: r.colour for r in loaded}
    assert by["Pawel"] == PROVENANCE_WIP
    assert by["scrap"] == COLOUR_EXCLUDE
    assert by["catch"] == PROVENANCE_EXTRA


def test_deepest_segment_wins():
    m = FolderColourAliasMap(
        [
            FolderColourRule(alias="VF2", colour="green"),
            FolderColourRule(alias="Pawel", colour="red"),
        ]
    )
    assert m.resolve_path_parts(["15.09.2026", "VF2", "Pawel"]) == PROVENANCE_WIP
    assert m.resolve_source_path("15.09.2026/VF2/Pawel/O1.nc") == PROVENANCE_WIP
    assert m.resolve_source_path("15.09.2026/VF2/O1.nc") == PROVENANCE_BACKUP


def test_red_override_inside_backup(tmp_path: Path):
    bak = tmp_path / "bak"
    normal = _write_nc(bak / "15.09.2026" / "OddMill" / "ok.nc", "O5101")
    wip = _write_nc(bak / "15.09.2026" / "OddMill" / "Pawel" / "wip.nc", "O5102")
    am = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap(
        [FolderColourRule(alias="Pawel", colour=PROVENANCE_WIP)]
    )
    result = scan_backup_tree(bak, am, colour_map=colours)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert by[normal.resolve()].provenance == PROVENANCE_BACKUP
    assert by[wip.resolve()].provenance == PROVENANCE_WIP


def test_exclude_skips_branch(tmp_path: Path):
    bak = tmp_path / "bak"
    keep = _write_nc(bak / "keep.nc", "O5201")
    _write_nc(bak / "trash" / "gone.nc", "O5202")
    am = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap(
        [FolderColourRule(alias="trash", colour=COLOUR_EXCLUDE)]
    )
    result = scan_backup_tree(bak, am, colour_map=colours)
    paths = {
        (Path(i.scan_root or "") / i.source_path).resolve() for i in result.instances
    }
    assert keep.resolve() in paths
    assert not any(p.name == "gone.nc" for p in paths)


def test_yellow_override_inside_backup(tmp_path: Path):
    bak = tmp_path / "bak"
    _write_nc(bak / "15.09.2026" / "OddMill" / "shop" / "extra.nc", "O5301")
    am = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap(
        [FolderColourRule(alias="shop", colour=PROVENANCE_EXTRA)]
    )
    result = scan_with_extra_roots(bak, am, colour_map=colours)
    assert result.instances
    assert all(i.provenance == PROVENANCE_EXTRA for i in result.instances)
