"""Tests for folder→machine map."""

from __future__ import annotations

from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.folder_map import (
    FolderMachineMap,
    discover_machine_folders,
    parse_machine_display,
    partition_folders,
    suggest_assignments,
)
from gcode_index.scanner import scan_backup_tree

ALIASES = Path(__file__).resolve().parents[1] / "aliases.yaml"
FIX = Path(__file__).parent / "fixtures" / "synthetic"


def test_discover_and_suggest(tmp_path: Path):
    root = tmp_path / "bak"
    (root / "15.09.2026" / "VF2S").mkdir(parents=True)
    (root / "15.09.2026" / "OddName").mkdir(parents=True)
    (root / "16.09.2026" / "VF2S").mkdir(parents=True)
    names = discover_machine_folders(root)
    assert names == ["OddName", "VF2S"] or set(names) == {"OddName", "VF2S"}
    am = AliasMap.load(ALIASES)
    suggested = suggest_assignments(names, am)
    assert suggested.get("VF2S").machine_id == "haas-vf-2"
    assert suggested.get("OddName").machine_id == "unknown"


def test_partition_skips_auto_matched(tmp_path: Path):
    root = tmp_path / "bak"
    (root / "15.09.2026" / "VF2S").mkdir(parents=True)
    (root / "15.09.2026" / "OddName").mkdir(parents=True)
    (root / "15.09.2026" / "UMC750").mkdir(parents=True)
    am = AliasMap.load(ALIASES)
    part = partition_folders(discover_machine_folders(root), am)
    assert part.manual_count == 1
    assert part.needs_manual == ["OddName"]
    auto_names = {n for n, _ in part.auto_matched}
    assert "VF2S" in auto_names
    assert "UMC750" in auto_names


def test_partition_respects_existing_map(tmp_path: Path):
    am = AliasMap.load(ALIASES)
    existing = FolderMachineMap()
    existing.set("OddMill", "haas-vf-2", "HAAS VF-2")
    part = partition_folders(["OddMill", "Mystery"], am, existing)
    assert part.needs_manual == ["Mystery"]
    assert len(part.previously_mapped) == 1
    assert part.previously_mapped[0][0] == "OddMill"


def test_folder_map_roundtrip(tmp_path: Path):
    m = FolderMachineMap()
    m.backup_root = "/bak"
    m.set("VF2S", "haas-vf-2", "HAAS VF-2")
    m.set("OddName", "haas-umc750", "HAAS UMC750")
    path = tmp_path / "machine_folders.yaml"
    m.save(path)
    loaded = FolderMachineMap.load(path)
    assert loaded.get("VF2S").machine_id == "haas-vf-2"
    assert loaded.get("vf2s").machine_id == "haas-vf-2"  # normalize match
    assert loaded.get("OddName").machine_id == "haas-umc750"


def test_map_overrides_alias_on_scan(tmp_path: Path):
    """Odd folder with .pgm becomes haas-vf-2 when map says so."""
    root = tmp_path / "bak"
    dest = root / "15.09.2026" / "OddMill"
    dest.mkdir(parents=True)
    (dest / "DUMP.PGM").write_bytes((FIX / "tiny.pgm").read_bytes())
    am = AliasMap.load(ALIASES)

    bare = scan_backup_tree(root, am)
    assert all(i.machine_id == "unknown" for i in bare.instances if "DUMP.PGM" in i.source_path)

    fmap = FolderMachineMap()
    fmap.set("OddMill", "haas-vf-2", "HAAS VF-2")
    mapped = scan_backup_tree(root, am, folder_map=fmap)
    hits = [i for i in mapped.instances if "DUMP.PGM" in i.source_path]
    assert hits
    assert all(i.machine_id == "haas-vf-2" for i in hits)
    assert all(i.machine_label == "HAAS VF-2" for i in hits)


def test_parse_machine_display():
    mid, label = parse_machine_display("HAAS VF-2 (haas-vf-2)")
    assert mid == "haas-vf-2"
    assert label == "HAAS VF-2"
    mid2, lab2 = parse_machine_display("MACHINE UNKNOWN (unknown)")
    assert mid2 == "unknown"
