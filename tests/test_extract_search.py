from __future__ import annotations

from pathlib import Path

import pytest

from gcode_index.db import open_db, query_instances, rank_match, search_instances, validate_search_query
from gcode_index.extract import (
    ExtractError,
    default_extract_filename,
    extract_text,
    extract_to_path,
)


def test_validate_search_query():
    assert validate_search_query("1234") == "1234"
    assert validate_search_query("  O1234  ") == "O1234"
    assert validate_search_query("P-00253232 VA") == "P-00253232 VA"
    assert validate_search_query("abc") == "abc"
    with pytest.raises(ValueError):
        validate_search_query("   ")
    with pytest.raises(ValueError):
        validate_search_query("")


def test_rank_prefers_prefix_and_exact():
    assert rank_match("1234", None, "1234") < rank_match("X1234", None, "1234")
    assert rank_match("12345", None, "1234") < rank_match("991234", None, "1234")
    # O-prefix / padding normalize: O1234 and 1234 are the same logical program
    assert rank_match("O1234", "PART-1234", "1234") == 0
    assert rank_match("01234", None, "O1234") == 0
    # program exact beats part prefix
    assert rank_match("1234", "other", "1234") < rank_match("Z", "1234-A", "1234")


def _seed_search_db(tmp_path: Path):
    conn = open_db(tmp_path / "idx.sqlite")
    conn.execute(
        """
        INSERT INTO index_runs (run_id, started_at, backup_root, indexer_version)
        VALUES ('r1', '2026-01-01T00:00:00+00:00', '/bak', '0.2.0')
        """
    )
    rows = [
        # mid-string program
        ("a", "XX1234YY", "PART-A", "haas-sl-10", "2026-01-01T00:00:00+00:00"),
        # prefix program
        ("b", "1234AB", "OTHER", "haas-sl-20", "2026-02-01T00:00:00+00:00"),
        # exact program
        ("c", "1234", "EXACT-PART", "puma", "2026-03-01T00:00:00+00:00"),
        # part-number prefix only
        ("d", "O9999", "1234-BRACKET", "sbl-500", "2026-04-01T00:00:00+00:00"),
        # unrelated
        ("e", "O5555", "NOPE", "puma", "2026-05-01T00:00:00+00:00"),
    ]
    for iid, prog, part, machine, date in rows:
        conn.execute(
            """
            INSERT INTO program_instances (
              instance_id, program_number, part_number, machine_id,
              backup_date, file_ctime, date_source, source_path, source_type,
              indexed_at, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, 'birth', 'x.pgm', 'haas_pgm_glued', ?, 'r1')
            """,
            (iid, prog, part, machine, date, date, date),
        )
    conn.commit()
    return conn


def test_search_ranking_order(tmp_path: Path):
    conn = _seed_search_db(tmp_path)
    try:
        hits = search_instances(conn, "1234", limit=20)
        ids = [r["instance_id"] for r in hits]
        assert "e" not in ids
        # exact → program prefix → part prefix → program substring
        assert ids == ["c", "b", "d", "a"]
    finally:
        conn.close()


def test_search_letters_and_filters(tmp_path: Path):
    conn = _seed_search_db(tmp_path)
    try:
        # Letter / punctuation free-text on part name
        hits = search_instances(conn, "BRACKET", limit=20)
        assert [r["instance_id"] for r in hits] == ["d"]

        # Case-insensitive: Va vs va / P- vs p-
        conn.execute(
            """
            UPDATE program_instances SET part_number = 'P-00045613 Va'
            WHERE instance_id = 'd'
            """
        )
        conn.commit()
        lower = search_instances(conn, "p-00045613 va", limit=20)
        upper = search_instances(conn, "P-00045613 VA", limit=20)
        assert [r["instance_id"] for r in lower] == ["d"]
        assert [r["instance_id"] for r in upper] == ["d"]

        # Machine filter
        by_machine = query_instances(conn, machine="puma", limit=50)
        assert {r["instance_id"] for r in by_machine} == {"c", "e"}

        # Date range (inclusive day bounds) — ISO and DD.MM.YYYY
        by_date = query_instances(
            conn, date_from="2026-02-01", date_to="2026-03-31", limit=50
        )
        assert {r["instance_id"] for r in by_date} == {"b", "c"}
        by_date_eu = query_instances(
            conn, date_from="01.02.2026", date_to="31.03.2026", limit=50
        )
        assert {r["instance_id"] for r in by_date_eu} == {"b", "c"}
        with pytest.raises(ValueError, match="invalid date"):
            query_instances(conn, date_from="32.01.2026", limit=10)

        # Combined text + machine
        combo = query_instances(conn, text="1234", machine="haas-sl-20", limit=50)
        assert [r["instance_id"] for r in combo] == ["b"]

        # Multi-select machines (OR)
        multi = query_instances(
            conn, machines=["puma", "haas-sl-20"], limit=50
        )
        assert {r["instance_id"] for r in multi} == {"b", "c", "e"}

        # machines= wins over machine=
        override = query_instances(
            conn, machine="puma", machines=["haas-sl-10"], limit=50
        )
        assert {r["instance_id"] for r in override} == {"a"}
    finally:
        conn.close()


