"""Folder role catalog + path aliases (status is separate from scan roots)."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.folder_colour_aliases import (
    COLOUR_PRESET_SWATCHES,
    ColourCatalog,
    ColourDef,
    FolderColourAliasMap,
    FolderColourRule,
    is_status_colour_id,
    load_colour_catalog,
    normalize_colour_id,
    save_colour_catalog,
    save_folder_colour_rules,
)
from gcode_index.models import (
    COLOUR_EXCLUDE,
    PROVENANCE_BACKUP,
    PROVENANCE_EXTRA,
    ROLE_FIXTURE,
    ROLE_PERSONAL,
    ROLE_PRODUCTION,
    ROLE_PROTOTYPE,
    ROLE_SEED_IDS,
    ROLE_SYSTEM_PROGRAMS,
    ROLE_WIP,
)
from gcode_index.scanner import scan_backup_tree

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"


def _write_nc(path: Path, ono: str = "O6001") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"%\n{ono} (COLOUR)\nG0\n%\n", encoding="utf-8")
    return path


def test_default_catalog_seeds_roles():
    cat = ColourCatalog()
    ids = [c.id for c in cat.colours]
    assert ids[:4] == list(ROLE_SEED_IDS)
    by = {c.id: c for c in cat.colours}
    assert by[ROLE_PROTOTYPE].swatch == "#2980B9"  # blue
    assert by[ROLE_PERSONAL].swatch == "#C0392B"  # red
    assert by[ROLE_SYSTEM_PROGRAMS].swatch == "#E67E22"  # orange
    assert by[ROLE_FIXTURE].swatch == "#8E44AD"  # purple
    # Status ids must not appear as roles
    assert PROVENANCE_BACKUP not in ids
    assert PROVENANCE_EXTRA not in ids
    assert "yellow" not in ids
    # Green/yellow not offered as role presets
    assert "#B58900" not in COLOUR_PRESET_SWATCHES
    assert "#1A7F37" not in COLOUR_PRESET_SWATCHES


def test_yellow_never_normalizes_to_fixture():
    """Regression: yellow/extra status must not become the fixture role."""
    assert is_status_colour_id("yellow")
    assert is_status_colour_id("extra")
    assert normalize_colour_id("yellow") == PROVENANCE_EXTRA
    assert normalize_colour_id("extra") == PROVENANCE_EXTRA
    assert normalize_colour_id("yellow") != ROLE_FIXTURE
    assert normalize_colour_id("blue") == ROLE_PROTOTYPE
    assert normalize_colour_id("red") == ROLE_PERSONAL
    assert normalize_colour_id("orange") == ROLE_SYSTEM_PROGRAMS
    assert normalize_colour_id("purple") == ROLE_FIXTURE


def test_v1_rules_only_migrates_on_load(tmp_path: Path):
    path = tmp_path / "folder_colour_aliases.yaml"
    # Legacy: red → personal; green/yellow status rules are dropped (not → fixture)
    path.write_text(
        "rules:\n"
        "  - alias: Pawel\n"
        "    colour: red\n"
        "  - alias: Prod\n"
        "    colour: green\n"
        "  - alias: YellowThing\n"
        "    colour: yellow\n"
        "  - alias: scrap\n"
        "    colour: exclude\n",
        encoding="utf-8",
    )
    cat = load_colour_catalog(path)
    assert {c.id for c in cat.colours} >= set(ROLE_SEED_IDS)
    by = {r.alias: r.colour for r in cat.rules}
    assert by["Pawel"] == ROLE_PERSONAL
    assert "Prod" not in by  # green was status — dropped
    assert "YellowThing" not in by  # yellow must never become fixture
    assert by["scrap"] == COLOUR_EXCLUDE
    assert all(r.colour not in (PROVENANCE_BACKUP, PROVENANCE_EXTRA, "yellow") for r in cat.rules)
    assert ROLE_FIXTURE not in by.values()


def test_legacy_status_colours_stripped_from_catalog(tmp_path: Path):
    path = tmp_path / "folder_colour_aliases.yaml"
    path.write_text(
        "colours:\n"
        "  - id: backup\n"
        "    label_pl: Zielona\n"
        "  - id: extra\n"
        "    label_pl: Zolta\n"
        "    meaning_pl: Przyrząd\n"
        "  - id: wip\n"
        "    label_pl: WIP\n"
        "rules:\n"
        "  - alias: X\n"
        "    colour: backup\n"
        "  - alias: Y\n"
        "    colour: extra\n",
        encoding="utf-8",
    )
    cat = load_colour_catalog(path)
    ids = {c.id for c in cat.colours}
    assert "backup" not in ids
    assert "extra" not in ids
    # Old wip kept as non-builtin custom; new seeds ensured
    wip = cat.get(ROLE_WIP)
    assert wip is not None
    assert wip.builtin is False
    assert ROLE_PROTOTYPE in ids
    assert ROLE_FIXTURE in ids
    assert cat.get(ROLE_FIXTURE).swatch == "#8E44AD"
    # Status rules dropped — never remapped to fixture/production
    assert cat.rules == []


def test_old_seeds_demoted_customs_preserved(tmp_path: Path):
    path = tmp_path / "folder_colour_aliases.yaml"
    path.write_text(
        "colours:\n"
        "  - id: production\n"
        "    label_pl: Seria\n"
        "    swatch: '#1A7F37'\n"
        "    builtin: true\n"
        "  - id: fixture\n"
        "    label_pl: Przyrząd\n"
        "    swatch: '#2980B9'\n"
        "  - id: quarantine\n"
        "    label_pl: Kwarantanna\n"
        "    swatch: '#111111'\n",
        encoding="utf-8",
    )
    cat = load_colour_catalog(path)
    prod = cat.get(ROLE_PRODUCTION)
    assert prod is not None
    assert prod.builtin is False
    assert prod.label_pl == "Seria"
    fix = cat.get(ROLE_FIXTURE)
    assert fix is not None
    assert fix.builtin is True
    assert fix.swatch == "#8E44AD"  # refreshed to purple seed
    q = cat.get("quarantine")
    assert q is not None
    assert q.swatch == "#111111"
    assert q.builtin is False
    assert {c.id for c in cat.colours} >= set(ROLE_SEED_IDS)


def test_custom_role_roundtrip(tmp_path: Path):
    path = tmp_path / "folder_colour_aliases.yaml"
    cat = ColourCatalog(
        colours=list(ColourCatalog().colours)
        + [
            ColourDef(
                id="quarantine",
                label_pl="Kwarantanna",
                label_en="Quarantine",
                swatch="#16A085",
                meaning_pl="Do sprawdzenia",
                meaning_en="Needs review",
                badge="●",
            )
        ],
        rules=[FolderColourRule(alias="Q", colour="quarantine")],
    )
    save_colour_catalog(path, cat)
    loaded = load_colour_catalog(path)
    q = loaded.get("quarantine")
    assert q is not None
    assert q.label_pl == "Kwarantanna"
    assert q.swatch == "#16A085"
    assert loaded.rules[0].colour == "quarantine"


def test_role_alias_does_not_override_status(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "OddMill" / "Q" / "x.nc", "O6101")
    other = _write_nc(bak / "15.09.2026" / "OddMill" / "ok.nc", "O6102")
    am = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap(
        [FolderColourRule(alias="Q", colour="quarantine")],
        known_ids={"quarantine", ROLE_PROTOTYPE},
    )
    result = scan_backup_tree(bak, am, colour_map=colours)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    # Status stays on-machine (backup); role set from alias
    assert by[hit.resolve()].provenance == PROVENANCE_BACKUP
    assert by[hit.resolve()].role == "quarantine"
    assert by[other.resolve()].provenance == PROVENANCE_BACKUP
    assert by[other.resolve()].role is None


def test_edited_role_meaning_persists(tmp_path: Path):
    path = tmp_path / "folder_colour_aliases.yaml"
    cat = ColourCatalog()
    proto = cat.get(ROLE_PROTOTYPE)
    assert proto is not None
    edited = ColourDef(
        id=proto.id,
        label_pl="Roboczy",
        label_en=proto.label_en,
        swatch=proto.swatch,
        meaning_pl="Zmienione znaczenie",
        meaning_en="Changed meaning",
        badge=proto.badge,
        builtin=True,
    )
    others = [c for c in cat.colours if c.id != ROLE_PROTOTYPE]
    save_colour_catalog(path, ColourCatalog(colours=[edited, *others], rules=[]))
    loaded = load_colour_catalog(path)
    b = loaded.get(ROLE_PROTOTYPE)
    assert b is not None
    assert b.label_pl == "Roboczy"
    assert b.meaning_pl == "Zmienione znaczenie"
    assert b.swatch == "#2980B9"


def test_wip_role_from_alias_still_works(tmp_path: Path):
    """Legacy wip id remains valid for existing DB rows / aliases."""
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "OddMill" / "Pawel" / "x.nc", "O6201")
    am = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap([FolderColourRule(alias="Pawel", colour="wip")])
    result = scan_backup_tree(bak, am, colour_map=colours)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert by[hit.resolve()].provenance == PROVENANCE_BACKUP
    assert by[hit.resolve()].role == ROLE_WIP
