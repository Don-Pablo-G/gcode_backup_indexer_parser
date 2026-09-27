"""Unit tests for Work Flag-column reason reconstruction."""

from __future__ import annotations

from pathlib import Path

from gcode_index.folder_colour_aliases import (
    ColourCatalog,
    ColourDef,
    FolderColourAliasMap,
    FolderColourRule,
)
from gcode_index.folder_tree_map import FolderTreeMap, FolderTreeRule
from gcode_index.models import (
    PROVENANCE_BACKUP,
    PROVENANCE_EXTRA,
    ROLE_FIXTURE,
    ROLE_PERSONAL,
    ROLE_PROTOTYPE,
    ROLE_SYSTEM_PROGRAMS,
)
from gcode_index.role_explain import (
    REASON_ALIAS,
    REASON_ALIAS_FUZZY,
    REASON_O9,
    REASON_PATH,
    REASON_UNAVAILABLE,
    explain_row_roles,
    format_flag_tooltip,
    format_o9_display,
    path_tail,
)


def test_match_segment_rule_returns_alias_and_fuzzy():
    exact_map = FolderColourAliasMap(
        [FolderColourRule(alias="Pawel", colour=ROLE_PERSONAL, exact=True)]
    )
    rule = exact_map.match_segment_rule("Pawel")
    assert rule is not None
    assert rule.alias == "Pawel"
    assert rule.colour == ROLE_PERSONAL
    assert exact_map.match_segment("Pawel") == ROLE_PERSONAL
    assert exact_map.match_segment_rule("PawelX") is None  # exact-only

    fuzzy_map = FolderColourAliasMap(
        [FolderColourRule(alias="Fix", colour=ROLE_FIXTURE, exact=False)]
    )
    fr = fuzzy_map.match_segment_rule("Fixture")
    assert fr is not None
    assert fr.alias == "Fix"
    assert fuzzy_map.match_segment("Fixture") == ROLE_FIXTURE


def test_explain_name_aliases_exact_and_fuzzy():
    cmap = FolderColourAliasMap(
        [
            FolderColourRule(alias="Pawel", colour=ROLE_PERSONAL, exact=True),
            FolderColourRule(alias="UCHWYT", colour=ROLE_FIXTURE, exact=False),
        ]
    )
    reasons = explain_row_roles(
        source_path="2024-03-01/VF2/Pawel/UCHWYTY/prog.nc",
        scan_root="/backup",
        program_number="1234",
        role_csv=f"{ROLE_FIXTURE},{ROLE_PERSONAL}",
        colour_map=cmap,
        tree_map=FolderTreeMap(),
        o9_enabled=True,
    )
    by_id = {r.role_id: r for r in reasons}
    assert by_id[ROLE_PERSONAL].reason_kind == REASON_ALIAS
    assert by_id[ROLE_PERSONAL].detail == "Pawel"
    assert by_id[ROLE_FIXTURE].reason_kind == REASON_ALIAS_FUZZY
    assert by_id[ROLE_FIXTURE].detail == "UCHWYT"


def test_explain_tree_path_replaces_name_union(tmp_path: Path):
    folder = tmp_path / "2024-03-01" / "VF2" / "PROTO"
    folder.mkdir(parents=True)
    cmap = FolderColourAliasMap(
        [FolderColourRule(alias="Pawel", colour=ROLE_PERSONAL, exact=True)]
    )
    # Name alias would have given personal; tree tags replace with prototype.
    tm = FolderTreeMap(
        rules=[
            FolderTreeRule(path=str(folder), tags=[ROLE_PROTOTYPE]),
        ]
    )
    rel = "2024-03-01/VF2/PROTO/Pawel/prog.nc"
    reasons = explain_row_roles(
        source_path=rel,
        scan_root=str(tmp_path),
        program_number="100",
        role_csv=ROLE_PROTOTYPE,
        colour_map=cmap,
        tree_map=tm,
        o9_enabled=True,
    )
    assert len(reasons) == 1
    assert reasons[0].role_id == ROLE_PROTOTYPE
    assert reasons[0].reason_kind == REASON_PATH
    assert "PROTO" in reasons[0].detail


