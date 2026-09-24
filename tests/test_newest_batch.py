"""Tests for newest-only collapse (#7) and batch extract filenames (#6)."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.db import (
    collapse_newest_per_program_machine,
    open_db,
    query_instances,
    write_scan_result,
)
from gcode_index.extract import batch_extract_filename, default_extract_filename
from gcode_index.scanner import scan_backup_tree

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"
FIX = Path(__file__).parent / "fixtures" / "synthetic"


def test_collapse_newest_per_program_machine():
    rows = [
        {"program_number": "1234", "machine_id": "haas-vf-2", "backup_date": "2026-09-01T00:00:00+00:00"},
        {"program_number": "1234", "machine_id": "haas-vf-2", "backup_date": "2026-09-15T00:00:00+00:00"},
        {"program_number": "1234", "machine_id": "haas-umc750", "backup_date": "2026-09-10T00:00:00+00:00"},
        {"program_number": "O1234", "machine_id": "haas-vf-2", "backup_date": "2026-08-01T00:00:00+00:00"},
    ]
    # O1234 and 1234 are different program_number strings (no normalize yet — #20)
    out = collapse_newest_per_program_machine(rows)
    assert len(out) == 3
    vf2 = [r for r in out if r["machine_id"] == "haas-vf-2" and r["program_number"] == "1234"]
    assert len(vf2) == 1
    assert vf2[0]["backup_date"].startswith("2026-09-15")


def test_query_newest_only(tmp_path: Path):
    bak = tmp_path / "bak"
    for date in ("01.09.2026", "15.09.2026"):
        dest = bak / date / "VF2S"
        dest.mkdir(parents=True)
        (dest / "DUMP.PGM").write_bytes((FIX / "tiny.pgm").read_bytes())
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(bak, am)
    # Same programs appear under both dates
    db = tmp_path / "gcode_index.sqlite"
    conn = open_db(db)
    write_scan_result(conn, backup_root=str(bak), aliases_path=str(ALIASES), result=result)
    conn.commit()

    all_rows = query_instances(conn, limit=500)
    newest = query_instances(conn, newest_only=True, limit=500)
    assert len(newest) < len(all_rows) or len(all_rows) == len(newest)
    # Group check: at most one per program+machine
    seen: set[tuple[str, str]] = set()
    for r in newest:
        key = (str(r["program_number"]).casefold(), str(r["machine_id"]).casefold())
        assert key not in seen
        seen.add(key)
    conn.close()


def test_batch_extract_filename_unique():
    row = {
        "program_number": "01234",
        "machine_id": "haas-vf-2",
        "backup_date": "2026-09-15T12:00:00+00:00",
        "source_type": "haas_pgm_glued",
    }
    used: set[str] = set()
    a = batch_extract_filename(row, used=used)
    b = batch_extract_filename(row, used=used)
    assert a != b
    assert a.endswith(".nc")
    assert "01234" in a
    assert "haas-vf-2" in a
    assert default_extract_filename(row) == "01234.nc"
