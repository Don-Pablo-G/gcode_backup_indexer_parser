"""Tests for bundled Help manuals (EN/PL)."""

from __future__ import annotations

from gcode_index.help_docs import docs_roots, read_manual, resolve_manual
from gcode_index.i18n import t


def test_manuals_resolve_en_and_pl():
    for lang in ("en", "pl"):
        for kind in ("simple", "full"):
            path = resolve_manual(lang, kind)  # type: ignore[arg-type]
            assert path is not None, f"missing manual {lang}/{kind}"
            assert path.is_file()
            text = read_manual(lang, kind)  # type: ignore[arg-type]
            assert len(text) > 200
            assert "Manual not found" not in text


def test_simple_manual_mentions_retrieve_only():
    pl = read_manual("pl", "simple")
    en = read_manual("en", "simple")
    assert "Prosty" in pl or "wydob" in pl.casefold()
    assert "Simple" in en
    assert "Full" in en or "index" in en.casefold()


def test_full_manual_mentions_scan():
    pl = read_manual("pl", "full")
    en = read_manual("en", "full")
    assert "Indeksuj" in pl or "skan" in pl.casefold()
    assert "scan" in en.casefold() or "index" in en.casefold()


def test_docs_roots_nonempty():
    roots = docs_roots()
    assert roots
    assert any((r / "en").is_dir() or (r / "pl").is_dir() for r in roots if r.exists())


def test_help_i18n_keys():
    assert "Pomoc" in t("pl", "menu_help")
    assert "Help" in t("en", "menu_help")
    assert "Prosty" in t("pl", "help_manual_simple")
    assert "Simple" in t("en", "help_manual_simple")
    assert "Pełny" in t("pl", "help_manual_full")
    assert "Full" in t("en", "help_manual_full")
