"""Hide duplicates (SHA collapse) — green then newest survivor."""

from __future__ import annotations

from gcode_index.db import collapse_hide_duplicates
from gcode_index.i18n import t


def _row(
    iid: str,
    sha: str | None,
    *,
    date: str = "2026-09-01T00:00:00+00:00",
    green: bool = False,
    machine: str = "vf2",
) -> dict:
    return {
        "instance_id": iid,
        "program_sha256": sha,
        "content_sha256": None,
        "backup_date": date,
        "machine_id": machine,
        "program_number": "1234",
        "provenance": "backup" if green else "extra",
        "role": None,
    }


def test_collapse_hide_duplicates_prefers_green_then_newest():
    rows = [
        _row("a", "sha1", date="2026-09-20T00:00:00+00:00", green=False),
        _row("b", "sha1", date="2026-09-10T00:00:00+00:00", green=True),
        _row("c", "sha1", date="2026-09-25T00:00:00+00:00", green=False),
        _row("d", "sha2", date="2026-09-01T00:00:00+00:00", green=False),
    ]
    out = collapse_hide_duplicates(rows, is_green=lambda r: r["provenance"] == "backup")
    assert [r["instance_id"] for r in out] == ["b", "d"]


def test_collapse_hide_duplicates_newest_among_same_colour():
    rows = [
        _row("old", "sha1", date="2026-09-01T00:00:00+00:00", green=True),
        _row("new", "sha1", date="2026-09-15T00:00:00+00:00", green=True),
    ]
    out = collapse_hide_duplicates(rows, is_green=lambda r: True)
    assert [r["instance_id"] for r in out] == ["new"]


def test_collapse_hide_duplicates_keeps_null_hashes():
    rows = [
        _row("u1", None, date="2026-09-01T00:00:00+00:00"),
        _row("u2", "", date="2026-09-02T00:00:00+00:00"),
        _row("h1", "sha1", date="2026-09-03T00:00:00+00:00"),
        _row("h2", "sha1", date="2026-09-04T00:00:00+00:00"),
    ]
    out = collapse_hide_duplicates(rows, is_green=lambda _r: False)
    ids = [r["instance_id"] for r in out]
    assert "u1" in ids and "u2" in ids
    assert ids.count("h1") + ids.count("h2") == 1
    assert "h2" in ids  # newer


def test_collapse_hide_duplicates_global_across_machines():
    rows = [
        _row("vf", "sha1", date="2026-09-10T00:00:00+00:00", machine="vf2"),
        _row("sl", "sha1", date="2026-09-05T00:00:00+00:00", machine="sl10"),
    ]
    out = collapse_hide_duplicates(rows, is_green=lambda _r: False)
    assert len(out) == 1
    assert out[0]["instance_id"] == "vf"


def test_collapse_hide_duplicates_stable_instance_id_tie():
    rows = [
        _row("z-late", "sha1", date="2026-09-10T00:00:00+00:00"),
        _row("a-early", "sha1", date="2026-09-10T00:00:00+00:00"),
    ]
    out = collapse_hide_duplicates(rows, is_green=lambda _r: False)
    assert [r["instance_id"] for r in out] == ["a-early"]


def test_collapse_content_sha_fallback_when_program_col_absent():
    rows = [
        {
            "instance_id": "1",
            "content_sha256": "csha",
            "backup_date": "2026-09-01T00:00:00+00:00",
        },
        {
            "instance_id": "2",
            "content_sha256": "csha",
            "backup_date": "2026-09-02T00:00:00+00:00",
        },
    ]
    out = collapse_hide_duplicates(rows)
    assert [r["instance_id"] for r in out] == ["2"]


def test_hide_duplicates_i18n_keys():
    assert t("pl", "hide_duplicates") == "Ukryj duplikaty"
    assert t("en", "hide_duplicates") == "Hide duplicates"
    assert t("pl", "status_hide_duplicates") == "ukryte duplikaty"
    assert t("en", "status_hide_duplicates") == "hide-duplicates"
    assert t("pl", "filters_menu") == "Filtry ▾"
    assert t("en", "filters_menu") == "Filters ▾"
    assert t("pl", "filters_menu_n", n=2) == "Filtry ▾ 2"
    assert t("en", "filters_menu_n", n=3) == "Filters ▾ 3"
    assert t("pl", "filters_menu_title") == "Filtry"
    assert t("en", "filters_menu_title") == "Filters"
