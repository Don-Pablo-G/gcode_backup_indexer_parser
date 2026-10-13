"""Work Date from DD.MM.YYYY first path segment under scan root."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.db import format_display_date, open_db, write_scan_result
from gcode_index.folder_date import (
    DATE_SOURCE_FOLDER,
    DATE_SOURCE_UNKNOWN,
    apply_work_dates,
    first_segment_under_root,
    parse_folder_date_name,
    resolve_work_date,
)
from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA, ProgramInstance
from gcode_index.scanner import scan_backup_tree, scan_with_extra_roots

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"
FIX = Path(__file__).parent / "fixtures" / "synthetic"
BIRTH = datetime(2020, 1, 2, 12, 0, tzinfo=timezone.utc)


def test_parse_folder_date_name_valid():
    dt = parse_folder_date_name("15.09.2026")
    assert dt == datetime(2026, 9, 15, tzinfo=timezone.utc)


def test_parse_folder_date_name_rejects_garbage():
    assert parse_folder_date_name("VF2S") is None
    assert parse_folder_date_name("32.13.2026") is None
    assert parse_folder_date_name("") is None
    assert parse_folder_date_name(None) is None


def test_first_segment_only():
    assert first_segment_under_root("15.09.2026/VF2S/Memory/x.nc") == "15.09.2026"
    assert first_segment_under_root("VF2S/jobs/x.nc") == "VF2S"
    assert first_segment_under_root("x.nc") == "x.nc"
    assert first_segment_under_root("") is None


def test_resolve_folder_wins():
    bd, src, seg = resolve_work_date(
        source_path="15.09.2026/VF2S/x.nc",
        date_folder_raw="15.09.2026",
        file_ctime=BIRTH,
        birth_source="birth",
        missing_folder_policy="unknown",
    )
    assert bd == datetime(2026, 9, 15, tzinfo=timezone.utc)
    assert src == DATE_SOURCE_FOLDER
    assert seg == "15.09.2026"


def test_resolve_main_backup_unknown():
    bd, src, seg = resolve_work_date(
        source_path="VF2S/x.nc",
        date_folder_raw=None,
        file_ctime=BIRTH,
        birth_source="birth",
        missing_folder_policy="unknown",
    )
    assert bd is None
    assert src == DATE_SOURCE_UNKNOWN
    assert seg == "VF2S"


def test_resolve_green_birth_fallback():
    bd, src, _seg = resolve_work_date(
        source_path="CatchAll/x.nc",
        date_folder_raw=None,
        file_ctime=BIRTH,
        birth_source="birth",
        missing_folder_policy="birth",
    )
    assert bd == BIRTH
    assert src == "birth"


def test_resolve_ignores_deeper_date_segment():
    """Only the first segment under the root counts."""
    bd, src, seg = resolve_work_date(
        source_path="VF2S/15.09.2026/x.nc",
        date_folder_raw=None,
        file_ctime=BIRTH,
        birth_source="birth",
        missing_folder_policy="unknown",
    )
    assert bd is None
    assert src == DATE_SOURCE_UNKNOWN
    assert seg == "VF2S"


def test_apply_keeps_file_ctime_audit():
    inst = ProgramInstance(
        program_number="O1",
        part_number=None,
        machine_id="haas-vf-2",
        backup_date=BIRTH,
        date_source="birth",
        source_path="15.09.2026/VF2S/a.nc",
        source_type="loose_nc",
        date_folder_raw="15.09.2026",
        file_ctime=BIRTH,
    )
    apply_work_dates([inst], missing_folder_policy="unknown")
    assert inst.backup_date == datetime(2026, 9, 15, tzinfo=timezone.utc)
    assert inst.date_source == DATE_SOURCE_FOLDER
    assert inst.file_ctime == BIRTH


def test_format_display_date_unknown():
    assert format_display_date("", unknown_label="unknown") == "unknown"
    assert format_display_date(None, unknown_label="nieznana") == "nieznana"
    assert format_display_date("2026-09-15T00:00:00+00:00") == "15.09.2026"


def _nc_body() -> bytes:
    return b"O01234 (PART)\nG0 X0\nM30\n%"


def test_scan_main_backup_folder_date(tmp_path: Path):
    bak = tmp_path / "bak"
    dest = bak / "15.09.2026" / "VF2S"
    dest.mkdir(parents=True)
    (dest / "job.nc").write_bytes(_nc_body())
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(bak, am)
    assert result.instances
    for inst in result.instances:
        assert inst.backup_date == datetime(2026, 9, 15, tzinfo=timezone.utc)
        assert inst.date_source == DATE_SOURCE_FOLDER
        assert inst.file_ctime is not None


def test_scan_main_backup_no_folder_date_unknown(tmp_path: Path):
    bak = tmp_path / "bak"
    dest = bak / "VF2S" / "jobs"
    dest.mkdir(parents=True)
    (dest / "loose.nc").write_bytes(_nc_body())
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(bak, am)
    loose = [i for i in result.instances if i.source_path.endswith("loose.nc")]
    assert loose
    for inst in loose:
        assert inst.backup_date is None
        assert inst.date_source == DATE_SOURCE_UNKNOWN
        assert inst.file_ctime is not None


def test_scan_green_extra_birth_fallback(tmp_path: Path):
    bak = tmp_path / "bak"
    green = tmp_path / "trusted"
    (bak / "15.09.2026" / "VF2S").mkdir(parents=True)
    (bak / "15.09.2026" / "VF2S" / "a.nc").write_bytes(_nc_body())
    (green / "NoDateHere").mkdir(parents=True)
    (green / "NoDateHere" / "b.nc").write_bytes(_nc_body())
    am = AliasMap.load(ALIASES)
    result = scan_with_extra_roots(
        bak,
        am,
        root_specs=[(green, PROVENANCE_BACKUP)],
    )
    greens = [
        i
        for i in result.instances
        if i.scan_root == str(green.resolve())
    ]
    assert greens
    for inst in greens:
        assert inst.backup_date is not None
        assert inst.date_source in ("birth", "mtime")
        assert inst.file_ctime == inst.backup_date


def test_scan_green_extra_folder_date(tmp_path: Path):
    bak = tmp_path / "bak"
    green = tmp_path / "trusted"
    (bak / "01.01.2026" / "VF2S").mkdir(parents=True)
    (bak / "01.01.2026" / "VF2S" / "a.nc").write_bytes(_nc_body())
    (green / "20.03.2026" / "catch").mkdir(parents=True)
    (green / "20.03.2026" / "catch" / "b.nc").write_bytes(_nc_body())
    am = AliasMap.load(ALIASES)
    result = scan_with_extra_roots(
        bak,
        am,
        root_specs=[(green, PROVENANCE_BACKUP)],
    )
    greens = [i for i in result.instances if i.scan_root == str(green.resolve())]
    assert greens
    for inst in greens:
        assert inst.backup_date == datetime(2026, 3, 20, tzinfo=timezone.utc)
        assert inst.date_source == DATE_SOURCE_FOLDER


def test_write_db_unknown_and_file_ctime(tmp_path: Path):
    bak = tmp_path / "bak"
    dest = bak / "VF2S"
    dest.mkdir(parents=True)
    (dest / "x.nc").write_bytes(_nc_body())
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(bak, am)
    db = tmp_path / "gcode_index.sqlite"
    conn = open_db(db)
    write_scan_result(conn, backup_root=str(bak), aliases_path=str(ALIASES), result=result)
    conn.commit()
    conn.row_factory = __import__("sqlite3").Row
    row = conn.execute(
        "SELECT backup_date, file_ctime, date_source FROM program_instances LIMIT 1"
    ).fetchone()
    assert row["backup_date"] == ""
    assert row["file_ctime"]
    assert row["date_source"] == DATE_SOURCE_UNKNOWN
    conn.close()


def test_yellow_extra_also_birth_fallback(tmp_path: Path):
    bak = tmp_path / "bak"
    yellow = tmp_path / "yellow"
    (bak / "15.09.2026" / "VF2S").mkdir(parents=True)
    (bak / "15.09.2026" / "VF2S" / "a.nc").write_bytes(_nc_body())
    (yellow / "Odd").mkdir(parents=True)
    (yellow / "Odd" / "c.nc").write_bytes(_nc_body())
    am = AliasMap.load(ALIASES)
    result = scan_with_extra_roots(bak, am, extra_roots=[yellow])
    yellows = [i for i in result.instances if i.provenance == PROVENANCE_EXTRA]
    assert yellows
    for inst in yellows:
        assert inst.backup_date is not None
        assert inst.date_source in ("birth", "mtime")
