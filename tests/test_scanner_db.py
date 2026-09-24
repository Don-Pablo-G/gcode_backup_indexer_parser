from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.db import (
    format_location,
    list_instances,
    open_db,
    search_instances,
    write_scan_result,
)
from gcode_index.excel_export import export_excel
from gcode_index.scanner import scan_backup_tree

FIX = Path(__file__).parent / "fixtures" / "synthetic"
ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"


def _build_mini_tree(tmp_path: Path) -> Path:
    root = tmp_path / "backup"
    # date/machine trees
    (root / "15.09.2026" / "SL-20").mkdir(parents=True)
    (root / "15.09.2026" / "doosan d").mkdir(parents=True)
    (root / "15.09.2026" / "doosan m").mkdir(parents=True)
    (root / "15.09.2026" / "SBL").mkdir(parents=True)
    (root / "15.09.2026" / "ST20Y" / "HaasBackup(09-15-2026)" / "Memory" / "sub").mkdir(
        parents=True
    )
    (root / "15.09.2026" / "UnknownBox").mkdir(parents=True)

    (root / "15.09.2026" / "SL-20" / "SL20.PGM").write_bytes(
        (FIX / "tiny.pgm").read_bytes()
    )
    (root / "15.09.2026" / "doosan d" / "ALL-FLDR.TXT").write_bytes(
        (FIX / "ALL-FLDR.TXT").read_bytes()
    )
    (root / "15.09.2026" / "doosan m" / "ALL-PROG.TXT").write_bytes(
        (FIX / "ALL-PROG.TXT").read_bytes()
    )
    nc = (FIX / "O1234.nc").read_bytes()
    (root / "15.09.2026" / "SBL" / "JOB99.nc").write_bytes(nc)
    (
        root / "15.09.2026" / "ST20Y" / "HaasBackup(09-15-2026)" / "Memory" / "sub" / "O5555.nc"
    ).write_bytes(nc)
    # .nc under unknown machine folder — must still index as MACHINE UNKNOWN
    (root / "15.09.2026" / "UnknownBox" / "orphan.nc").write_bytes(nc)
    # .nc under PGM machine (not Memory) — fuzzy-match SL-20, type loose_nc
    (root / "15.09.2026" / "SL-20" / "extra.nc").write_bytes(nc)
    (root / "loose1234.nc").write_bytes(nc)
    return root


def test_scanner_routes_and_sqlite(tmp_path: Path):
    root = _build_mini_tree(tmp_path)
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(root, am)

    types = {i.source_type for i in result.instances}
    assert "haas_pgm_glued" in types
    assert "fanuc_all_fldr" in types
    assert "fanuc_all_prog" in types
    assert "manual_nc_folder" in types
    assert "haas_ngc_nc" in types
    assert "loose_nc" in types

    assert any(u.machine_folder_raw == "UnknownBox" for u in result.unknowns)

    orphan = next(i for i in result.instances if i.source_path.endswith("orphan.nc"))
    assert orphan.machine_id == "unknown"
    assert orphan.machine_label == "MACHINE UNKNOWN"
    assert orphan.source_type == "loose_nc"

    extra = next(i for i in result.instances if i.source_path.endswith("extra.nc"))
    assert extra.machine_id == "haas-sl-20"
    assert extra.source_type == "loose_nc"

    ngc = next(i for i in result.instances if i.source_type == "haas_ngc_nc")
    assert ngc.machine_id == "haas-st-20y"
    assert ngc.folder_path == "sub"

    db_path = tmp_path / "gcode_index.sqlite"
    conn = open_db(db_path)
    run_id = write_scan_result(
        conn, backup_root=str(root), aliases_path=str(ALIASES), result=result
    )
    assert run_id
    n = conn.execute("SELECT COUNT(*) FROM program_instances").fetchone()[0]
    assert n == len(result.instances)
    # pgm(2) + fldr(3) + prog(4) + manual(1) + ngc(1) + loose root(1) + orphan(1) + extra(1)
    assert n >= 2 + 3 + 4 + 1 + 1 + 1 + 1 + 1

    rows = search_instances(conn, "0001")
    assert rows
    # Path search finds loose / tree .nc by digits in source_path
    path_hits = search_instances(conn, "5555")
    assert any("O5555.nc" in (r["source_path"] or "") for r in path_hits)

    browsed = list_instances(conn, limit=50)
    assert len(browsed) >= 1
    looseish = [r for r in browsed if r["source_type"] in ("loose_nc", "haas_ngc_nc", "manual_nc_folder")]
    assert looseish
    assert format_location(looseish[0]) == "whole file"
    glued = next(r for r in browsed if r["source_type"] == "haas_pgm_glued")
    assert format_location(glued).startswith("L")

    conn.close()

    xlsx = tmp_path / "out.xlsx"
    export_excel(xlsx, result.instances)
    assert xlsx.is_file() and xlsx.stat().st_size > 0


