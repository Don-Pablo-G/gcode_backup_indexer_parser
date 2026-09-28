"""Role + machine from G-code header — normalize, precedence, tip, reindex."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap, normalize_folder_name
from gcode_index.folder_colour_aliases import (
    FolderColourAliasMap,
    FolderColourRule,
)
from gcode_index.folder_map import FolderMachineMap
from gcode_index.folder_tree_map import FolderTreeMap, FolderTreeRule, roles_from_db
from gcode_index.header_match import (
    MIN_HEADER_NEEDLE,
    extract_header_paren_comments,
    match_machine_from_header,
    match_machine_in_comments,
    match_roles_from_header,
    match_roles_in_comments,
)
from gcode_index.models import (
    ROLE_FIXTURE,
    ROLE_PERSONAL,
    ROLE_PROTOTYPE,
    ROLE_SYSTEM_PROGRAMS,
)
from gcode_index.odbiorca_aliases import extract_header_paren_comments as extract_odb
from gcode_index.role_explain import REASON_HEADER, REASON_PATH, explain_row_roles
from gcode_index.scanner import UNKNOWN_MACHINE_ID, scan_backup_tree

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"


def _write_nc(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _colour_map(*pairs: tuple[str, str]) -> FolderColourAliasMap:
    return FolderColourAliasMap(
        [
            FolderColourRule(alias=alias, colour=rid, exact=True)
            for alias, rid in pairs
        ]
    )


def test_extract_shared_with_odbiorca(tmp_path: Path):
    nc = _write_nc(tmp_path / "p.nc", "%\nO1 (PROTO)\nG0\n%\n")
    assert extract_header_paren_comments(nc) == extract_odb(nc)


def test_match_roles_longest_and_union():
    cmap = _colour_map(("PROTO", ROLE_PROTOTYPE), ("Pawel", ROLE_PERSONAL))
    hits = match_roles_in_comments(["PROTO order", "Pawel"], cmap)
    assert hits[ROLE_PROTOTYPE] == "PROTO"
    assert hits[ROLE_PERSONAL] == "Pawel"
    # Exact token in multi-word comment
    assert match_roles_in_comments(["PROTO bay"], cmap)[ROLE_PROTOTYPE] == "PROTO"
    # Substring ≥4 within token: PROTO in PROTOExtra still hits
    assert match_roles_in_comments(["PROTOExtra"], cmap)[ROLE_PROTOTYPE] == "PROTO"
    # Too-short needle skipped
    short = _colour_map(("AB", ROLE_FIXTURE))
    assert len(normalize_folder_name("AB")) < MIN_HEADER_NEEDLE
    assert match_roles_in_comments(["AB"], short) == {}
    # 3-char mid-string does not substring-hit; Fix→Fixture residual too long
    mid = _colour_map(("Fix", ROLE_FIXTURE))
    assert match_roles_in_comments(["XFixY"], mid) == {}
    assert match_roles_in_comments(["Fixture"], mid) == {}
    assert match_roles_in_comments(["Fix_bay"], mid)[ROLE_FIXTURE] == "Fix"
    # pat vs pattyn / pat_backup on O-line bodies
    pat = _colour_map(("pat", ROLE_PERSONAL))
    assert match_roles_in_comments(["pattyn"], pat) == {}
    assert match_roles_in_comments(["pat_backup"], pat)[ROLE_PERSONAL] == "pat"


def test_match_machine_longest_and_exact():
    am = AliasMap(
        {
            "vf2": {"machine_id": "haas-vf-2", "label": "VF-2"},
            "vf2s": {"machine_id": "haas-vf-2", "label": "VF-2SS"},
            "umc750": {"machine_id": "haas-umc750", "label": "UMC-750"},
        }
    )
    hit = match_machine_in_comments(["VF2S job"], am)
    assert hit is not None
    assert hit[0] == "haas-vf-2"
    assert hit[1] == "vf2s"  # longer needle wins over vf2
    hit2 = match_machine_in_comments(["UMC750"], am)
    assert hit2 is not None
    assert hit2[0] == "haas-umc750"


def test_body_comment_below_o_line_ignored(tmp_path: Path):
    """Alias on a later line (even within old 40-line window) must not match."""
    nc = _write_nc(
        tmp_path / "p.nc",
        "%\n"
        "O1234 (loose)\n"
        "(LP1)\n"
        "G0\n"
        "G1 X0\n"
        "(PROTO)\n"  # line 5 — false-positive if multi-line window still used
        "(VF2S)\n"
        + "\n".join(f"G1 X{i}" for i in range(50))
        + "\n(PROTO)\n(VF2S)\nM30\n%\n",
    )
    comments = extract_header_paren_comments(nc, max_lines=40)
    assert comments == ["loose"]
    assert "PROTO" not in comments
    assert "VF2S" not in comments
    cmap = _colour_map(("PROTO", ROLE_PROTOTYPE))
    am = AliasMap.load(ALIASES)
    assert match_roles_from_header(nc, cmap) == {}
    assert match_machine_from_header(nc, am) is None


def test_o_line_multi_comment_matches_role_and_machine(tmp_path: Path):
    nc = _write_nc(
        tmp_path / "p.nc",
        "%\nO9001 (VF2S) (PROTO) (Pawel)\nG0\n%\n",
    )
    comments = extract_header_paren_comments(nc)
    assert comments == ["VF2S", "PROTO", "Pawel"]
    cmap = _colour_map(("PROTO", ROLE_PROTOTYPE), ("Pawel", ROLE_PERSONAL))
    am = AliasMap.load(ALIASES)
    roles = match_roles_from_header(nc, cmap)
    assert ROLE_PROTOTYPE in roles
    assert ROLE_PERSONAL in roles
    hit = match_machine_from_header(nc, am)
    assert hit is not None
    assert hit[0] == "haas-vf-2"


def test_glued_byte_start_role_machine(tmp_path: Path):
    glued = tmp_path / "dump.nc"
    part_a = "%\nO1111 (UMC750)\nG0\nM30\n%\n"
    part_b = "%\nO2222 (PROTO) (VF2S)\nG0\nM30\n%\n"
    glued.write_text(part_a + part_b, encoding="utf-8")
    byte_b = len(part_a.encode("utf-8"))
    cmap = _colour_map(("PROTO", ROLE_PROTOTYPE))
    am = AliasMap.load(ALIASES)
    assert match_roles_from_header(glued, cmap, byte_start=0) == {}
    assert match_roles_from_header(glued, cmap, byte_start=byte_b) == {
        ROLE_PROTOTYPE: "PROTO"
    }
    mach_a = match_machine_from_header(glued, am, byte_start=0)
    mach_b = match_machine_from_header(glued, am, byte_start=byte_b)
    assert mach_a is not None and "umc" in mach_a[0].casefold()
    assert mach_b is not None and mach_b[0] == "haas-vf-2"


def test_folder_personal_plus_header_proto_both_roles(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(
        bak / "15.09.2026" / "VF2S" / "Pawel" / "x.nc",
        "%\nO9101 (PROTO)\nG0\n%\n",
    )
    am = AliasMap.load(ALIASES)
    colours = _colour_map(("Pawel", ROLE_PERSONAL), ("PROTO", ROLE_PROTOTYPE))
    result = scan_backup_tree(
        bak, am, colour_map=colours, role_from_header=True, machine_from_header=True
    )
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    roles = roles_from_db(by[hit.resolve()].role)
    assert ROLE_PERSONAL in roles
    assert ROLE_PROTOTYPE in roles
    assert result.roles_from_header >= 1


def test_tree_replace_then_header_then_o9(tmp_path: Path):
    bak = tmp_path / "bak"
    folder = bak / "15.09.2026" / "VF2S" / "cell"
    hit = _write_nc(folder / "O9005.nc", "%\nO9005 (PROTO)\nG0\n%\n")
    am = AliasMap.load(ALIASES)
    colours = _colour_map(
        ("Pawel", ROLE_PERSONAL),
        ("PROTO", ROLE_PROTOTYPE),
    )
    tree = FolderTreeMap(
        rules=[FolderTreeRule(path=str(folder.resolve()), tags=[ROLE_FIXTURE])]
    )
    result = scan_backup_tree(
        bak,
        am,
        colour_map=colours,
        tree_map=tree,
        role_from_header=True,
        o9_system_programs_role=True,
    )
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    roles = roles_from_db(by[hit.resolve()].role)
    assert ROLE_FIXTURE in roles  # tree replace
    assert ROLE_PROTOTYPE in roles  # header accumulate
    assert ROLE_SYSTEM_PROGRAMS in roles  # O9 accumulate
    assert ROLE_PERSONAL not in roles  # name union replaced by tree


def test_mapped_machine_wins_over_header(tmp_path: Path):
    bak = tmp_path / "bak"
    # Path under VF2S folder → machine from alias; header says UMC750
    hit = _write_nc(
        bak / "15.09.2026" / "VF2S" / "loose" / "x.nc",
        "%\nO9201 (UMC750)\nG0\n%\n",
    )
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(bak, am, machine_from_header=True)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    inst = by[hit.resolve()]
    assert inst.machine_id != UNKNOWN_MACHINE_ID
    assert "umc" not in (inst.machine_id or "").casefold()
    assert result.machine_from_header == 0


def test_unknown_plus_header_assigns_machine(tmp_path: Path):
    bak = tmp_path / "bak"
    # Loose folder name that does not match any machine alias
    hit = _write_nc(
        bak / "15.09.2026" / "misc_cell" / "parts" / "x.nc",
        "%\nO9301 (VF2S)\nG0\n%\n",
    )
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(bak, am, machine_from_header=True)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    inst = by[hit.resolve()]
    assert inst.machine_id == "haas-vf-2"
    assert result.machine_from_header >= 1


def test_folder_map_beats_header_machine(tmp_path: Path):
    bak = tmp_path / "bak"
    cell = bak / "15.09.2026" / "odd_name"
    hit = _write_nc(cell / "x.nc", "%\nO9401 (UMC750)\nG0\n%\n")
    am = AliasMap.load(ALIASES)
    fmap = FolderMachineMap()
    fmap.set("odd_name", "haas-vf-2", "VF-2")
    result = scan_backup_tree(
        bak, am, folder_map=fmap, machine_from_header=True
    )
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert by[hit.resolve()].machine_id == "haas-vf-2"
    assert result.machine_from_header == 0


def test_toggles_off_no_change(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(
        bak / "15.09.2026" / "misc" / "y.nc",
        "%\nO9501 (PROTO) (VF2S)\nG0\n%\n",
    )
    am = AliasMap.load(ALIASES)
    colours = _colour_map(("PROTO", ROLE_PROTOTYPE))
    result = scan_backup_tree(
        bak,
        am,
        colour_map=colours,
        role_from_header=False,
        machine_from_header=False,
    )
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    inst = by[hit.resolve()]
    assert ROLE_PROTOTYPE not in roles_from_db(inst.role)
    assert inst.machine_id == UNKNOWN_MACHINE_ID
    assert result.roles_from_header == 0
    assert result.machine_from_header == 0


def test_reindex_backfills_header_role_and_machine(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(
        bak / "15.09.2026" / "loose" / "z.nc",
        "%\nO9601 (proto) (vf-2s)\nG0\n%\n",
    )
    am = AliasMap.load(ALIASES)
    empty = FolderColourAliasMap.empty()
    first = scan_backup_tree(
        bak, am, colour_map=empty, role_from_header=True, machine_from_header=False
    )
    by1 = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in first.instances
    }
    assert ROLE_PROTOTYPE not in roles_from_db(by1[hit.resolve()].role)

    colours = _colour_map(("PROTO", ROLE_PROTOTYPE))
    second = scan_backup_tree(
        bak,
        am,
        colour_map=colours,
        role_from_header=True,
        machine_from_header=True,
    )
    by2 = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in second.instances
    }
    assert ROLE_PROTOTYPE in roles_from_db(by2[hit.resolve()].role)
    assert by2[hit.resolve()].machine_id == "haas-vf-2"
    assert second.roles_from_header >= 1
    assert second.machine_from_header >= 1


def test_tip_header_reason_when_file_present(tmp_path: Path):
    bak = tmp_path / "bak"
    nc = _write_nc(
        bak / "loose" / "a.nc",
        "%\nO1 (PROTO)\nG0\n%\n",
    )
    cmap = _colour_map(("PROTO", ROLE_PROTOTYPE))
    reasons = explain_row_roles(
        source_path="loose/a.nc",
        scan_root=str(bak),
        program_number="1",
        role_csv=ROLE_PROTOTYPE,
        colour_map=cmap,
        tree_map=FolderTreeMap(),
        o9_enabled=True,
        role_from_header=True,
    )
    assert len(reasons) == 1
    assert reasons[0].reason_kind == REASON_HEADER
    assert reasons[0].detail == "PROTO"
    assert nc.is_file()
    from gcode_index.role_explain import format_reason_phrase

    en = format_reason_phrase(reasons[0], "en")
    pl = format_reason_phrase(reasons[0], "pl")
    assert "O-number line" in en
    assert "linia O" in pl


def test_tip_ignores_alias_not_on_o_line(tmp_path: Path):
    bak = tmp_path / "bak"
    _write_nc(
        bak / "loose" / "a.nc",
        "%\nO1 (part)\n(LP1)\nG0\n(PROTO)\nM30\n%\n",
    )
    reasons = explain_row_roles(
        source_path="loose/a.nc",
        scan_root=str(bak),
        program_number="1",
        role_csv=ROLE_PROTOTYPE,
        colour_map=_colour_map(("PROTO", ROLE_PROTOTYPE)),
        tree_map=FolderTreeMap(),
        role_from_header=True,
    )
    assert reasons[0].reason_kind != REASON_HEADER


def test_tip_header_unavailable_without_source(tmp_path: Path):
    reasons = explain_row_roles(
        source_path="missing/a.nc",
        scan_root=str(tmp_path / "nope"),
        program_number="1",
        role_csv=ROLE_PROTOTYPE,
        colour_map=_colour_map(("PROTO", ROLE_PROTOTYPE)),
        tree_map=FolderTreeMap(),
        role_from_header=True,
    )
    assert reasons[0].reason_kind != REASON_HEADER
    assert reasons[0].reason_kind != REASON_PATH


def test_tree_path_still_preferred_over_header_in_tip(tmp_path: Path):
    folder = tmp_path / "cell"
    folder.mkdir()
    _write_nc(folder / "a.nc", "%\nO1 (PROTO)\nG0\n%\n")
    tm = FolderTreeMap(
        rules=[FolderTreeRule(path=str(folder), tags=[ROLE_PROTOTYPE])]
    )
    reasons = explain_row_roles(
        source_path="cell/a.nc",
        scan_root=str(tmp_path),
        program_number="1",
        role_csv=ROLE_PROTOTYPE,
        colour_map=_colour_map(("PROTO", ROLE_PROTOTYPE)),
        tree_map=tm,
        role_from_header=True,
    )
    assert reasons[0].reason_kind == REASON_PATH
