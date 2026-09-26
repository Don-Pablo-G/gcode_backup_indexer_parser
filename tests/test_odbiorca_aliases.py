"""Odbiorca (recipient) catalogue + name aliases."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.odbiorca_aliases import (
    OdbiorcaAliasMap,
    OdbiorcaCatalog,
    OdbiorcaDef,
    OdbiorcaRule,
    load_odbiorca_catalog,
    save_odbiorca_catalog,
)
from gcode_index.folder_tree_map import FolderTreeMap, FolderTreeRule
from gcode_index.models import PROVENANCE_BACKUP
from gcode_index.scanner import scan_backup_tree

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"


def _write_nc(path: Path, ono: str = "O9001") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"%\n{ono} (ODB)\nG0\n%\n", encoding="utf-8")
    return path


def test_odbiorca_catalog_roundtrip(tmp_path: Path):
    path = tmp_path / "odbiorcy.yaml"
    cat = OdbiorcaCatalog(
        odbiorcy=[
            OdbiorcaDef(id="acme", label_pl="Acme", label_en="Acme Ltd"),
        ],
        rules=[OdbiorcaRule(alias="Acme", odbiorca_id="acme", exact=True)],
    )
    save_odbiorca_catalog(path, cat)
    loaded = load_odbiorca_catalog(path)
    assert loaded.get("acme") is not None
    assert loaded.get("acme").label_en == "Acme Ltd"
    assert loaded.rules[0].alias == "Acme"
    assert loaded.rules[0].exact is True


def test_odbiorca_deepest_name_wins(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "Acme" / "x.nc", "O9101")
    am = AliasMap.load(ALIASES)
    odb = OdbiorcaAliasMap(
        [OdbiorcaRule(alias="Acme", odbiorca_id="acme", exact=True)],
        known_ids={"acme"},
    )
    result = scan_backup_tree(bak, am, odbiorca_map=odb)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert by[hit.resolve()].odbiorca_id == "acme"
    assert by[hit.resolve()].provenance == PROVENANCE_BACKUP


def test_odbiorca_path_override(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "VF2S" / "Acme" / "x.nc", "O9201")
    am = AliasMap.load(ALIASES)
    odb = OdbiorcaAliasMap(
        [OdbiorcaRule(alias="Acme", odbiorca_id="acme", exact=True)],
        known_ids={"acme", "other"},
    )
    tree = FolderTreeMap(
        rules=[
            FolderTreeRule(
                path=str((bak / "15.09.2026" / "VF2S" / "Acme").resolve()),
                odbiorca_id="other",
            )
        ]
    )
    result = scan_backup_tree(bak, am, odbiorca_map=odb, tree_map=tree)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    assert by[hit.resolve()].odbiorca_id == "other"


def test_odbiorca_does_not_change_roles_or_status(tmp_path: Path):
    bak = tmp_path / "bak"
    hit = _write_nc(bak / "15.09.2026" / "OddMill" / "Acme" / "x.nc", "O9301")
    am = AliasMap.load(ALIASES)
    from gcode_index.folder_colour_aliases import FolderColourAliasMap, FolderColourRule
    from gcode_index.models import ROLE_PERSONAL

    colours = FolderColourAliasMap(
        [FolderColourRule(alias="Acme", colour=ROLE_PERSONAL, exact=True)]
    )
    odb = OdbiorcaAliasMap(
        [OdbiorcaRule(alias="Acme", odbiorca_id="acme", exact=True)]
    )
    result = scan_backup_tree(bak, am, colour_map=colours, odbiorca_map=odb)
    by = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    inst = by[hit.resolve()]
    assert inst.odbiorca_id == "acme"
    assert inst.role == ROLE_PERSONAL
    assert inst.provenance == PROVENANCE_BACKUP
