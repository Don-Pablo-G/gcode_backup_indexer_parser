from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.db import open_db, search_instances, write_scan_result
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

    db_path = tmp_path / "gcode_index.sqlite"
    conn = open_db(db_path)
    run_id = write_scan_result(
        conn, backup_root=str(root), aliases_path=str(ALIASES), result=result
    )
    assert run_id
    n = conn.execute("SELECT COUNT(*) FROM program_instances").fetchone()[0]
    assert n == len(result.instances)
    assert n >= 2 + 3 + 4 + 1 + 1 + 1  # pgm + fldr + prog + manual + ngc + loose

    rows = search_instances(conn, "0001")
    assert rows
    conn.close()

    xlsx = tmp_path / "out.xlsx"
    export_excel(xlsx, result.instances)
    assert xlsx.is_file() and xlsx.stat().st_size > 0


def test_search_rejects_short_digits(tmp_path: Path):
    conn = open_db(tmp_path / "empty.sqlite")
    try:
        import pytest

        with pytest.raises(ValueError):
            search_instances(conn, "12")
    finally:
        conn.close()
