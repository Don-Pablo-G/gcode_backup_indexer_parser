"""Tests for multi-root scan + green/yellow provenance flags."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.db import open_db, query_instances, write_scan_result
from gcode_index.extra_roots import load_extra_roots, save_extra_roots
from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA
from gcode_index.scanner import scan_backup_tree, scan_with_extra_roots

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"
FIX = Path(__file__).parent / "fixtures" / "synthetic"


def _make_pgm_tree(root: Path, date: str, machine: str) -> Path:
    dest = root / date / machine
    dest.mkdir(parents=True)
    (dest / "DUMP.PGM").write_bytes((FIX / "tiny.pgm").read_bytes())
    return dest


def test_backup_provenance_is_green(tmp_path: Path):
    bak = tmp_path / "bak"
    _make_pgm_tree(bak, "15.09.2026", "VF2S")
    am = AliasMap.load(ALIASES)
    result = scan_backup_tree(bak, am)
    assert result.instances
    assert all(i.provenance == PROVENANCE_BACKUP for i in result.instances)
    assert all(i.scan_root == str(bak.resolve()) for i in result.instances)


def test_extra_root_gets_yellow_flag(tmp_path: Path):
    bak = tmp_path / "bak"
    extra = tmp_path / "shop_nc"
    _make_pgm_tree(bak, "15.09.2026", "VF2S")
    _make_pgm_tree(extra, "01.01.2026", "OddMill")
    am = AliasMap.load(ALIASES)
    result = scan_with_extra_roots(bak, am, extra_roots=[extra])
    greens = [i for i in result.instances if i.provenance == PROVENANCE_BACKUP]
    yellows = [i for i in result.instances if i.provenance == PROVENANCE_EXTRA]
    assert greens
    assert yellows
    assert all(i.scan_root == str(bak.resolve()) for i in greens)
    assert all(i.scan_root == str(extra.resolve()) for i in yellows)

    db = tmp_path / "gcode_index.sqlite"
    conn = open_db(db)
    write_scan_result(conn, backup_root=str(bak), aliases_path=str(ALIASES), result=result)
    conn.commit()
    yellow_rows = query_instances(conn, provenance=PROVENANCE_EXTRA)
    green_rows = query_instances(conn, provenance=PROVENANCE_BACKUP)
    assert yellow_rows
    assert green_rows
    assert all(r["provenance"] == PROVENANCE_EXTRA for r in yellow_rows)
    conn.close()


def test_extra_roots_yaml_roundtrip(tmp_path: Path):
    path = tmp_path / "extra_scan_roots.yaml"
    save_extra_roots(path, [str(tmp_path / "a"), str(tmp_path / "b"), str(tmp_path / "a")])
    loaded = load_extra_roots(path)
    assert loaded == [str(tmp_path / "a"), str(tmp_path / "b")]
