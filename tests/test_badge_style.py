"""Windows-safe status/role colour markers (no emoji glyphs)."""

from __future__ import annotations

from gcode_index.badge_style import (
    DOT,
    DOT_LARGE,
    STATUS_SWATCH,
    flag_tag,
    flag_text,
    pick_override_role,
    role_dot,
    status_dot,
    status_swatch,
)
from gcode_index.models import (
    PROVENANCE_BACKUP,
    PROVENANCE_EXTRA,
    ROLE_FIXTURE,
    ROLE_PERSONAL,
    ROLE_PROTOTYPE,
)


def test_status_swatches_are_hex_green_yellow():
    assert STATUS_SWATCH[PROVENANCE_BACKUP].startswith("#")
    assert STATUS_SWATCH[PROVENANCE_EXTRA].startswith("#")
    assert status_swatch(PROVENANCE_BACKUP) == STATUS_SWATCH[PROVENANCE_BACKUP]
    assert status_swatch("extra") == STATUS_SWATCH[PROVENANCE_EXTRA]


def test_dots_are_monochrome_disc_not_emoji():
    assert status_dot() == DOT_LARGE == "⬤"
    assert role_dot("🔴") == "⬤"
    assert "🟢" not in flag_text(PROVENANCE_BACKUP, ["wip"])
    # Always exactly one disc — roles never add Flag discs
    assert flag_text(PROVENANCE_BACKUP, ["wip", "fixture"]) == "⬤"
    assert flag_text(PROVENANCE_BACKUP, ["wip", "wip", "WIP"]) == "⬤"
    assert flag_text(PROVENANCE_BACKUP, []) == "⬤"
    assert (
        flag_text(
            PROVENANCE_BACKUP,
            ["prototype", "fixture"],
            override_role_ids=[ROLE_PROTOTYPE],
        )
        == "⬤"
    )
    assert DOT == "●"  # compact disc still available for labels


def test_flag_tag_status_by_default():
    assert flag_tag(PROVENANCE_EXTRA, []) == "flag_extra"
    assert flag_tag(PROVENANCE_BACKUP, ["wip", "fixture"]) == "flag_backup"
    assert flag_tag(PROVENANCE_EXTRA, ["system", "system_programs"]) == "flag_extra"
    # Non-override roles do not change the tag even when present
    assert (
        flag_tag(
            PROVENANCE_BACKUP,
            ["personal", "fixture"],
            override_role_ids=[],
        )
        == "flag_backup"
    )


def test_flag_tag_override_role_replaces_status():
    assert (
        flag_tag(
            PROVENANCE_BACKUP,
            ["prototype", "fixture"],
            override_role_ids=[ROLE_PROTOTYPE],
        )
        == "flag_prototype"
    )
    assert (
        flag_tag(
            PROVENANCE_EXTRA,
            ["personal"],
            override_role_ids=[ROLE_PERSONAL],
        )
        == "flag_personal"
    )
    # No matching override → status
    assert (
        flag_tag(
            PROVENANCE_EXTRA,
            ["fixture"],
            override_role_ids=[ROLE_PROTOTYPE],
        )
        == "flag_extra"
    )


def test_pick_override_priority_prototype_first():
    # Several overrides: prototype wins over alphabetical
    assert (
        pick_override_role(
            [ROLE_FIXTURE, ROLE_PROTOTYPE, ROLE_PERSONAL],
            [ROLE_FIXTURE, ROLE_PROTOTYPE, ROLE_PERSONAL],
        )
        == ROLE_PROTOTYPE
    )
    # Without prototype: stable sorted order
    assert (
        pick_override_role(
            [ROLE_FIXTURE, ROLE_PERSONAL],
            [ROLE_FIXTURE, ROLE_PERSONAL],
        )
        == ROLE_FIXTURE
    )
    assert pick_override_role(["wip"], [ROLE_PROTOTYPE]) is None
