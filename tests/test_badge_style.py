"""Windows-safe status/role colour markers + multi-colour Flag discs."""

from __future__ import annotations

from gcode_index.badge_style import (
    DOT,
    DOT_LARGE,
    STATUS_SWATCH,
    flag_discs,
    flag_tag,
    flag_text,
    is_flag_green,
    normalize_swatch_hex,
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
    ROLE_SYSTEM_PROGRAMS,
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
    # Plain-text fallback stays one glyph (GUI uses images for multi-colour)
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


def test_flag_discs_status_plus_distinct_functions():
    swatches = {
        ROLE_PERSONAL: "#C0392B",
        ROLE_SYSTEM_PROGRAMS: "#E67E22",
        ROLE_FIXTURE: "#8E44AD",
        ROLE_PROTOTYPE: "#2980B9",
    }
    discs = flag_discs(
        PROVENANCE_BACKUP,
        [ROLE_PERSONAL, ROLE_SYSTEM_PROGRAMS, ROLE_PERSONAL],
        role_swatches=swatches,
    )
    assert [d[0] for d in discs] == [
        PROVENANCE_BACKUP,
        ROLE_PERSONAL,
        ROLE_SYSTEM_PROGRAMS,
    ]
    assert discs[0][1] == STATUS_SWATCH[PROVENANCE_BACKUP]
    # Same colour as status is skipped
    green_personal = dict(swatches)
    green_personal[ROLE_PERSONAL] = STATUS_SWATCH[PROVENANCE_BACKUP]
    discs2 = flag_discs(
        PROVENANCE_BACKUP,
        [ROLE_PERSONAL, ROLE_FIXTURE],
        role_swatches=green_personal,
    )
    assert [d[0] for d in discs2] == [PROVENANCE_BACKUP, ROLE_FIXTURE]


def test_flag_discs_override_replaces_status():
    swatches = {ROLE_PROTOTYPE: "#2980B9", ROLE_PERSONAL: "#C0392B"}
    discs = flag_discs(
        PROVENANCE_BACKUP,
        [ROLE_PROTOTYPE, ROLE_PERSONAL],
        override_role_ids=[ROLE_PROTOTYPE],
        role_swatches=swatches,
    )
    assert discs == [(ROLE_PROTOTYPE, "#2980B9")]


def test_normalize_swatch_hex_dedupe():
    assert normalize_swatch_hex("#1A7F37") == normalize_swatch_hex("1a7f37")
    assert normalize_swatch_hex("#abc") == "#aabbcc"


def test_flag_tag_status_by_default():
    assert flag_tag(PROVENANCE_EXTRA, []) == "flag_extra"
    assert flag_tag(PROVENANCE_BACKUP, ["wip", "fixture"]) == "flag_backup"
    assert flag_tag(PROVENANCE_EXTRA, ["system", "system_programs"]) == "flag_extra"
    # Non-override roles do not change the row tag even when present
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


def test_is_flag_green_matches_primary_disc():
    """Only green = primary Flag disc is backup green (not yellow, not override)."""
    assert is_flag_green(PROVENANCE_BACKUP, []) is True
    assert is_flag_green(PROVENANCE_BACKUP, ["wip", "fixture"]) is True
    assert is_flag_green(PROVENANCE_EXTRA, []) is False
    assert is_flag_green(PROVENANCE_EXTRA, ["wip"]) is False
    # Prototype override replaces green → not green
    assert (
        is_flag_green(
            PROVENANCE_BACKUP,
            [ROLE_PROTOTYPE],
            override_role_ids=[ROLE_PROTOTYPE],
        )
        is False
    )
    # Non-override roles keep green (additive discs beside status)
    assert (
        is_flag_green(
            PROVENANCE_BACKUP,
            [ROLE_PERSONAL, ROLE_FIXTURE],
            override_role_ids=[ROLE_PROTOTYPE],
        )
        is True
    )
    # Override on yellow still not green
    assert (
        is_flag_green(
            PROVENANCE_EXTRA,
            [ROLE_PROTOTYPE],
            override_role_ids=[ROLE_PROTOTYPE],
        )
        is False
    )
