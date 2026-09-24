"""Tests for preview truncation (#5) and compare/diff (#12)."""

from __future__ import annotations

from pathlib import Path

from gcode_index.compare import (
    instance_label,
    preview_text,
    truncate_preview,
    unified_diff_programs,
)
from gcode_index.extract import extract_text


def test_truncate_preview_by_lines_and_chars():
    text = "\n".join(f"N{i}" for i in range(100))
    body, truncated = truncate_preview(text, max_chars=10_000, max_lines=10)
    assert truncated
    assert body.count("\n") <= 10

    long_line = "A" * 500
    body2, truncated2 = truncate_preview(long_line, max_chars=100, max_lines=50)
    assert truncated2
    assert len(body2) <= 100


def test_preview_and_diff_on_nc_files(tmp_path: Path):
    a = tmp_path / "a.nc"
    b = tmp_path / "b.nc"
    a.write_text("%\nO1234 (PART-A)\nG0 X0\nM30\n%\n", encoding="ascii")
    b.write_text("%\nO1234 (PART-A)\nG0 X1\nM30\n%\n", encoding="ascii")

    row_a = {
        "program_number": "1234",
        "machine_id": "haas-vf-2",
        "machine_label": "HAAS VF-2",
        "backup_date": "2026-09-01T00:00:00+00:00",
        "source_path": str(a),
        "source_type": "loose_nc",
        "source_size": a.stat().st_size,
        "content_sha256": None,
        "byte_start": None,
        "byte_end": None,
        "line_start": None,
        "line_end": None,
        "scan_root": None,
    }
    row_b = {
        **row_a,
        "machine_id": "haas-umc750",
        "machine_label": "HAAS UMC750",
        "backup_date": "2026-09-15T00:00:00+00:00",
        "source_path": str(b),
        "source_size": b.stat().st_size,
    }

    body, err = preview_text(row_a)
    assert err is None
    assert "O1234" in body
    assert "G0 X0" in body
    assert instance_label(row_a).startswith("1234")

    diff, derr = unified_diff_programs(row_a, row_b)
    assert derr is None
    assert "G0 X0" in diff or "-G0 X0" in diff
    assert "G0 X1" in diff or "+G0 X1" in diff
    assert "HAAS VF-2" in diff or "1234" in diff

    # Identical bodies
    same, serr = unified_diff_programs(row_a, row_a)
    assert serr is None
    assert "identical" in same.casefold()


def test_preview_missing_file(tmp_path: Path):
    row = {
        "program_number": "9",
        "machine_id": "x",
        "machine_label": "x",
        "backup_date": "2026-09-01T00:00:00+00:00",
        "source_path": str(tmp_path / "missing.nc"),
        "source_type": "loose_nc",
        "source_size": None,
        "content_sha256": None,
        "byte_start": None,
        "byte_end": None,
        "line_start": None,
        "line_end": None,
        "scan_root": None,
    }
    body, err = preview_text(row)
    assert body == ""
    assert err
    assert "missing" in err.casefold() or "not" in err.casefold() or "No such" in err