def test_explain_o9_accumulates_after_tree(tmp_path: Path):
    folder = tmp_path / "sys"
    folder.mkdir()
    tm = FolderTreeMap(
        rules=[FolderTreeRule(path=str(folder), tags=[ROLE_PROTOTYPE])]
    )
    reasons = explain_row_roles(
        source_path="sys/O9005.nc",
        scan_root=str(tmp_path),
        program_number="O9005",
        role_csv=f"{ROLE_PROTOTYPE},{ROLE_SYSTEM_PROGRAMS}",
        colour_map=FolderColourAliasMap.empty(),
        tree_map=tm,
        o9_enabled=True,
    )
    by_id = {r.role_id: r for r in reasons}
    assert by_id[ROLE_PROTOTYPE].reason_kind == REASON_PATH
    assert by_id[ROLE_SYSTEM_PROGRAMS].reason_kind == REASON_O9
    assert by_id[ROLE_SYSTEM_PROGRAMS].o9_number == "O9005"


def test_explain_stale_role_unavailable():
    reasons = explain_row_roles(
        source_path="plain/prog.nc",
        scan_root="/backup",
        program_number="1",
        role_csv=ROLE_PERSONAL,
        colour_map=FolderColourAliasMap.empty(),
        tree_map=FolderTreeMap(),
        o9_enabled=True,
    )
    assert len(reasons) == 1
    assert reasons[0].reason_kind == REASON_UNAVAILABLE


def test_explain_o9_disabled_leaves_stale_system():
    reasons = explain_row_roles(
        source_path="plain/prog.nc",
        scan_root="/backup",
        program_number="O9001",
        role_csv=ROLE_SYSTEM_PROGRAMS,
        colour_map=FolderColourAliasMap.empty(),
        tree_map=FolderTreeMap(),
        o9_enabled=False,
    )
    assert reasons[0].reason_kind == REASON_UNAVAILABLE


def test_format_flag_tooltip_pl_status_and_empty():
    catalog = ColourCatalog()
    text = format_flag_tooltip(
        provenance=PROVENANCE_BACKUP,
        source_path="a/b.nc",
        scan_root="/r",
        program_number="1",
        role_csv=None,
        catalog=catalog,
        lang="pl",
    )
    assert "Flaga:" in text
    assert "Na maszynie" in text
    assert "Funkcje:" in text
    assert "Brak funkcji" in text


def test_format_flag_tooltip_override_and_unavailable_en():
    catalog = ColourCatalog(
        colours=[
            ColourDef(
                id=ROLE_PROTOTYPE,
                label_pl="Prototyp",
                label_en="Prototype",
                can_override_main_state_colour=True,
            )
        ],
        rules=[FolderColourRule(alias="PROTO", colour=ROLE_PROTOTYPE, exact=True)],
    )
    text = format_flag_tooltip(
        provenance=PROVENANCE_EXTRA,
        source_path="PROTO/prog.nc",
        scan_root="/r",
        program_number="2",
        role_csv=f"{ROLE_PROTOTYPE},{ROLE_PERSONAL}",
        catalog=catalog,
        colour_map=catalog.alias_map(),
        lang="en",
    )
    assert "Flag:" in text
    assert "Prototype" in text
    assert "overrides status" in text
    assert "Functions:" in text
    assert "reason unavailable (re-scan?)" in text


def test_format_flag_tooltip_yellow_no_roles_en():
    text = format_flag_tooltip(
        provenance=PROVENANCE_EXTRA,
        source_path="x.nc",
        scan_root="/r",
        program_number="1",
        role_csv="",
        catalog=ColourCatalog(),
        lang="en",
    )
    assert "Status unknown" in text
    assert "No functions" in text


def test_path_tail_and_o9_display():
    assert path_tail("a/b/c/d/e") == "…/c/d/e"
    assert path_tail("a/b") == "a/b"
    assert format_o9_display("O9005") == "O9005"
    assert format_o9_display("9001") == "O9001"
