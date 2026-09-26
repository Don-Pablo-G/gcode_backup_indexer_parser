"""Folder role catalog + path aliases (status is separate from scan roots)."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.folder_colour_aliases import (
    ColourCatalog,
    ColourDef,
    FolderColourAliasMap,
    FolderColourRule,
    load_colour_catalog,
    save_colour_catalog,
    save_folder_colour_rules,
)
from gcode_index.models import (
    COLOUR_EXCLUDE,
    PROVENANCE_BACKUP,
    ROLE_FIXTURE,
    ROLE_PRODUCTION,
    ROLE_SEED_IDS,
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
    assert ids[:5] == list(ROLE_SEED_IDS)
    # Status ids must not appear as roles
    assert PROVENANCE_BACKUP not in ids
    assert "extra" not in ids


def test_v1_rules_only_migrates_on_load(tmp_path: Path):
    path = tmp_path / "folder_colour_aliases.yaml"
    # Legacy: red → wip role; green/yellow rules remap to production/fixture
    path.write_text(
        "rules:\n"
        "  - alias: Pawel\n"
        "    colour: red\n"
        "  - alias: Prod\n"
        "    colour: green\n"
        "  - alias: scrap\n"
        "    colour: exclude\n",
        encoding="utf-8",
    )
    cat = load_colour_catalog(path)
    assert {c.id for c in cat.colours} >= set(ROLE_SEED_IDS)
    by = {r.alias: r.colour for r in cat.rules}
    assert by["Pawel"] == ROLE_WIP
    assert by["Prod"] == ROLE_PRODUCTION
    assert by["scrap"] == COLOUR_EXCLUDE


def test_legacy_status_colours_stripped_from_catalog(tmp_path: Path):
    path = tmp_path / "folder_colour_aliases.yaml"
    path.write_text(
        "colours:\n"
        "  - id: backup\n"
        "    label_pl: Zielona\n"
        "  - id: extra\n"
        "    label_pl: Zolta\n"
        "  - id: wip\n"
        "    label_pl: WIP\n"
        "rules:\n"
        "  - alias: X\n"
        "    colour: backup\n",
        encoding="utf-8",
    )
    cat = load_colour_catalog(path)
    ids = {c.id for c in cat.colours}
    assert "backup" not in ids
    assert "extra" not in ids
    assert ROLE_WIP in ids
    assert ROLE_PRODUCTION in ids
    assert cat.rules[0].colour == ROLE_PRODUCTION  # backup rule → production


def test_custom_role_roundtrip(tmp_path: Path):
    path = tmp_path / "folder_colour_aliases.yaml"
    cat = ColourCatalog(
        colours=list(ColourCatalog().colours)
        + [
            ColourDef(
                id="quarantine",
                label_pl="Kwarantanna",
                label_en="Quarantine",
                swatch="#e67e22",
                meaning_pl="Do sprawdzenia",
                meaning_en="Needs review",
                badge="🟠",
            )
        ],
        rules=[FolderColourRule(alias="Q", colour="quarantine")],
    )
    save_colour_catalog(path, cat)
    loaded = load_colour_catalog(path)
    q = loaded.get("quarantine")
    assert q is not None
    assert q.label_pl == "Kwarantanna"
    assert q.swatch == "#E67E22"
    assert loaded.rules[0].colour == "quarantine"


def test_role_alias_does_not_override_status(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "OddMill" / "Q" / "x.nc", "O6101")
    other = _write_nc(bak / "15.09.2026" / "OddMill" / "ok.nc", "O6102")
    am = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap(
        [FolderColourRule(alias="Q", colour="quarantine")],
        known_ids={"quarantine", ROLE_PRODUCTION},
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
    prod = cat.get(ROLE_PRODUCTION)
    assert prod is not None
    edited = ColourDef(
        id=prod.id,
        label_pl="Seria",
        label_en=prod.label_en,
        swatch=prod.swatch,
        meaning_pl="Zmienione znaczenie",
        meaning_en="Changed meaning",
        badge=prod.badge,
        builtin=True,
    )
    others = [c for c in cat.colours if c.id != ROLE_PRODUCTION]
    save_colour_catalog(path, ColourCatalog(colours=[edited, *others], rules=[]))
    loaded = load_colour_catalog(path)
    b = loaded.get(ROLE_PRODUCTION)
    assert b is not None
    assert b.label_pl == "Seria"
    assert b.meaning_pl == "Zmienione znaczenie"


def test_wip_role_from_alias(tmp_path: Path):
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
