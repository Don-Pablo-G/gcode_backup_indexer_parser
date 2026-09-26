"""Program-body SHA: glued dump slices match loose ``.nc`` with the same body."""

from __future__ import annotations

from pathlib import Path

from gcode_index.db import open_db, write_scan_result
from gcode_index.extract import ensure_percent_frame, extract_text
from gcode_index.integrity import file_sha256
from gcode_index.locators.haas_pgm import locate_haas_pgm
from gcode_index.locators.whole_file_nc import locate_whole_file_nc
from gcode_index.models import ScanResult
from gcode_index.program_hash import (
    normalize_program_text,
    program_sha256_file,
    program_sha256_slice,
    program_sha256_text,
)
from gcode_index.scan_report import find_exact_duplicate_groups

FIX = Path(__file__).parent / "fixtures" / "synthetic"


def test_normalize_adds_percent_and_lf():
    raw = "O1234\r\nM30\r\n"
    norm = normalize_program_text(raw)
    assert norm.startswith("%\n")
    assert norm.rstrip("\n").endswith("%")
    assert "\r" not in norm
    assert program_sha256_text(raw) == program_sha256_text("%\nO1234\nM30\n%\n")


def test_glued_slice_matches_loose_nc_body(tmp_path: Path):
    """Extract-normalized slice from tiny.pgm O00001 equals a matching loose .nc."""
    pgm = FIX / "tiny.pgm"
    glued = locate_haas_pgm(pgm, source_path="tiny.pgm", machine_id="haas-sl-20")
    assert len(glued) >= 1
    slice0 = glued[0]
    assert slice0.program_sha256
    assert slice0.content_sha256 == file_sha256(pgm)

    body = extract_text(
        {
            "source_path": str(pgm.resolve()),
            "source_type": slice0.source_type,
            "line_start": slice0.line_start,
            "line_end": slice0.line_end,
            "byte_start": slice0.byte_start,
            "byte_end": slice0.byte_end,
            "content_sha256": slice0.content_sha256,
            "source_size": slice0.source_size,
        },
        skip_integrity=True,
    )
    # Same body as extract (already % framed); CRLF must not change program_sha256
    loose_path = tmp_path / "O00001.nc"
    crlf = body.replace("\r\n", "\n").replace("\n", "\r\n")
    loose_path.write_bytes(crlf.encode("ascii"))
    loose = locate_whole_file_nc(
        loose_path,
        source_path="O00001.nc",
        source_type="loose_nc",
        machine_id="haas-vf-2",
        parser_id="loose_nc",
    )
    assert loose.program_sha256 == slice0.program_sha256
    assert loose.content_sha256 != slice0.content_sha256

    assert (
        program_sha256_slice(pgm, slice0.byte_start, slice0.byte_end)
        == slice0.program_sha256
    )
    assert program_sha256_file(loose_path) == loose.program_sha256

    # Bare body without % still matches (normalization adds the frame)
    bare_path = tmp_path / "bare.nc"
    bare = "O00001 (PART-A) \nG00 X0\nM30\n"
    bare_path.write_text(bare, encoding="ascii")
    assert program_sha256_file(bare_path) == slice0.program_sha256


def test_exact_duplicates_group_glued_and_loose(tmp_path: Path):
    pgm = FIX / "tiny.pgm"
    glued = locate_haas_pgm(pgm, source_path="tiny.pgm", machine_id="haas-sl-20")[0]
    body = ensure_percent_frame(
        pgm.read_bytes()[glued.byte_start : glued.byte_end].decode(
            "ascii", errors="replace"
        )
    )
    loose_path = tmp_path / "PART-A.nc"
    loose_path.write_bytes(body.encode("ascii"))
    loose = locate_whole_file_nc(
        loose_path,
        source_path=str(loose_path),
        source_type="loose_nc",
        machine_id="haas-vf-2",
        parser_id="loose_nc",
    )
    assert glued.program_sha256 == loose.program_sha256

    db = tmp_path / "gcode_index.sqlite"
    conn = open_db(db)
    write_scan_result(
        conn,
        backup_root=str(tmp_path),
        aliases_path=None,
        result=ScanResult(instances=[glued, loose]),
    )
    exact = find_exact_duplicate_groups(conn)
    assert len(exact) == 1
    assert len(exact[0].members) == 2
    paths = {m["source_path"] for m in exact[0].members}
    assert "tiny.pgm" in paths
    assert str(loose_path) in paths
    conn.close()


def test_schema_migrates_program_sha256(tmp_path: Path):
    db = tmp_path / "old.sqlite"
    import sqlite3

    # Pre-0.2.61 shape (has content_sha256, lacks program_sha256)
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE program_instances (
          instance_id TEXT PRIMARY KEY,
          program_number TEXT NOT NULL,
          part_number TEXT,
          machine_id TEXT NOT NULL,
          machine_label TEXT,
          machine_folder_raw TEXT,
          date_folder_raw TEXT,
          backup_date TEXT NOT NULL,
          file_ctime TEXT NOT NULL,
          date_source TEXT NOT NULL,
          source_path TEXT NOT NULL,
          line_start INTEGER,
          line_end INTEGER,
          byte_start INTEGER,
          byte_end INTEGER,
          source_type TEXT NOT NULL,
          folder_path TEXT,
          control_family TEXT,
          source_mtime TEXT,
          source_size INTEGER,
          content_sha256 TEXT,
          indexed_at TEXT NOT NULL,
          parser_id TEXT,
          parser_version TEXT,
          parse_status TEXT,
          error_message TEXT,
          header_kind TEXT,
          provenance TEXT NOT NULL DEFAULT 'backup',
          scan_root TEXT,
          programmer TEXT,
          run_id TEXT
        );
        CREATE TABLE index_runs (
          run_id TEXT PRIMARY KEY,
          started_at TEXT NOT NULL,
          finished_at TEXT,
          backup_root TEXT NOT NULL,
          aliases_path TEXT,
          indexer_version TEXT,
          instance_count INTEGER,
          file_count INTEGER,
          unknown_count INTEGER
        );
        """
    )
    conn.commit()
    conn.close()

    conn = open_db(db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(program_instances)")}
    assert "program_sha256" in cols
    assert "content_sha256" in cols
    conn.close()
