from __future__ import annotations

from pathlib import Path

import pytest

from gcode_index.db import (
    format_display_size,
    open_db,
    parse_size_bound,
    query_instances,
    sort_instances,
)


def test_parse_size_bound():
    assert parse_size_bound(None) is None
    assert parse_size_bound("") is None
    assert parse_size_bound("  ") is None
    assert parse_size_bound("1024") == 1024
    assert parse_size_bound("10k") == 10 * 1024
    assert parse_size_bound("10KB") == 10 * 1024
    assert parse_size_bound("1.5M") == int(1.5 * 1024 * 1024)
    assert parse_size_bound("1,5m") == int(1.5 * 1024 * 1024)
    assert parse_size_bound("2G") == 2 * 1024**3
    with pytest.raises(ValueError):
        parse_size_bound("abc")
    with pytest.raises(ValueError):
        parse_size_bound("-10")


def test_format_display_size():
    assert format_display_size(None) == ""
    assert format_display_size(500) == "500"
    assert format_display_size(2048) == "2K"
    assert format_display_size(1536) == "1.5K"
    assert format_display_size(2 * 1024 * 1024) == "2M"


def _seed_size_mtime_db(tmp_path: Path):
    conn = open_db(tmp_path / "idx.sqlite")
    conn.execute(
        """
        INSERT INTO index_runs (run_id, started_at, backup_root, indexer_version)
        VALUES ('r1', '2026-01-01T00:00:00+00:00', '/bak', '0.2.0')
        """
    )
    rows = [
        # iid, prog, size, mtime, backup_date
        ("a", "O100", 100, "2026-01-10T12:00:00+00:00", "2026-01-10T12:00:00+00:00"),
        ("b", "O200", 5000, "2026-02-15T12:00:00+00:00", "2026-02-15T12:00:00+00:00"),
        ("c", "O300", 2_000_000, "2026-03-20T12:00:00+00:00", "2026-03-20T12:00:00+00:00"),
        ("d", "O400", None, None, "2026-04-01T12:00:00+00:00"),  # null size/mtime
    ]
    for iid, prog, size, mtime, bdate in rows:
        conn.execute(
            """
            INSERT INTO program_instances (
              instance_id, program_number, part_number, machine_id,
              backup_date, file_ctime, date_source, source_path, source_type,
              source_mtime, source_size, indexed_at, run_id
            ) VALUES (?, ?, 'P', 'puma', ?, ?, 'birth', 'x.pgm', 'loose_nc',
                      ?, ?, ?, 'r1')
            """,
            (iid, prog, bdate, bdate, mtime, size, bdate),
        )
    conn.commit()
    return conn


def test_query_size_and_mtime_filters(tmp_path: Path):
    conn = _seed_size_mtime_db(tmp_path)
    try:
        by_min = query_instances(conn, size_min="1k", limit=50)
        assert {r["instance_id"] for r in by_min} == {"b", "c"}

        by_max = query_instances(conn, size_max=200, limit=50)
        assert {r["instance_id"] for r in by_max} == {"a"}

        by_range = query_instances(conn, size_min=100, size_max="10k", limit=50)
        assert {r["instance_id"] for r in by_range} == {"a", "b"}

        by_mtime = query_instances(
            conn, mtime_from="01.02.2026", mtime_to="28.02.2026", limit=50
        )
        assert {r["instance_id"] for r in by_mtime} == {"b"}

        # Null size excluded from size filters; null mtime falls back to backup_date
        by_file = query_instances(conn, mtime_from="01.04.2026", limit=50)
        assert {r["instance_id"] for r in by_file} == {"d"}
    finally:
        conn.close()


def test_sort_instances_columns(tmp_path: Path):
    conn = _seed_size_mtime_db(tmp_path)
    try:
        rows = query_instances(conn, limit=50)
        by_prog = sort_instances(rows, "program", reverse=False)
        assert [r["program_number"] for r in by_prog] == [
            "O100",
            "O200",
            "O300",
            "O400",
        ]
        by_size = sort_instances(rows, "size", reverse=True)
        # null size sorts as -1 → last when reverse=True (largest first)
        assert by_size[0]["instance_id"] == "c"
        assert by_size[-1]["instance_id"] == "d"
        by_date = sort_instances(rows, "date", reverse=True)
        assert by_date[0]["instance_id"] == "d"
    finally:
        conn.close()
