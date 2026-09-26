"""Missing-source detection and badge i18n."""

from __future__ import annotations

from pathlib import Path

import pytest

from gcode_index.extract import ExtractError, extract_text
from gcode_index.i18n import t
from gcode_index.path_util import source_exists_on_disk


def test_source_exists_on_disk(tmp_path: Path):
    present = tmp_path / "job.nc"
    present.write_text("O1\n", encoding="ascii")
    assert source_exists_on_disk("job.nc", str(tmp_path)) is True
    assert source_exists_on_disk("gone.nc", str(tmp_path)) is False
    assert source_exists_on_disk("", str(tmp_path)) is False
    assert source_exists_on_disk(str(present), str(tmp_path)) is True


def test_source_exists_respects_absolute(tmp_path: Path):
    present = tmp_path / "abs.nc"
    present.write_text("x", encoding="ascii")
    assert source_exists_on_disk(str(present), backup_root="/nonexistent") is True
    assert source_exists_on_disk(str(tmp_path / "no.nc"), backup_root="/nonexistent") is False


def test_extract_missing_message_mentions_scan(tmp_path: Path):
    row = {
        "source_path": "missing.nc",
        "source_type": "loose_nc",
        "line_start": None,
        "line_end": None,
        "byte_start": None,
        "byte_end": None,
        "program_number": "X",
    }
    with pytest.raises(ExtractError, match="missing on disk") as ei:
        extract_text(row, backup_root=tmp_path)
    assert "scan" in str(ei.value).casefold()


def test_missing_badge_i18n():
    assert t("pl", "badge_missing") == "BRAK"
    assert t("en", "badge_missing") == "MISSING"
    assert t("pl", "badge_ok") == "✓"
    assert t("en", "badge_ok") == "✓"
    assert "Źródło" in t("pl", "col_src")
    assert "Source" in t("en", "col_src")
    assert "nie istnieje" in t("pl", "extract_source_missing", path="X").casefold()
    assert "missing" in t("en", "extract_source_missing", path="X").casefold()
    assert "3" in t("pl", "status_missing_sources", n=3)