def test_scan_progress_callback(tmp_path: Path):
    root = _build_mini_tree(tmp_path)
    am = AliasMap.load(ALIASES)
    events: list[dict] = []
    result = scan_backup_tree(root, am, progress=events.append)
    assert result.instances
    phases = [e["phase"] for e in events]
    assert "counting" in phases
    assert "scanning" in phases
    assert phases[-1] == "done"
    scanned = [e for e in events if e["phase"] == "scanning" and e["current"] > 0]
    assert scanned
    assert scanned[-1]["total"] >= scanned[-1]["current"]
    assert any(e.get("eta_s") is not None or e["current"] >= e["total"] for e in scanned)


def test_umc750_memory_tree_indexes(tmp_path: Path):
    """Haas NGC UMC750 Memory/*.nc must land on haas-umc750 (not MACHINE UNKNOWN)."""
    sample = (
        Path("/cursor/stores/bc-8553f678-6c90-4da8-8c05-737a2b3271c2")
        / "internal"
        / "samples"
        / "haas-ngc"
        / "P-00253232_VA.nc"
    )
    if not sample.is_file():
        # Fallback tiny synthetic O-header
        body = b"%\r\nO03232 (P-00253232 VA OP1/OP2)\r\nM30\r\n%\r\n"
    else:
        body = sample.read_bytes()

    root = tmp_path / "backup"
    for folder in ("UMC750", "UMC", "UMC750SS"):
        dest = root / "15.09.2026" / folder / "HaasBackup(09-15-2026)" / "Memory" / "sub"
        dest.mkdir(parents=True)
        (dest / f"{folder}.nc").write_bytes(body)

    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(root, am)
    umc = [i for i in result.instances if i.machine_id == "haas-umc750"]
    assert len(umc) == 3
    assert all(i.source_type == "haas_ngc_nc" for i in umc)
    assert all(i.program_number == "03232" for i in umc)
    assert all(i.machine_label == "HAAS UMC750" for i in umc)


def test_vf2s_folder_indexes_pgm(tmp_path: Path):
    """Folder VF2S (sample dump basename) must map to haas-vf-2 and index .pgm."""
    root = tmp_path / "backup"
    dest = root / "15.09.2026" / "VF2S"
    dest.mkdir(parents=True)
    (dest / "VF2S.PGM").write_bytes((FIX / "tiny.pgm").read_bytes())
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(root, am)
    vf = [i for i in result.instances if i.machine_id == "haas-vf-2"]
    assert vf
    assert all(i.source_type == "haas_pgm_glued" for i in vf)


def test_unmapped_folder_still_indexes_pgm(tmp_path: Path):
    """Odd folder names must not drop .pgm — index as MACHINE UNKNOWN."""
    root = tmp_path / "backup"
    dest = root / "15.09.2026" / "MysteryMill"
    dest.mkdir(parents=True)
    (dest / "DUMP.PGM").write_bytes((FIX / "tiny.pgm").read_bytes())
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(root, am)
    assert any(u.machine_folder_raw == "MysteryMill" for u in result.unknowns)
    mystery = [i for i in result.instances if "DUMP.PGM" in i.source_path]
    assert mystery
    assert all(i.machine_id == "unknown" for i in mystery)


def test_search_allows_short_and_letter_queries(tmp_path: Path):
    conn = open_db(tmp_path / "empty.sqlite")
    try:
        # Empty DB + free-text / short queries just return [] (no digit gate)
        assert search_instances(conn, "12") == []
        assert search_instances(conn, "VA") == []
    finally:
        conn.close()
