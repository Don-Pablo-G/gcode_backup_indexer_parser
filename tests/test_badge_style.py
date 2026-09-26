"""Windows-safe status/role colour markers (no emoji glyphs)."""

from __future__ import annotations

from gcode_index.badge_style import (
    DOT,
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
    assert status_dot() == DOT == "●"
    assert role_dot("🔴") == "●"
    assert "🟢" not in flag_text(PROVENANCE_BACKUP, ["wip"])
    assert flag_text(PROVENANCE_BACKUP, ["wip", "fixture"]) == "●●●"


def test_flag_tag_prefers_first_role():
    assert flag_tag(PROVENANCE_EXTRA, []) == "flag_extra"
    assert flag_tag(PROVENANCE_BACKUP, ["wip", "fixture"]) == "flag_wip"
