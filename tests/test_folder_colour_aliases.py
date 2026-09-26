"""Folder colour catalog + path aliases (custom colours, migrate v1)."""

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
    PROVENANCE_EXTRA,
    PROVENANCE_WIP,
)
from gcode_index.scanner import scan_backup_tree

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"


def _write_nc(path: Path, ono: str = "O6001") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"%\n{ono} (COLOUR)\nG0\n%\n", encoding="utf-8")
    return path


def test_default_catalog_seeds_three_colours():
    cat = ColourCatalog()
    ids = [c.id for c in cat.colours]
    assert ids[:3] == [PROVENANCE_BACKUP, PROVENANCE_EXTRA, PROVENANCE_WIP]


def test_v1_rules_only_migrates_on_load(tmp_path: Path):
    path = tmp_path / "folder_colour_aliases.yaml"
    # Legacy v1: rules only, colour names green/yellow/red
    save_folder_colour_rules(
        path,
        [
            FolderColourRule(alias="Pawel", colour="red"),
            FolderColourRule(alias="scrap", colour="exclude"),
        ],
    )
    # Force rewrite as v1-looking file (rules only, no colours key)
    path.write_text(
        "rules:\n  - alias: Pawel\n    colour: red\n  - alias: scrap\n    colour: exclude\n",
        encoding="utf-8",
    )
    cat = load_colour_catalog(path)
    assert len(cat.colours) >= 3
    assert {c.id for c in cat.colours} >= {PROVENANCE_BACKUP, PROVENANCE_EXTRA, PROVENANCE_WIP}
    by = {r.alias: r.colour for r in cat.rules}
    assert by["Pawel"] == PROVENANCE_WIP
    assert by["scrap"] == COLOUR_EXCLUDE


def test_custom_colour_roundtrip(tmp_path: Path):
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


def test_custom_colour_applied_in_scan(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "OddMill" / "Q" / "x.nc", "O6101")
    other = _write_nc(bak / "15.09.2026" / "OddMill" / "ok.nc", "O6102")
    am = AliasMap.load(ALIASES)
    colours = FolderColourAliasMap(
        [FolderColourRule(alias="Q", colour="quarantine")],
        known_ids={"quarantine", PROVENANCE_BACKUP},
    )
    result = scan_backup_tree(bak, am, colour_map=colours)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert by[hit.resolve()].provenance == "quarantine"
    assert by[other.resolve()].provenance == PROVENANCE_BACKUP


def test_edited_meaning_persists(tmp_path: Path):
    path = tmp_path / "folder_colour_aliases.yaml"
    cat = ColourCatalog()
    backup = cat.get(PROVENANCE_BACKUP)
    assert backup is not None
    edited = ColourDef(
        id=backup.id,
        label_pl="Na maszynie",
        label_en=backup.label_en,
        swatch=backup.swatch,
        meaning_pl="Zmienione znaczenie",
        meaning_en="Changed meaning",
        badge=backup.badge,
        builtin=True,
    )
    others = [c for c in cat.colours if c.id != PROVENANCE_BACKUP]
    save_colour_catalog(path, ColourCatalog(colours=[edited, *others], rules=[]))
    loaded = load_colour_catalog(path)
    b = loaded.get(PROVENANCE_BACKUP)
    assert b is not None
    assert b.label_pl == "Na maszynie"
    assert b.meaning_pl == "Zmienione znaczenie"
