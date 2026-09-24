"""Tests for scan report (#14) and duplicate / near-duplicate finder (#13)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.db import open_db, write_scan_result
from gcode_index.models import FileSeen, ProgramInstance, ScanResult, UnknownFolder
from gcode_index.scan_report import (
    find_duplicate_groups,
    find_exact_duplicate_groups,
    find_near_duplicate_groups,
    format_scan_report,
    load_scan_report,
    scan_report_from_result,
)
from gcode_index.scanner import scan_backup_tree

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"
FIX = Path(__file__).parent / "fixtures" / "synthetic"


def _inst(
    *,
    program: str,
    machine: str,
    sha: str,
    size: int,
    path: str,
    label: str | None = None,
    source_type: str = "loose_nc",
    date: str = "2026-09-15T00:00:00+00:00",
) -> ProgramInstance:
    return ProgramInstance(
        program_number=program,
        part_number=None,
        machine_id=machine,
        machine_label=label or machine,
        backup_date=datetime.fromisoformat(date),
        date_source="mtime",
        source_path=path,
        source_type=source_type,
        source_size=size,
        content_sha256=sha,
        control_family="haas",
    )


def test_scan_report_from_result_counts():
    result = ScanResult(
        instances=[
            _inst(program="1", machine="haas-vf-2", sha="a" * 64, size=100, path="a.nc"),
            _inst(
                program="2",
                machine="unknown",
                label="MACHINE UNKNOWN",
                sha="b" * 64,
                size=50,
                path="orphan.nc",
            ),
            _inst(
                program="3",
                machine="haas-st-20y",
                sha="c" * 64,
                size=80,
                path="x.nc.copy",
                source_type="haas_ngc_nc_copy",
            ),
        ],
        files_seen=[
            FileSeen("a.nc", "loose_nc", 100, None, "indexed"),
            FileSeen(
                "15.09.2026/VF2S",
                None,
                None,
                None,
                "skipped",
                note="mapped machine (haas-vf-2) but no glued dump found",
            ),
        ],
        unknowns=[
            UnknownFolder("15.09.2026", "UnknownBox", "unknownbox"),
        ],
    )
    report = scan_report_from_result(result, run_id="abc-123")
    assert report.instance_count == 3
    assert report.copy_count == 1
    assert report.unknown_program_count == 1
    assert report.unknown_folder_count == 1
    assert len(report.skipped) == 1
    assert any("haas-vf-2" in name for name, _n in report.per_machine)
    text = format_scan_report(report)
    assert "MACHINE UNKNOWN" in text
    assert "Skipped dumps" in text
    assert "*.nc.copy" in text


def test_load_scan_report_from_db(tmp_path: Path):
    bak = tmp_path / "bak"
    (bak / "15.09.2026" / "UnknownBox").mkdir(parents=True)
    (bak / "15.09.2026" / "UnknownBox" / "orphan.nc").write_bytes(
        (FIX / "O1234.nc").read_bytes()
    )
    (bak / "15.09.2026" / "VF2S").mkdir(parents=True)
    (bak / "15.09.2026" / "VF2S" / "DUMP.PGM").write_bytes((FIX / "tiny.pgm").read_bytes())
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(bak, am)
    db = tmp_path / "gcode_index.sqlite"
    conn = open_db(db)
    run_id = write_scan_result(
        conn, backup_root=str(bak), aliases_path=str(ALIASES), result=result
    )
    report = load_scan_report(conn, run_id=run_id)
    assert report is not None
    assert report.instance_count == len(result.instances)
    assert report.unknown_folder_count >= 1
    assert report.unknown_program_count >= 1
    text = format_scan_report(report)
    assert "Per machine" in text
    conn.close()


def test_exact_and_near_duplicates(tmp_path: Path):
    db = tmp_path / "gcode_index.sqlite"
    conn = open_db(db)
    # Fabricate a scan result with known SHA / size patterns
    same = "ab" * 32
    result = ScanResult(
        instances=[
            _inst(
                program="1234",
                machine="haas-vf-2",
                sha=same,
                size=1000,
                path="d1/vf2/a.nc",
                date="2026-09-01T00:00:00+00:00",
            ),
            _inst(
                program="1234",
                machine="haas-umc750",
                sha=same,
                size=1000,
                path="d1/umc/a.nc",
                date="2026-09-10T00:00:00+00:00",
            ),
            # Near: same O#, different SHA, size within 5%
            _inst(
                program="5555",
                machine="haas-vf-2",
                sha="11" * 32,
                size=2000,
                path="d2/vf2/b.nc",
            ),
            _inst(
                program="5555",
                machine="haas-sl-20",
                sha="22" * 32,
                size=2050,
                path="d2/sl20/b.nc",
            ),
            # Unique — should not appear
            _inst(
                program="9999",
                machine="haas-vf-2",
                sha="33" * 32,
                size=500,
                path="solo.nc",
            ),
        ]
    )
    write_scan_result(
        conn, backup_root=str(tmp_path), aliases_path=None, result=result
    )

    exact = find_exact_duplicate_groups(conn)
    assert len(exact) == 1
    assert exact[0].kind == "exact"
    assert len(exact[0].members) == 2
    assert "Exact SHA" in exact[0].label

    near = find_near_duplicate_groups(conn)
    assert len(near) == 1
    assert near[0].kind == "near"
    assert len(near[0].members) == 2
    assert "5555" in near[0].label

    all_groups = find_duplicate_groups(conn)
    assert len(all_groups) == 2
    assert all_groups[0].kind == "exact"
    assert all_groups[1].kind == "near"
    conn.close()
