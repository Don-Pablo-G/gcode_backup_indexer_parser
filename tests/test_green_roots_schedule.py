"""Tests for typed green/yellow scan roots and auto-index schedule."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.extra_roots import (
    ScanRootSpec,
    load_extra_roots,
    load_scan_roots,
    normalize_scan_roots,
    save_extra_roots,
    save_scan_roots,
)
from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA
from gcode_index.schedule import (
    SCHEDULE_DAILY,
    SCHEDULE_HOURLY,
    SCHEDULE_OFF,
    is_schedule_due,
    normalize_schedule,
    next_schedule_at,
)
from gcode_index.scanner import scan_with_extra_roots

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"
FIX = Path(__file__).parent / "fixtures" / "synthetic"


def _make_pgm_tree(root: Path, date: str, machine: str) -> Path:
    dest = root / date / machine
    dest.mkdir(parents=True)
    (dest / "DUMP.PGM").write_bytes((FIX / "tiny.pgm").read_bytes())
    return dest


def _make_loose_nc(root: Path, name: str = "O1234.nc") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text("%\nO1234 (CATCH)\nG0\n%\n", encoding="utf-8")
    return path


def test_green_root_specs_yaml_roundtrip(tmp_path: Path):
    path = tmp_path / "extra_scan_roots.yaml"
    save_scan_roots(
        path,
        [
            ScanRootSpec(path=str(tmp_path / "catch"), provenance=PROVENANCE_BACKUP),
            ScanRootSpec(path=str(tmp_path / "other"), provenance=PROVENANCE_EXTRA),
            ScanRootSpec(path=str(tmp_path / "catch"), provenance=PROVENANCE_BACKUP),
        ],
    )
    loaded = load_scan_roots(path)
    assert len(loaded) == 2
    assert loaded[0].provenance == PROVENANCE_BACKUP
    assert loaded[1].provenance == PROVENANCE_EXTRA


def test_legacy_string_roots_still_yellow(tmp_path: Path):
    path = tmp_path / "extra_scan_roots.yaml"
    save_extra_roots(path, [str(tmp_path / "a")])
    loaded = load_scan_roots(path)
    assert loaded[0].provenance == PROVENANCE_EXTRA
    assert load_extra_roots(path) == [str(tmp_path / "a")]


def test_green_root_scan_flags_backup(tmp_path: Path):
    bak = tmp_path / "bak"
    catch = tmp_path / "catch_nc"
    _make_pgm_tree(bak, "15.09.2026", "VF2S")
    _make_loose_nc(catch)
    am = AliasMap.load(ALIASES)
    result = scan_with_extra_roots(
        bak,
        am,
        root_specs=[(catch, PROVENANCE_BACKUP)],
    )
    greens = [i for i in result.instances if i.provenance == PROVENANCE_BACKUP]
    yellows = [i for i in result.instances if i.provenance == PROVENANCE_EXTRA]
    assert yellows == []
    assert any(i.scan_root == str(catch.resolve()) for i in greens)
    assert any(i.program_number in ("1234", "O1234", "01234") or "1234" in (i.program_number or "") for i in greens)


def test_mixed_green_and_yellow_roots(tmp_path: Path):
    bak = tmp_path / "bak"
    green = tmp_path / "green"
    yellow = tmp_path / "yellow"
    _make_pgm_tree(bak, "15.09.2026", "VF2S")
    _make_loose_nc(green, "O2000.nc")
    _make_pgm_tree(yellow, "01.01.2026", "OddMill")
    am = AliasMap.load(ALIASES)
    result = scan_with_extra_roots(
        bak,
        am,
        root_specs=[
            ScanRootSpec(path=str(green), provenance=PROVENANCE_BACKUP),
            ScanRootSpec(path=str(yellow), provenance=PROVENANCE_EXTRA),
        ],
    )
    assert any(
        i.provenance == PROVENANCE_BACKUP and i.scan_root == str(green.resolve())
        for i in result.instances
    )
    assert any(
        i.provenance == PROVENANCE_EXTRA and i.scan_root == str(yellow.resolve())
        for i in result.instances
    )


def test_normalize_scan_roots_skips_backup(tmp_path: Path):
    bak = tmp_path / "bak"
    bak.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    specs = normalize_scan_roots(
        [
            ScanRootSpec(path=str(bak), provenance=PROVENANCE_BACKUP),
            ScanRootSpec(path=str(other), provenance=PROVENANCE_BACKUP),
        ],
        backup_root=str(bak),
    )
    assert len(specs) == 1
    assert specs[0][0].resolve() == other.resolve()


def test_schedule_normalize_and_due():
    assert normalize_schedule("daily") == SCHEDULE_DAILY
    assert normalize_schedule("1h") == SCHEDULE_HOURLY
    assert normalize_schedule("nope") == SCHEDULE_OFF
    now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    assert is_schedule_due(SCHEDULE_HOURLY, None, now=now) is True
    assert (
        is_schedule_due(
            SCHEDULE_HOURLY,
            now - timedelta(minutes=10),
            now=now,
        )
        is False
    )
    assert (
        is_schedule_due(
            SCHEDULE_HOURLY,
            now - timedelta(hours=2),
            now=now,
        )
        is True
    )
    nxt = next_schedule_at(SCHEDULE_DAILY, now - timedelta(hours=1), now=now)
    assert nxt is not None
    assert nxt >= now
