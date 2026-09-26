"""Auto role system_programs for any O9… program number."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.folder_colour_aliases import FolderColourAliasMap, FolderColourRule
from gcode_index.folder_tree_map import roles_from_db
from gcode_index.models import (
    ROLE_PERSONAL,
    ROLE_SYSTEM_PROGRAMS,
    is_o9_system_program,
)
from gcode_index.scanner import scan_backup_tree

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"


def _write_nc(path: Path, ono: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"%\n{ono} (PART)\nG0\n%\n", encoding="utf-8")
    return path


def test_is_o9_system_program_match():
    assert is_o9_system_program("9001")
    assert is_o9_system_program("O9001")
    assert is_o9_system_program("o9")
    assert is_o9_system_program("O99999")
    assert is_o9_system_program("9")
    assert not is_o9_system_program("8001")
    assert not is_o9_system_program("O8001")
    assert not is_o9_system_program("O09001")  # leading 0 after O — not starting with 9
    assert not is_o9_system_program("")
    assert not is_o9_system_program(None)
    assert not is_o9_system_program("O")


def test_o9_adds_system_programs_role(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "loose" / "sys.nc", "O9001")
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(bak, am, o9_system_programs_role=True)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    roles = roles_from_db(by[hit.resolve()].role)
    assert ROLE_SYSTEM_PROGRAMS in roles
    assert result.o9_system_programs >= 1


def test_o9_accumulates_with_folder_role(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "Personal" / "sys.nc", "O9123")
    am = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap(
        [FolderColourRule(alias="Personal", colour=ROLE_PERSONAL)]
    )
    result = scan_backup_tree(
        bak, am, colour_map=colours, o9_system_programs_role=True
    )
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    roles = roles_from_db(by[hit.resolve()].role)
    assert ROLE_PERSONAL in roles
    assert ROLE_SYSTEM_PROGRAMS in roles


def test_o9_toggle_off(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "loose" / "sys.nc", "O9001")
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(bak, am, o9_system_programs_role=False)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    roles = roles_from_db(by[hit.resolve()].role)
    assert ROLE_SYSTEM_PROGRAMS not in roles
    assert result.o9_system_programs == 0


def test_non_o9_unaffected(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "loose" / "part.nc", "O1234")
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(bak, am, o9_system_programs_role=True)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    roles = roles_from_db(by[hit.resolve()].role)
    assert ROLE_SYSTEM_PROGRAMS not in roles


def test_reindex_backfills_o9_role(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "misc" / "m.nc", "O9555")
    am = AliasMap.load(ALIASES)
    first = scan_backup_tree(bak, am, o9_system_programs_role=False)
    by1 = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in first.instances
    }
    assert ROLE_SYSTEM_PROGRAMS not in roles_from_db(by1[hit.resolve()].role)

    second = scan_backup_tree(bak, am, o9_system_programs_role=True)
    by2 = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in second.instances
    }
    assert ROLE_SYSTEM_PROGRAMS in roles_from_db(by2[hit.resolve()].role)
    assert second.o9_system_programs >= 1
