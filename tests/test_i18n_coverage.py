"""Localization coverage: PL+EN keys exist and hard-coded UI literals stay out of dialogs."""

from __future__ import annotations

import re
from pathlib import Path

from gcode_index.i18n import STRINGS, t

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "src" / "gcode_index" / "gui.py"

# Keys introduced / required for the GUI i18n audit (0.2.56)
REQUIRED = [
    "compare_title",
    "close",
    "cancel",
    "ok",
    "show_in_results",
    "scan_report_title",
    "duplicates_title",
    "preview_find",
    "preview_header",
    "preview_error",
    "map_dialog_title",
    "aliases_intro",
    "scan_starting",
    "scan_done",
    "scan_failed_title",
    "extract_save_title",
    "date_today",
    "date_clear",
    "report_per_machine",
    "compare_identical",
    "help_manual_missing",
]


def test_required_keys_in_pl_and_en():
    for key in REQUIRED:
        assert key in STRINGS["pl"], key
        assert key in STRINGS["en"], key
        assert t("pl", key) != key
        assert t("en", key) != key


def test_pl_and_en_string_tables_same_keys():
    pl = set(STRINGS["pl"])
    en = set(STRINGS["en"])
    missing_en = sorted(pl - en)
    missing_pl = sorted(en - pl)
    assert missing_en == [], f"EN missing keys: {missing_en[:20]}"
    assert missing_pl == [], f"PL missing keys: {missing_pl[:20]}"


def test_gui_dialogs_use_tr_for_common_buttons():
    src = GUI.read_text(encoding="utf-8")
    # Dialog Close/Cancel/Show in results must go through _tr / self._
    assert 'text="Close"' not in src
    assert 'text="Cancel"' not in src
    assert 'text="Show in results"' not in src
    assert 'text="Save map"' not in src
    assert 'title="Compare programs"' not in src
    assert 'title="Scan report"' not in src
    assert "Duplicate / near-duplicate finder" not in src
