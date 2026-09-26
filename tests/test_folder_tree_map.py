"""Path-specific folder tree map + multi-tag roles."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.db import open_db, query_instances, write_scan_result
from gcode_index.folder_colour_aliases import (
    FolderColourAliasMap,
    FolderColourRule,
)
from gcode_index.folder_tree_map import (
    FolderTreeMap,
    FolderTreeRule,
    load_folder_tree_map,
    normalize_roles_list,
    roles_from_db,
    roles_to_db,
    save_folder_tree_map,
    tree_map_path_for_target,
)
from gcode_index.models import ROLE_FIXTURE, ROLE_WIP
from gcode_index.scanner import scan_backup_tree

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"


def _write_nc(path: Path, ono: str = "O7001") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"%\n{ono} (TREE)\nG0\n%\n", encoding="utf-8")
    return path


def test_normalize_roles_multi_and_csv():
    assert normalize_roles_list(["fixture", "wip", "fixture"]) == ["fixture", "wip"]
    assert normalize_roles_list("wip, fixture") == ["fixture", "wip"]
    assert roles_to_db(["wip", "fixture"]) == "fixture,wip"
    assert roles_from_db("fixture,wip") == ["fixture", "wip"]
    assert roles_from_db("wip") == ["wip"]
    assert roles_from_db(None) == []
    # Exact duplicates and aliases collapse to one canonical id
    assert normalize_roles_list("system_programs,system_programs") == [
        "system_programs"
    ]
    assert normalize_roles_list(["system", "system_programs", "orange"]) == [
        "system_programs"
    ]
    assert roles_to_db(["System Programs", "system_programs"]) == "system_programs"


def test_longest_prefix_wins(tmp_path: Path):
    root = tmp_path / "bak"
    deep = root / "15.09.2026" / "VF2S" / "Pawel"
    deep.mkdir(parents=True)
    tm = FolderTreeMap(
        rules=[
            FolderTreeRule(path=str(root / "15.09.2026"), tags=["production"]),
            FolderTreeRule(path=str(deep), tags=["wip", "fixture"]),
        ]
    )
    hit = tm.resolve(deep / "O1.nc")
    assert hit is not None
    assert hit.tags == ["fixture", "wip"]
    parent = tm.resolve(root / "15.09.2026" / "VF2S" / "other.nc")
    assert parent is not None
    assert parent.tags == ["production"]


def test_yaml_roundtrip(tmp_path: Path):
    path = tree_map_path_for_target(tmp_path)
    tm = FolderTreeMap(
        rules=[
            FolderTreeRule(
                path=str(tmp_path / "a" / "b"),
                tags=["wip", "fixture"],
                machine_id="haas-vf-2",
            ),
            FolderTreeRule(path=str(tmp_path / "scrap"), exclude=True),
        ]
    )
    save_folder_tree_map(path, tm)
    loaded = load_folder_tree_map(path)
    assert len(loaded) == 2
    rule = loaded.get_exact(tmp_path / "a" / "b")
    assert rule is not None
    assert rule.tags == ["fixture", "wip"]
    assert rule.machine_id == "haas-vf-2"
    ex = loaded.get_exact(tmp_path / "scrap")
    assert ex is not None and ex.exclude


def test_tree_map_multi_tag_and_exclude_scan(tmp_path: Path):
    backup = tmp_path / "backup"
    keep = backup / "01.01.2026" / "Loose"
    drop = backup / "01.01.2026" / "Scrap"
    _write_nc(keep / "a.nc", "O7101")
    _write_nc(drop / "b.nc", "O7102")
    aliases = AliasMap.load(ALIASES)
    tm = FolderTreeMap(
        rules=[
            FolderTreeRule(path=str(keep), tags=["fixture", "wip"]),
            FolderTreeRule(path=str(drop), exclude=True),
        ]
    )
    result = scan_backup_tree(backup, aliases, tree_map=tm)
    assert len(result.instances) == 1
    inst = result.instances[0]
    assert roles_from_db(inst.role) == ["fixture", "wip"]
    assert ROLE_WIP in roles_from_db(inst.role)
    assert ROLE_FIXTURE in roles_from_db(inst.role)


def test_tree_map_beats_name_alias(tmp_path: Path):
    backup = tmp_path / "backup"
    folder = backup / "01.01.2026" / "Pawel"
    _write_nc(folder / "x.nc", "O7201")
    aliases = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap(
        rules=[FolderColourRule(alias="Pawel", colour="production")]
    )
    tm = FolderTreeMap(
        rules=[FolderTreeRule(path=str(folder), tags=["wip", "personal"])]
    )
    result = scan_backup_tree(backup, aliases, colour_map=colours, tree_map=tm)
    assert len(result.instances) == 1
    assert roles_from_db(result.instances[0].role) == ["personal", "wip"]


def test_db_role_filter_matches_any_tag(tmp_path: Path):
    backup = tmp_path / "backup"
    folder = backup / "01.01.2026" / "Loose"
    _write_nc(folder / "a.nc", "O7301")
    aliases = AliasMap.load(ALIASES)
    tm = FolderTreeMap(rules=[FolderTreeRule(path=str(folder), tags=["fixture", "wip"])])
    result = scan_backup_tree(backup, aliases, tree_map=tm)
    db = tmp_path / "gcode_index.sqlite"
    conn = open_db(db)
    write_scan_result(conn, backup_root=str(backup), aliases_path=str(ALIASES), result=result)
    rows_wip = query_instances(conn, role="wip")
    rows_fix = query_instances(conn, role="fixture")
    rows_prod = query_instances(conn, role="production")
    assert len(rows_wip) == 1
    assert len(rows_fix) == 1
    assert len(rows_prod) == 0
    conn.close()


def test_inherited_vs_exact(tmp_path: Path):
    parent = tmp_path / "p"
    child = parent / "c"
    child.mkdir(parents=True)
    tm = FolderTreeMap(rules=[FolderTreeRule(path=str(parent), tags=["wip"])])
    exact, inherited = tm.inherited_from(child)
    assert exact is None
    assert inherited is not None and inherited.tags == ["wip"]
    tm.set_rule(child, tags=["fixture"])
    exact2, inherited2 = tm.inherited_from(child)
    assert exact2 is not None and exact2.tags == ["fixture"]
    assert inherited2 is not None and inherited2.tags == ["wip"]


def test_collect_tree_map_roots_accepts_scan_root_specs(tmp_path: Path):
    """Regression: Mapuj drzewo unpackaged ScanRootSpec as tuples → silent no-op."""
    from gcode_index.extra_roots import ScanRootSpec
    from gcode_index.folder_tree_map import collect_tree_map_roots
    from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA

    backup = tmp_path / "backup"
    extra = tmp_path / "extra"
    backup.mkdir()
    extra.mkdir()
    missing = tmp_path / "gone"
    specs = [
        ScanRootSpec(path=str(extra), provenance=PROVENANCE_EXTRA),
        ScanRootSpec(path=str(missing), provenance=PROVENANCE_BACKUP),
    ]
    roots, skipped = collect_tree_map_roots(backup, specs)
    assert {p.resolve() for p in roots} == {backup.resolve(), extra.resolve()}
    assert any("gone" in s for s in skipped)
    # Tuple form still accepted (defensive)
    roots2, _ = collect_tree_map_roots(None, [(str(extra), PROVENANCE_EXTRA)])
    assert roots2[0].resolve() == extra.resolve()
