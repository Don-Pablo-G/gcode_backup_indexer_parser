"""Unit tests for results-table column layout helpers."""

from __future__ import annotations

from gcode_index.column_layout import (
    DEFAULT_COLUMN_WIDTHS,
    MIN_COLUMN_WIDTH,
    format_column_widths,
    merge_widths,
    parse_column_widths,
    redistribute_to_width,
    resize_adjacent,
)


def test_parse_format_roundtrip():
    raw = "flag=90, path=300, bogus=x, size=50"
    parsed = parse_column_widths(raw)
    assert parsed["flag"] == 90
    assert parsed["path"] == 300
    assert parsed["size"] == 50
    assert "bogus" not in parsed
    cols = ("flag", "path", "size")
    text = format_column_widths(parsed, cols)
    assert "flag=90" in text
    assert "path=300" in text
    again = parse_column_widths(text)
    assert again["flag"] == 90


def test_merge_widths_keeps_defaults():
    merged = merge_widths({"path": 400, "unknown": 9}, ("flag", "path", "program"))
    assert merged["path"] == 400
    assert merged["flag"] == DEFAULT_COLUMN_WIDTHS["flag"]
    assert "unknown" not in merged


def test_redistribute_fills_exact_total():
    widths = {"flag": 80, "program": 100, "path": 200}
    visible = ["flag", "program", "path"]
    out = redistribute_to_width(widths, visible, 500)
    assert sum(out.values()) == 500
    # Extra goes to path (fill priority)
    assert out["path"] == 200 + (500 - 380)
    assert out["flag"] == 80
    assert out["program"] == 100


def test_redistribute_shrinks_when_too_wide():
    widths = {"flag": 200, "program": 200, "path": 400}
    out = redistribute_to_width(widths, ["flag", "program", "path"], 300)
    assert sum(out.values()) == 300
    assert all(w >= MIN_COLUMN_WIDTH for w in out.values())


def test_resize_adjacent_absorbs_delta():
    widths = {"a": 100, "b": 200, "c": 150}
    out = resize_adjacent(widths, "a", "b", 40)
    assert out["a"] == 140
    assert out["b"] == 160
    assert out["c"] == 150
    assert out["a"] + out["b"] == widths["a"] + widths["b"]

    # Clamp at min — cannot steal past minwidth from neighbor
    out2 = resize_adjacent({"a": 100, "b": MIN_COLUMN_WIDTH}, "a", "b", 50)
    assert out2["a"] == 100
    assert out2["b"] == MIN_COLUMN_WIDTH

    out3 = resize_adjacent({"a": 100, "b": 200}, "a", "b", -80)
    # give = min(80, 100-40) = 60 → a=40, b=260
    assert out3["a"] == MIN_COLUMN_WIDTH
    assert out3["b"] == 260
