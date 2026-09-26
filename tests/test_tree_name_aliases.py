"""Name-wide role aliases: accumulate (union) + exact tree rules."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap, normalize_folder_name
from gcode_index.folder_colour_aliases import (
    FolderColourAliasMap,
    FolderColourRule,
    collect_folder_name_frequencies,
    count_same_name_dirs,
    is_risky_alias_name,
)
from gcode_index.folder_tree_map import FolderTreeMap, FolderTreeRule, roles_from_db
from gcode_index.models import COLOUR_EXCLUDE, PROVENANCE_BACKUP, ROLE_FIXTURE, ROLE_PERSONAL
from gcode_index.scanner import scan_backup_tree

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"


def _write_nc(path: Path, ono: str = "O8001") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"%\n{ono} (ACCUM)\nG0\n%\n", encoding="utf-8")
    return path


def test_roles_accumulate_along_path(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "Pawel" / "x.nc", "O8101")
    am = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap(
        [
            FolderColourRule(alias="VF2S", colour=ROLE_FIXTURE, exact=True),
            FolderColourRule(alias="Pawel", colour=ROLE_PERSONAL, exact=True),
        ]
    )
    result = scan_backup_tree(bak, am, colour_map=colours)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    inst = by[hit.resolve()]
    assert inst.provenance == PROVENANCE_BACKUP
    roles = roles_from_db(inst.role)
    assert ROLE_FIXTURE in roles
    assert ROLE_PERSONAL in roles


def test_exact_rule_no_fuzzy_blast(tmp_path: Path):
    """Tree-created exact rules must not fuzzy-match longer names."""
    colours = FolderColourAliasMap(
        [FolderColourRule(alias="Fix", colour=ROLE_FIXTURE, exact=True)]
    )
    assert colours.match_segment("Fix") == ROLE_FIXTURE
    assert colours.match_segment("Fixture") is None  # would fuzzy-match if not exact
    # Legacy fuzzy still works when exact=False
    fuzzy = FolderColourAliasMap(
        [FolderColourRule(alias="Fix", colour=ROLE_FIXTURE, exact=False)]
    )
    assert fuzzy.match_segment("Fixture") == ROLE_FIXTURE


def test_path_tags_replace_name_union(tmp_path: Path):
    bak = tmp_path / "bak"
    pawel = bak / "15.09.2026" / "VF2S" / "Pawel"
    hit = _write_nc(pawel / "x.nc", "O8201")
    other_date = _write_nc(
        bak / "16.09.2026" / "VF2S" / "Pawel" / "y.nc", "O8202"
    )
    am = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap(
        [
            FolderColourRule(alias="VF2S", colour=ROLE_FIXTURE, exact=True),
            FolderColourRule(alias="Pawel", colour=ROLE_PERSONAL, exact=True),
        ]
    )
    tree = FolderTreeMap(
        rules=[
            FolderTreeRule(path=str(pawel), tags=["prototype"]),
        ]
    )
    result = scan_backup_tree(bak, am, colour_map=colours, tree_map=tree)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    # Path rule replaces union on that prefix only
    assert roles_from_db(by[hit.resolve()].role) == ["prototype"]
    # Other dates keep name-union
    other_roles = roles_from_db(by[other_date.resolve()].role)
    assert ROLE_FIXTURE in other_roles
    assert ROLE_PERSONAL in other_roles


def test_risky_alias_names():
    assert is_risky_alias_name("ab")[0] is True
    assert is_risky_alias_name("ab")[1] == "short"
    assert is_risky_alias_name("Memory")[1] == "memory"
    assert is_risky_alias_name("15.09.2026")[1] == "date"
    assert is_risky_alias_name("Pawel")[0] is False


def test_count_same_name_dirs(tmp_path: Path):
    a = tmp_path / "d1" / "Pawel"
    b = tmp_path / "d2" / "sub" / "pawel"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    assert count_same_name_dirs([tmp_path], "Pawel") == 2
    assert normalize_folder_name("Pawel") == normalize_folder_name("pawel")


def test_collect_folder_name_frequencies_sorts_by_count(tmp_path: Path):
    bak = tmp_path / "bak"
    extra = tmp_path / "extra"
    # Pawel x3, Memory x2, Unique x1 — also case variants of Pawel
    (bak / "15.09.2026" / "VF2" / "Pawel").mkdir(parents=True)
    (bak / "16.09.2026" / "VF2" / "pawel").mkdir(parents=True)
    (bak / "17.09.2026" / "UMC" / "Pawel").mkdir(parents=True)
    (bak / "15.09.2026" / "VF2" / "Memory").mkdir(parents=True)
    (extra / "Memory").mkdir(parents=True)
    (extra / "UniqueOnly").mkdir(parents=True)
    entries = collect_folder_name_frequencies([bak, extra])
    by_key = {e.key: e for e in entries}
    pawel_key = normalize_folder_name("Pawel")
    assert by_key[pawel_key].count == 3
    # Representative spelling is the most common (Pawel appears twice vs pawel once)
    assert by_key[pawel_key].name == "Pawel"
    assert by_key[normalize_folder_name("Memory")].count == 2
    assert by_key[normalize_folder_name("UniqueOnly")].count == 1
    # Sorted most frequent first
    assert entries[0].key == pawel_key
    assert entries[0].count >= entries[1].count


def test_exclude_any_segment_drops(tmp_path: Path):
    bak = tmp_path / "bak"
    _write_nc(bak / "15.09.2026" / "scrap" / "x.nc", "O8301")
    am = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap(
        [FolderColourRule(alias="scrap", colour=COLOUR_EXCLUDE, exact=True)]
    )
    result = scan_backup_tree(bak, am, colour_map=colours)
    assert result.instances == []
