"""Windows-safe status/role colour markers (no emoji glyphs)."""

from __future__ import annotations

from gcode_index.badge_style import (
    DOT,
    DOT_LARGE,
    STATUS_SWATCH,
    flag_tag,
    flag_text,
    role_dot,
    status_dot,
    status_swatch,
)
from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA


def test_status_swatches_are_hex_green_yellow():
    assert STATUS_SWATCH[PROVENANCE_BACKUP].startswith("#")
    assert STATUS_SWATCH[PROVENANCE_EXTRA].startswith("#")
    assert status_swatch(PROVENANCE_BACKUP) == STATUS_SWATCH[PROVENANCE_BACKUP]
    assert status_swatch("extra") == STATUS_SWATCH[PROVENANCE_EXTRA]


def test_dots_are_monochrome_disc_not_emoji():
    assert status_dot() == DOT_LARGE == "⬤"
    assert role_dot("🔴") == "⬤"
    assert "🟢" not in flag_text(PROVENANCE_BACKUP, ["wip"])
    # Status disc + unique role discs (roles alongside, not replacing status)
    assert flag_text(PROVENANCE_BACKUP, ["wip", "fixture"]) == "⬤⬤⬤"
    assert flag_text(PROVENANCE_BACKUP, ["wip", "wip", "WIP"]) == "⬤⬤"
    assert flag_text(PROVENANCE_BACKUP, []) == "⬤"
    assert DOT == "●"  # compact disc still available for labels


def test_flag_tag_status_wins_by_default():
    assert flag_tag(PROVENANCE_EXTRA, []) == "flag_extra"
    assert flag_tag(PROVENANCE_BACKUP, ["wip", "fixture"]) == "flag_backup"
    assert flag_tag(PROVENANCE_EXTRA, ["system", "system_programs"]) == "flag_extra"


def test_flag_tag_role_overshadow_when_enabled():
    assert (
        flag_tag(
            PROVENANCE_BACKUP,
            ["wip", "fixture"],
            role_overshadow_status=True,
        )
        == "flag_fixture"
    )  # sorted unique → fixture first
    assert (
        flag_tag(
            PROVENANCE_EXTRA,
            ["system_programs"],
            role_overshadow_status=True,
        )
        == "flag_system_programs"
    )
    assert (
        flag_tag(PROVENANCE_EXTRA, [], role_overshadow_status=True) == "flag_extra"
    )
