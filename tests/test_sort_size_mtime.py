from __future__ import annotations

from pathlib import Path

import pytest

from gcode_index.db import (
    format_display_size,
    instance_size_bytes,
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


def test_instance_size_bytes_span_vs_source():
    """Glued rows use span; loose / null span fall back to source_size."""
    assert instance_size_bytes(
        {"byte_start": 100, "byte_end": 250, "source_size": 9_600_000}
    ) == 150
    assert instance_size_bytes(
        {"byte_start": None, "byte_end": None, "source_size": 4096}
    ) == 4096
    assert instance_size_bytes({"source_size": 512}) == 512
    assert instance_size_bytes({}) is None
    # Half-open: end == start → 0-byte span (still preferred over dump size)
    assert (
        instance_size_bytes(
            {"byte_start": 10, "byte_end": 10, "source_size": 999}
        )
        == 0
    )


def _seed_size_mtime_db(tmp_path: Path):
    conn = open_db(tmp_path / "idx.sqlite")
    conn.execute(
        """
        INSERT INTO index_runs (run_id, started_at, backup_root, indexer_version)
        VALUES ('r1', '2026-01-01T00:00:00+00:00', '/bak', '0.2.0')
        """
    )
    rows = [
        # iid, prog, size, mtime, backup_date, byte_start, byte_end
        ("a", "O100", 100, "2026-01-10T12:00:00+00:00", "2026-01-10T12:00:00+00:00", None, None),
        ("b", "O200", 5000, "2026-02-15T12:00:00+00:00", "2026-02-15T12:00:00+00:00", None, None),
        ("c", "O300", 2_000_000, "2026-03-20T12:00:00+00:00", "2026-03-20T12:00:00+00:00", None, None),
        ("d", "O400", None, None, "2026-04-01T12:00:00+00:00", None, None),  # null size/mtime
        # Glued dump: huge source_size, tiny instance span
        (
            "g",
            "O500",
            9_600_000,
            "2026-05-01T12:00:00+00:00",
            "2026-05-01T12:00:00+00:00",
            1000,
            1250,
        ),
    ]
    for iid, prog, size, mtime, bdate, bstart, bend in rows:
        conn.execute(
            """
            INSERT INTO program_instances (
              instance_id, program_number, part_number, machine_id,
              backup_date, file_ctime, date_source, source_path, source_type,
              source_mtime, source_size, byte_start, byte_end, indexed_at, run_id
            ) VALUES (?, ?, 'P', 'puma', ?, ?, 'birth', 'x.pgm', 'loose_nc',
                      ?, ?, ?, ?, ?, 'r1')
            """,
            (iid, prog, bdate, bdate, mtime, size, bstart, bend, bdate),
        )
    conn.commit()
    return conn


def test_query_size_and_mtime_filters(tmp_path: Path):
    conn = _seed_size_mtime_db(tmp_path)
    try:
        by_min = query_instances(conn, size_min="1k", limit=50)
        assert {r["instance_id"] for r in by_min} == {"b", "c"}

        by_max = query_instances(conn, size_max=200, limit=50)
        # glued span 250 bytes is > 200; only tiny loose row "a"
        assert {r["instance_id"] for r in by_max} == {"a"}

        by_range = query_instances(conn, size_min=100, size_max="10k", limit=50)
        # glued 250B + loose a/b; not dump 9.6MB
        assert {r["instance_id"] for r in by_range} == {"a", "b", "g"}

        # Instance-size filter: glued row matches span, not dump size
        glued_only = query_instances(conn, size_min=200, size_max=300, limit=50)
        assert {r["instance_id"] for r in glued_only} == {"g"}
        dump_range = query_instances(conn, size_min="9M", size_max="10M", limit=50)
        assert {r["instance_id"] for r in dump_range} == set()

        by_mtime = query_instances(
            conn, mtime_from="01.02.2026", mtime_to="28.02.2026", limit=50
        )
        assert {r["instance_id"] for r in by_mtime} == {"b"}

        # Null size excluded from size filters; null mtime falls back to backup_date
        by_file = query_instances(
            conn, mtime_from="01.04.2026", mtime_to="30.04.2026", limit=50
        )
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
            "O500",
        ]
        by_size = sort_instances(rows, "size", reverse=True)
        # Largest instance size first: c (2M), then b (5k), g (250), a (100), d (null/-1)
        assert [r["instance_id"] for r in by_size] == ["c", "b", "g", "a", "d"]
        by_date = sort_instances(rows, "date", reverse=True)
        assert by_date[0]["instance_id"] == "g"
    finally:
        conn.close()


def test_query_glued_instance_size_not_dump(tmp_path: Path):
    """Size filters must not treat glued dump source_size as the program size."""
    conn = _seed_size_mtime_db(tmp_path)
    try:
        tiny = query_instances(conn, size_max=500, limit=50)
        assert "g" in {r["instance_id"] for r in tiny}
        assert all(
            instance_size_bytes(r) is None or instance_size_bytes(r) <= 500
            for r in tiny
        )
    finally:
        conn.close()
