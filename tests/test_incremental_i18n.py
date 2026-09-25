"""Tests for incremental scan (#9) and UI i18n defaults."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.db import open_db, write_scan_result
from gcode_index.i18n import (
    DEFAULT_LANG,
    DEFAULT_UI_MODE,
    load_ui_language,
    load_ui_mode,
    load_ui_settings,
    normalize_ui_mode,
    save_ui_language,
    save_ui_settings,
    t,
)
from gcode_index.scan_cache import load_scan_cache
from gcode_index.scanner import scan_backup_tree

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"
FIX = Path(__file__).parent / "fixtures" / "synthetic"


def test_i18n_polish_default():
    assert DEFAULT_LANG == "pl"
    assert "Indeksator" in t("pl", "app_title")
    assert "G-code" in t("en", "app_title")
    assert "(LP1)" in t("pl", "hint")
    assert "(MS1)" in t("pl", "hint")
    assert "(LP1)" in t("en", "hint")
    assert t("pl", "extract_selected").startswith("Wydobądź")
    assert "Ekstrahuj" not in t("pl", "extract_selected")
    assert "Ekstrahuj" not in t("pl", "ctx_extract")
    assert "Wydobądź" in t("pl", "ctx_extract")


def test_ui_mode_defaults():
    assert DEFAULT_UI_MODE == "simple"
    assert normalize_ui_mode("full") == "full"
    assert normalize_ui_mode("Prosty") == "simple"
    assert normalize_ui_mode("pełny") == "full"
    assert "Prosty" in t("pl", "mode_simple")
    assert "Pełny" in t("pl", "mode_full")
    assert "Wydobądź" in t("pl", "hint_simple")
    # Prosty = retrieve-only (no scan / index in the hint)
    assert "Indeksuj" not in t("pl", "hint_simple")
    assert "odczyt" in t("pl", "hint_simple").lower() or "bazę" in t("pl", "hint_simple")
    assert "Retrieve only" in t("en", "hint_simple")
    assert "Full mode" in t("en", "hint_simple")
    assert t("pl", "folders_step_simple").startswith("1")
    assert t("pl", "find_programs_step").startswith("2")
    assert "Zmień" in t("pl", "change_folders")
    assert "wszystkie" in t("pl", "machines_all")
    assert "More filters" in t("en", "more_filters")
    assert "opcjonalny" in t("pl", "backup_folder_optional")
    assert "Otwórz" in t("pl", "status_pick_simple")
    assert "Open an existing" in t("en", "status_pick_simple")


def test_ui_accent_constants():
    from gcode_index.ui_theme import UI_ACCENT, UI_KEY_FG

    assert UI_ACCENT.startswith("#")
    assert UI_KEY_FG.startswith("#")
    assert UI_ACCENT != UI_KEY_FG


def test_short_path_helper_logic():
    # Mirrors IndexerApp._short_path truncation used by the collapsed folder strip
    long = "D:\\very\\long\\path\\to\\cnc\\backups\\folder\\tree"
    maxlen = 42
    short = long if len(long) <= maxlen else "…" + long[-(maxlen - 1) :]
    assert short.startswith("…")
    assert len(short) == maxlen
    assert short.endswith("tree")


def test_ui_language_persist(tmp_path: Path):
    path = tmp_path / "ui_settings.yaml"
    save_ui_language(path, "en")
    assert load_ui_language(path) == "en"
    save_ui_language(path, "pl")
    assert load_ui_language(path) == "pl"


def test_ui_settings_mode_and_language(tmp_path: Path):
    path = tmp_path / "ui_settings.yaml"
    save_ui_settings(path, language="en", ui_mode="full")
    settings = load_ui_settings(path)
    assert settings["language"] == "en"
    assert settings["ui_mode"] == "full"
    # Language-only save keeps mode
    save_ui_language(path, "pl")
    assert load_ui_language(path) == "pl"
    assert load_ui_mode(path) == "full"
    save_ui_settings(path, ui_mode="simple")
    assert load_ui_mode(path) == "simple"
    assert load_ui_language(path) == "pl"


def test_incremental_reuses_unchanged_pgm(tmp_path: Path):
    bak = tmp_path / "bak"
    dest = bak / "15.09.2026" / "VF2S"
    dest.mkdir(parents=True)
    pgm = dest / "DUMP.PGM"
    pgm.write_bytes((FIX / "tiny.pgm").read_bytes())

    am = AliasMap.load(ALIASES)
    first = scan_backup_tree(bak, am)
    assert first.instances
    assert all(fs.status == "indexed" for fs in first.files_seen if fs.source_type == "haas_pgm_glued")

    db = tmp_path / "idx.sqlite"
    conn = open_db(db)
    write_scan_result(conn, backup_root=str(bak.resolve()), aliases_path=str(ALIASES), result=first)
    conn.commit()
    cache = load_scan_cache(conn)
    conn.close()
    assert cache.by_key

    second = scan_backup_tree(bak, am, cache=cache)
    cached = [fs for fs in second.files_seen if fs.status == "cached"]
    assert cached, "unchanged PGM should be reused from cache"
    assert len(second.instances) == len(first.instances)
    # Same program numbers
    assert {i.program_number for i in second.instances} == {
        i.program_number for i in first.instances
    }

    # Change file → must re-index
    pgm.write_bytes(
        b"%\r\nO09999 (NEW)\r\n(LP1)\r\nG0\r\n%\r\n"
    )
    third = scan_backup_tree(bak, am, cache=cache)
    assert any(fs.status == "indexed" for fs in third.files_seen if "DUMP.PGM" in (fs.source_path or ""))
    assert any(i.program_number == "09999" for i in third.instances)
    assert any(i.programmer == "LP1" for i in third.instances)
