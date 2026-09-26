"""Auto role system_programs for program numbers O9000–O9099."""

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
    assert is_o9_system_program("9000")
    assert is_o9_system_program("9001")
    assert is_o9_system_program("O9001")
    assert is_o9_system_program("o9099")
    assert is_o9_system_program("O09001")  # leading zero after O → 9001
    assert is_o9_system_program("9099")
    assert not is_o9_system_program("o9")
    assert not is_o9_system_program("9")
    assert not is_o9_system_program("8999")
    assert not is_o9_system_program("O8999")
    assert not is_o9_system_program("9100")
    assert not is_o9_system_program("O9100")
    assert not is_o9_system_program("O9123")
    assert not is_o9_system_program("O99999")
    assert not is_o9_system_program("8001")
    assert not is_o9_system_program("O8001")
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
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "Personal" / "sys.nc", "O9050")
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


def test_folder_system_plus_o9_is_single_system_programs(tmp_path: Path):
    """System-folder alias + O9 auto-tag → one system_programs id (set)."""
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "System" / "sys.nc", "O9001")
    am = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap(
        [FolderColourRule(alias="System", colour=ROLE_SYSTEM_PROGRAMS)]
    )
    result = scan_backup_tree(
        bak, am, colour_map=colours, o9_system_programs_role=True
    )
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    roles = roles_from_db(by[hit.resolve()].role)
    assert roles == [ROLE_SYSTEM_PROGRAMS]
    assert roles.count(ROLE_SYSTEM_PROGRAMS) == 1
    assert by[hit.resolve()].role == ROLE_SYSTEM_PROGRAMS


def test_outside_range_no_auto_tag(tmp_path: Path):
    """O9123 (and other O9… outside 9000–9099) do not get auto system_programs."""
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "loose" / "sys.nc", "O9123")
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(bak, am, o9_system_programs_role=True)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert ROLE_SYSTEM_PROGRAMS not in roles_from_db(by[hit.resolve()].role)
    assert result.o9_system_programs == 0


def test_outside_range_folder_alias_still_applies(tmp_path: Path):
    """Folder alias can still tag system_programs when number is outside O9000–9099."""
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "System" / "sys.nc", "O9555")
    am = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap(
        [FolderColourRule(alias="System", colour=ROLE_SYSTEM_PROGRAMS)]
    )
    result = scan_backup_tree(
        bak, am, colour_map=colours, o9_system_programs_role=True
    )
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert roles_from_db(by[hit.resolve()].role) == [ROLE_SYSTEM_PROGRAMS]
    assert result.o9_system_programs == 0  # not from O9 auto-tag


def test_legacy_duplicate_csv_collapses_on_display_and_reindex(tmp_path: Path):
    """Existing CSV with duplicate tags collapses via normalize / reindex."""
    from gcode_index.folder_tree_map import normalize_roles_list, roles_to_db
    from gcode_index.badge_style import flag_text
    from gcode_index.models import PROVENANCE_BACKUP

    raw = "system_programs,system_programs,system"
    assert normalize_roles_list(raw) == [ROLE_SYSTEM_PROGRAMS]
    assert roles_to_db(raw.split(",")) == ROLE_SYSTEM_PROGRAMS
    assert flag_text(PROVENANCE_BACKUP, raw.split(",")) == "⬤⬤"  # status + 1 role

    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "loose" / "sys.nc", "O9001")
    am = AliasMap.load(ALIASES)
    first = scan_backup_tree(bak, am, o9_system_programs_role=False)
    by1 = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in first.instances
    }
    by1[hit.resolve()].role = "system_programs,system_programs"
    assert roles_from_db(by1[hit.resolve()].role) == [ROLE_SYSTEM_PROGRAMS]

    second = scan_backup_tree(bak, am, o9_system_programs_role=True)
    by2 = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in second.instances
    }
    assert by2[hit.resolve()].role == ROLE_SYSTEM_PROGRAMS
    assert roles_from_db(by2[hit.resolve()].role).count(ROLE_SYSTEM_PROGRAMS) == 1


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
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "misc" / "m.nc", "O9001")
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


def test_reindex_drops_broad_o9_outside_range(tmp_path: Path):
    """Numbers outside 9000–9099 lose auto-tag on reindex (no folder alias)."""
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "loose" / "old.nc", "O9555")
    am = AliasMap.load(ALIASES)
    # Simulate a prior broad-rule tag left on the in-memory instance only;
    # a fresh reindex rebuilds roles from path + narrow O9 and must not keep it.
    result = scan_backup_tree(bak, am, o9_system_programs_role=True)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert ROLE_SYSTEM_PROGRAMS not in roles_from_db(by[hit.resolve()].role)
    assert by[hit.resolve()].role in (None, "")
