from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from gcode_index.app_meta import format_version_build, resolve_app_meta, window_title
from gcode_index.date_format import format_display_date_dmy, parse_display_date


def test_parse_display_date():
    assert parse_display_date("15.09.2026") == date(2026, 9, 15)
    assert parse_display_date("2026-09-15") == date(2026, 9, 15)
    assert parse_display_date("") is None
    assert parse_display_date("32.01.2026") is None
    assert format_display_date_dmy(date(2026, 9, 15)) == "15.09.2026"


def test_resolve_app_meta_from_version_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    stamp = tmp_path / "VERSION.txt"
    stamp.write_text("version=0.2.41\nbuild=b99\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GCODE_INDEX_BUILD", raising=False)
    ver, build = resolve_app_meta()
    assert ver == "0.2.41"
    assert build == "b99"
    assert format_version_build() == "0.2.41-b99"
    assert "0.2.41-b99" in window_title("Test App")


def test_resolve_app_meta_env_build(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GCODE_INDEX_BUILD", "b42")
    ver, build = resolve_app_meta()
    assert ver  # package version
    assert build == "b42"
    assert format_version_build().endswith("-b42")