def test_extract_glued_line_span(tmp_path: Path):
    # CRLF Haas-style dump
    body = (
        b"%\r\n"
        b"O00001 (PART-A)\r\n"
        b"G00 X0\r\n"
        b"M30\r\n"
        b"O00002 (PART-B)\r\n"
        b"G01 Y1\r\n"
        b"%\r\n"
    )
    src = tmp_path / "tiny.pgm"
    src.write_bytes(body)
    row = {
        "source_path": str(src),
        "source_type": "haas_pgm_glued",
        "line_start": 2,
        "line_end": 4,
        "byte_start": None,
        "byte_end": None,
        "program_number": "O00001",
    }
    text = extract_text(row)
    assert text.lstrip().startswith("%")
    assert "O00001" in text
    assert text.rstrip().endswith("%")
    assert "PART-A" in text
    assert "O00002" not in text
    out = extract_to_path(row, tmp_path / "out" / "O00001.nc")
    assert out.is_file()
    written = out.read_text(encoding="utf-8")
    assert "PART-A" in written
    assert written.lstrip().startswith("%")
    assert written.rstrip().endswith("%")


def test_extract_glued_byte_span(tmp_path: Path):
    data = b"AAA\r\nO1234 (P)\r\nG00\r\nBBB\r\n"
    src = tmp_path / "dump.pgm"
    src.write_bytes(data)
    start = data.index(b"O1234")
    end = data.index(b"BBB")
    row = {
        "source_path": "dump.pgm",
        "source_type": "haas_pgm_glued",
        "line_start": None,
        "line_end": None,
        "byte_start": start,
        "byte_end": end,
        "program_number": "O1234",
    }
    text = extract_text(row, backup_root=tmp_path)
    assert text.lstrip().startswith("%")
    assert "O1234" in text
    assert text.rstrip().endswith("%")
    assert "BBB" not in text


def test_ensure_percent_frame_idempotent():
    from gcode_index.extract import ensure_percent_frame

    already = "%\nO1\nM30\n%\n"
    assert ensure_percent_frame(already) == already
    bare = "O1\nM30\n"
    framed = ensure_percent_frame(bare)
    assert framed.startswith("%\n")
    assert framed.rstrip().endswith("%")
    assert framed.count("%") == 2


def test_extract_whole_file_nc(tmp_path: Path):
    src = tmp_path / "O1234.nc"
    src.write_text("%\nO1234\nM30\n%\n", encoding="ascii")
    row = {
        "source_path": str(src.name),
        "source_type": "loose_nc",
        "line_start": None,
        "line_end": None,
        "byte_start": None,
        "byte_end": None,
        "program_number": "O1234",
    }
    assert "O1234" in extract_text(row, backup_root=tmp_path)
    assert default_extract_filename(row) == "O1234.nc"


def test_extract_loose_nc_without_percent_left_alone(tmp_path: Path):
    """Whole-file .nc must not get an invented % frame (e.g. some ST-20Y dumps)."""
    src = tmp_path / "bare.nc"
    src.write_text("O9278\nG00 X0\nM30\n", encoding="ascii")
    row = {
        "source_path": "bare.nc",
        "source_type": "loose_nc",
        "line_start": None,
        "line_end": None,
        "byte_start": None,
        "byte_end": None,
        "program_number": "9278",
    }
    text = extract_text(row, backup_root=tmp_path)
    assert text == "O9278\nG00 X0\nM30\n"
    assert not text.lstrip().startswith("%")


def test_extract_missing_file(tmp_path: Path):
    row = {
        "source_path": "missing.nc",
        "source_type": "loose_nc",
        "line_start": None,
        "line_end": None,
        "byte_start": None,
        "byte_end": None,
        "program_number": "X",
    }
    with pytest.raises(ExtractError):
        extract_text(row, backup_root=tmp_path)


def test_extract_refuses_changed_source(tmp_path: Path):
    from gcode_index.integrity import file_sha256

    src = tmp_path / "job.nc"
    src.write_text("%\nO1\nM30\n%\n", encoding="ascii")
    digest = file_sha256(src)
    row = {
        "source_path": "job.nc",
        "source_type": "loose_nc",
        "line_start": None,
        "line_end": None,
        "byte_start": None,
        "byte_end": None,
        "program_number": "1",
        "source_size": src.stat().st_size,
        "content_sha256": digest,
    }
    assert "O1" in extract_text(row, backup_root=tmp_path)

    src.write_text("%\nO1\nG00 X1\nM30\n%\n", encoding="ascii")
    with pytest.raises(ExtractError, match="changed since index"):
        extract_text(row, backup_root=tmp_path)

    # Explicit bypass for recovery tools
    assert "G00" in extract_text(row, backup_root=tmp_path, skip_integrity=True)


def test_path_util_helpers():
    from gcode_index.path_util import format_eta, resolve_source_abspath

    assert format_eta(None) == ""
    assert "s left" in format_eta(12)
    assert "m" in format_eta(125)
    p = resolve_source_abspath("sub/a.nc", "/bak")
    assert p == Path("/bak") / "sub" / "a.nc"
    abs_p = resolve_source_abspath("/abs/x.nc", "/bak")
    assert abs_p == Path("/abs/x.nc")


def test_gui_module_importable():
    tkinter = pytest.importorskip("tkinter")
    assert tkinter is not None
    from gcode_index import gui

    assert hasattr(gui, "IndexerApp")
    assert hasattr(gui, "main")
    assert gui.SEARCH_DEBOUNCE_MS >= 150
    assert "UNKNOWN" in gui.UNKNOWN_MACHINE_DISPLAY
    assert "unknown" in gui.UNKNOWN_MACHINE_DISPLAY
