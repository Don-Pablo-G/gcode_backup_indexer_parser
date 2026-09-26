"""Odbiorca from G-code header — normalize, precedence, reindex backfill."""

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
    # Too-short needle skipped
    short = _odb_map(("AB", "ab"))
    assert len(normalize_folder_name("AB")) < MIN_HEADER_ODBIORCA_NEEDLE
    assert match_odbiorca_in_comments(["AB"], short) is None


def test_extract_skips_body_comments(tmp_path: Path):
    nc = _write_nc(
        tmp_path / "p.nc",
        "%\n"
        "O1234 (Acme_Sp)\n"
        "(LP1)\n"
        + "\n".join(f"G1 X{i}" for i in range(50))
        + "\n(OtherClient)\nM30\n%\n",
    )
    comments = extract_header_paren_comments(nc, max_lines=40)
    joined = " ".join(comments)
    assert "Acme_Sp" in joined
    assert "OtherClient" not in joined  # below header window


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
