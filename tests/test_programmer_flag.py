"""Programmer flag: next-line (LLdigit), case-insensitive; non-matches ignored."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.db import open_db, query_instances, write_scan_result
from gcode_index.locators import parse_programmer_flag
from gcode_index.locators.haas_pgm import locate_haas_pgm
from gcode_index.locators.whole_file_nc import locate_whole_file_nc
from gcode_index.scanner import scan_backup_tree

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"


def test_parse_programmer_flag_rules():
    assert parse_programmer_flag("(PG1)") == "PG1"
    assert parse_programmer_flag("(lp2)") == "LP2"
    assert parse_programmer_flag("  (Pg3)  ") == "PG3"
    # Non-matches → ignored
    assert parse_programmer_flag("(PART123)") is None
    assert parse_programmer_flag("(PG)") is None
    assert parse_programmer_flag("(PG10)") is None
    assert parse_programmer_flag("(PG0)") is None
    assert parse_programmer_flag("(P1)") is None
    assert parse_programmer_flag("(PG1 more)") is None
    assert parse_programmer_flag("") is None
    assert parse_programmer_flag("O01234") is None


def test_haas_pgm_reads_next_line_programmer(tmp_path: Path):
    pgm = tmp_path / "PROG.PGM"
    pgm.write_bytes(
        b"%\r\n"
        b"O01234 (PART-A)\r\n"
        b"(pg1)\r\n"
        b"G0 X0\r\n"
        b"O05678 (PART-B)\r\n"
        b"(NOT A FLAG)\r\n"
        b"G1 Y1\r\n"
        b"%\r\n"
    )
    insts = locate_haas_pgm(
        pgm,
        source_path="PROG.PGM",
        machine_id="haas-vf-2",
        machine_label="HAAS VF-2",
    )
    by_prog = {i.program_number: i for i in insts}
    assert by_prog["01234"].programmer == "PG1"
    assert by_prog["05678"].programmer is None
    assert by_prog["05678"].part_number == "PART-B"


def test_whole_file_nc_programmer(tmp_path: Path):
    nc = tmp_path / "9278.nc"
    nc.write_bytes(b"%\nO09278 (UMC PART)\n(LP2)\nG0 X0\n%\n")
    inst = locate_whole_file_nc(
        nc,
        source_path="9278.nc",
        source_type="haas_ngc_nc",
        machine_id="haas-umc750",
    )
    assert inst.program_number == "09278"
    assert inst.programmer == "LP2"

    nc2 = tmp_path / "noflag.nc"
    nc2.write_bytes(b"O01\n(PART ONLY)\nG0\n")
    inst2 = locate_whole_file_nc(
        nc2,
        source_path="noflag.nc",
        source_type="loose_nc",
        machine_id="unknown",
    )
    assert inst2.programmer is None


def test_scan_and_query_programmer(tmp_path: Path):
    bak = tmp_path / "bak"
    dest = bak / "15.09.2026" / "VF2S"
    dest.mkdir(parents=True)
    (dest / "DUMP.PGM").write_bytes(
        b"%\r\nO01000 (WIDGET)\r\n(ab9)\r\nG0\r\n%\r\n"
    )
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(bak, am)
    assert any(i.programmer == "AB9" for i in result.instances)

    db = tmp_path / "idx.sqlite"
    conn = open_db(db)
    write_scan_result(conn, backup_root=str(bak), aliases_path=str(ALIASES), result=result)
    conn.commit()
    rows = query_instances(conn, programmer="ab9")
    assert rows
    assert all(r["programmer"] == "AB9" for r in rows)
    conn.close()
