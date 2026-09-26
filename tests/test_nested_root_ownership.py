"""Longest-prefix ownership for nested green/yellow scan roots."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA
from gcode_index.scanner import (
    owning_scan_root,
    roots_nest,
    scan_with_extra_roots,
)

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"


def _write_nc(path: Path, ono: str = "O1001") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"%\n{ono} (NEST)\nG0\n%\n", encoding="utf-8")
    return path


def test_roots_nest_detects_parent_child(tmp_path: Path):
    parent = tmp_path / "share"
    child = parent / "catch"
    child.mkdir(parents=True)
    assert roots_nest(parent, child)
    assert roots_nest(child, parent)
    sibling = tmp_path / "other"
    sibling.mkdir()
    assert not roots_nest(parent, sibling)


def test_owning_scan_root_prefers_deeper(tmp_path: Path):
    parent = (tmp_path / "yellow_parent").resolve()
    child = (parent / "green_child").resolve()
    child.mkdir(parents=True)
    f = _write_nc(child / "O1001.nc")
    roots = [
        (parent, PROVENANCE_EXTRA),
        (child, PROVENANCE_BACKUP),
    ]
    owner = owning_scan_root(f, roots)
    assert owner is not None
    assert owner[0] == child
    assert owner[1] == PROVENANCE_BACKUP


def test_nested_green_child_inside_yellow_parent(tmp_path: Path):
    """Parent yellow + child green → child files green only; outside child yellow."""
    bak = tmp_path / "bak"
    bak.mkdir()
    parent = tmp_path / "yellow_parent"
    child = parent / "green_child"
    outside = _write_nc(parent / "loose_out.nc", "O2001")
    inside = _write_nc(child / "loose_in.nc", "O2002")
    am = AliasMap.load(ALIASES)
    result = scan_with_extra_roots(
        bak,
        am,
        root_specs=[
            (parent, PROVENANCE_EXTRA),
            (child, PROVENANCE_BACKUP),
        ],
    )
    by_abs = {
        (Path(i.scan_root or "") / i.source_path).resolve(): i
        for i in result.instances
    }
    # No duplicates for the nested file
    assert sum(1 for p in by_abs if p == inside.resolve()) == 1
    assert sum(1 for p in by_abs if p == outside.resolve()) == 1

    inside_inst = by_abs[inside.resolve()]
    outside_inst = by_abs[outside.resolve()]
    assert inside_inst.provenance == PROVENANCE_BACKUP
    assert inside_inst.scan_root == str(child.resolve())
    assert outside_inst.provenance == PROVENANCE_EXTRA
    assert outside_inst.scan_root == str(parent.resolve())


def test_nested_yellow_child_inside_green_parent(tmp_path: Path):
    bak = tmp_path / "bak"
    bak.mkdir()
    parent = tmp_path / "green_parent"
    child = parent / "yellow_child"
    _write_nc(parent / "out.nc", "O3001")
    inside = _write_nc(child / "in.nc", "O3002")
    am = AliasMap.load(ALIASES)
    result = scan_with_extra_roots(
        bak,
        am,
        root_specs=[
            (parent, PROVENANCE_BACKUP),
            (child, PROVENANCE_EXTRA),
        ],
    )
    inside_rows = [
        i
        for i in result.instances
        if (Path(i.scan_root or "") / i.source_path).resolve() == inside.resolve()
    ]
    assert len(inside_rows) == 1
    assert inside_rows[0].provenance == PROVENANCE_EXTRA
    assert inside_rows[0].scan_root == str(child.resolve())


def test_nested_extra_inside_main_backup(tmp_path: Path):
    """Yellow catch folder under main backup → deepest (yellow) owns those files."""
    bak = tmp_path / "bak"
    catch = bak / "catch_nc"
    _write_nc(bak / "15.09.2026" / "OddMill" / "O4001.nc", "O4001")
    nested = _write_nc(catch / "O4002.nc", "O4002")
    am = AliasMap.load(ALIASES)
    result = scan_with_extra_roots(
        bak,
        am,
        root_specs=[(catch, PROVENANCE_EXTRA)],
    )
    nested_rows = [
        i
        for i in result.instances
        if (Path(i.scan_root or "") / i.source_path).resolve() == nested.resolve()
    ]
    assert len(nested_rows) == 1
    assert nested_rows[0].provenance == PROVENANCE_EXTRA
    assert nested_rows[0].scan_root == str(catch.resolve())
    # Backup still has its own file(s), not duplicated as yellow
    bak_rows = [
        i for i in result.instances if i.scan_root == str(bak.resolve())
    ]
    assert bak_rows
    assert all(i.provenance == PROVENANCE_BACKUP for i in bak_rows)
