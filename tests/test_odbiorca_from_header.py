"""Odbiorca from G-code O-number line — normalize, precedence, reindex backfill."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap, normalize_folder_name
from gcode_index.folder_tree_map import FolderTreeMap, FolderTreeRule
from gcode_index.odbiorca_aliases import (
    MIN_HEADER_ODBIORCA_NEEDLE,
    OdbiorcaAliasMap,
    OdbiorcaRule,
    extract_header_paren_comments,
    match_odbiorca_from_header,
    match_odbiorca_in_comments,
)
from gcode_index.models import PROVENANCE_BACKUP
from gcode_index.scanner import scan_backup_tree

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"


def _write_nc(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _odb_map(*pairs: tuple[str, str]) -> OdbiorcaAliasMap:
    rules = [
        OdbiorcaRule(alias=alias, odbiorca_id=oid, exact=True) for alias, oid in pairs
    ]
    ids = {oid for _, oid in pairs}
    return OdbiorcaAliasMap(rules, known_ids=ids)


def test_normalize_equates_space_underscore_hyphen_case():
    assert normalize_folder_name("Acme Sp") == normalize_folder_name("Acme_Sp")
    assert normalize_folder_name("Acme Sp") == normalize_folder_name("acme-sp")
    assert normalize_folder_name("ACME SP") == normalize_folder_name("Acme_Sp")


def test_match_comments_longest_and_exact():
    odb = _odb_map(("Acme", "acme"), ("Acme Sp", "acme_sp"))
    # Longer alias wins over shorter substring
    assert match_odbiorca_in_comments(["Acme Sp order"], odb) == "acme_sp"
    assert match_odbiorca_in_comments(["(Acme_Sp)"], odb) == "acme_sp"
    assert match_odbiorca_in_comments(["ACME SP"], odb) == "acme_sp"
    assert match_odbiorca_in_comments(["Acme"], odb) == "acme"
    # Prefix ≥3 (machine-style): alias is prefix of comment body
    assert match_odbiorca_in_comments(["AcmeExtra"], odb) == "acme"
    # Too-short needle skipped
    short = _odb_map(("AB", "ab"))
    assert len(normalize_folder_name("AB")) < MIN_HEADER_ODBIORCA_NEEDLE
    assert match_odbiorca_in_comments(["AB"], short) is None
    # 3-char mid-string no longer substring-hits (needs ≥4); prefix only
    mid = _odb_map(("Acm", "acm"))
    assert match_odbiorca_in_comments(["XAcmY"], mid) is None
    assert match_odbiorca_in_comments(["AcmExtra"], mid) == "acm"


def test_extract_only_o_line_parens(tmp_path: Path):
    nc = _write_nc(
        tmp_path / "p.nc",
        "%\n"
        "O1234 (Acme_Sp) (extra)\n"
        "(LP1)\n"
        "(OtherClient)\n"
        + "\n".join(f"G1 X{i}" for i in range(50))
        + "\n(OtherClient)\nM30\n%\n",
    )
    comments = extract_header_paren_comments(nc, max_lines=40)
    assert comments == ["Acme_Sp", "extra"]
    assert "LP1" not in comments
    assert "OtherClient" not in comments


def test_alias_on_line_after_o_does_not_match(tmp_path: Path):
    """False-positive regression: alias deeper than the O-line must not hit."""
    bak = tmp_path / "bak"
    hit = _write_nc(
        bak / "15.09.2026" / "VF2S" / "loose" / "x.nc",
        "%\n"
        "O9101 (part)\n"
        "(LP1)\n"
        "G0\n"
        "G1 X0\n"
        "(Acme_Sp)\n"  # line 5 — old 40-line window would have matched
        "M30\n%\n",
    )
    am = AliasMap.load(ALIASES)
    odb = _odb_map(("Acme Sp", "acme"))
    result = scan_backup_tree(bak, am, odbiorca_map=odb, odbiorca_from_header=True)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert by[hit.resolve()].odbiorca_id is None
    assert result.odbiorca_from_header == 0
    assert match_odbiorca_from_header(hit, odb) is None


def test_header_fills_when_folder_empty(tmp_path: Path):
    bak = tmp_path / "bak"
    # Loose tree — no odbiorca-named folder
    hit = _write_nc(
        bak / "15.09.2026" / "VF2S" / "loose" / "x.nc",
        "%\nO9101 (Acme_Sp)\nG0\n%\n",
    )
    am = AliasMap.load(ALIASES)
    odb = _odb_map(("Acme Sp", "acme"))
    result = scan_backup_tree(bak, am, odbiorca_map=odb, odbiorca_from_header=True)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert by[hit.resolve()].odbiorca_id == "acme"
    assert result.odbiorca_from_header >= 1


def test_folder_wins_over_header(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(
        bak / "15.09.2026" / "VF2S" / "OtherCust" / "x.nc",
        "%\nO9201 (Acme_Sp)\nG0\n%\n",
    )
    am = AliasMap.load(ALIASES)
    odb = _odb_map(("Acme Sp", "acme"), ("OtherCust", "other"))
    result = scan_backup_tree(bak, am, odbiorca_map=odb, odbiorca_from_header=True)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert by[hit.resolve()].odbiorca_id == "other"
    assert result.odbiorca_from_header == 0


def test_path_override_wins_over_header_and_folder(tmp_path: Path):
    bak = tmp_path / "bak"
    folder = bak / "15.09.2026" / "VF2S" / "Acme"
    hit = _write_nc(folder / "x.nc", "%\nO9301 (Acme_Sp)\nG0\n%\n")
    am = AliasMap.load(ALIASES)
    odb = _odb_map(("Acme", "acme"), ("Acme Sp", "acme"))
    tree = FolderTreeMap(
        rules=[
            FolderTreeRule(
                path=str(folder.resolve()),
                odbiorca_id="path_win",
            )
        ]
    )
    result = scan_backup_tree(
        bak, am, odbiorca_map=odb, tree_map=tree, odbiorca_from_header=True
    )
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert by[hit.resolve()].odbiorca_id == "path_win"
    assert result.odbiorca_from_path >= 1
    assert result.odbiorca_from_header == 0


def test_toggle_off_skips_header(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(
        bak / "15.09.2026" / "VF2S" / "loose" / "y.nc",
        "%\nO9401 (Acme_Sp)\nG0\n%\n",
    )
    am = AliasMap.load(ALIASES)
    odb = _odb_map(("Acme Sp", "acme"))
    result = scan_backup_tree(bak, am, odbiorca_map=odb, odbiorca_from_header=False)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert by[hit.resolve()].odbiorca_id is None
    assert result.odbiorca_from_header == 0


def test_reindex_backfills_header_odbiorca(tmp_path: Path):
    """Second scan with aliases present fills rows that were empty before."""
    bak = tmp_path / "bak"
    hit = _write_nc(
        bak / "15.09.2026" / "VF2S" / "misc" / "z.nc",
        "%\nO9501 (acme-sp)\nG0\n%\n",
    )
    am = AliasMap.load(ALIASES)
    empty = OdbiorcaAliasMap.empty()
    first = scan_backup_tree(bak, am, odbiorca_map=empty, odbiorca_from_header=True)
    by1 = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in first.instances
    }
    assert by1[hit.resolve()].odbiorca_id is None

    odb = _odb_map(("Acme Sp", "acme"))
    second = scan_backup_tree(bak, am, odbiorca_map=odb, odbiorca_from_header=True)
    by2 = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in second.instances
    }
    assert by2[hit.resolve()].odbiorca_id == "acme"
    assert second.odbiorca_from_header >= 1
    assert by2[hit.resolve()].provenance == PROVENANCE_BACKUP


def test_match_odbiorca_from_header_helper(tmp_path: Path):
    nc = _write_nc(tmp_path / "a.nc", "%\nO1 (Acme_Sp)\nG0\n%\n")
    odb = _odb_map(("Acme Sp", "acme"))
    assert match_odbiorca_from_header(nc, odb) == "acme"


def test_glued_byte_start_isolates_o_line(tmp_path: Path):
    """Second glued program: seek byte_start → only that instance's O-line."""
    glued = tmp_path / "dump.nc"
    part_a = "%\nO1111 (OtherCust)\nG0\nM30\n%\n"
    part_b = "%\nO2222 (Acme_Sp)\nG0\nM30\n%\n"
    glued.write_text(part_a + part_b, encoding="utf-8")
    byte_b = len(part_a.encode("utf-8"))
    odb = _odb_map(("Acme Sp", "acme"), ("OtherCust", "other"))
    assert match_odbiorca_from_header(glued, odb, byte_start=0) == "other"
    assert match_odbiorca_from_header(glued, odb, byte_start=byte_b) == "acme"
    assert extract_header_paren_comments(glued, byte_start=byte_b) == ["Acme_Sp"]
