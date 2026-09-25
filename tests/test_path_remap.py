"""Tests for client path-prefix remaps (C: → Z: extract)."""

from __future__ import annotations

from pathlib import Path

from gcode_index.extract import resolve_source_path
from gcode_index.instance_ini import (
    INSTANCE_INI_FILENAME,
    InstanceConfig,
    load_instance_ini,
    save_instance_ini,
)
from gcode_index.path_remap import (
    PathRemap,
    apply_path_remaps,
    normalize_path_key,
    normalize_remaps,
    parse_remap_rules_block,
)
from gcode_index.path_util import resolve_source_abspath


def test_normalize_path_key_case_and_separators():
    assert normalize_path_key(r"C:\Share\Foo") == normalize_path_key("c:/share/foo")
    assert normalize_path_key(r"C:\Share\\") == normalize_path_key(r"c:\share")


def test_apply_remap_drive_letter():
    remaps = [PathRemap(r"C:\CNC\Share", r"Z:\CNC\Share")]
    out = apply_path_remaps(r"C:\CNC\Share\2024\HAAS", remaps)
    assert out.replace("/", "\\").casefold().startswith(r"z:\cnc\share".casefold())
    assert "2024" in out.replace("/", "\\")
    assert "HAAS" in out


def test_apply_remap_case_insensitive_and_slash():
    remaps = [("c:/cnc/share", r"Z:\CNC\Share")]
    out = apply_path_remaps(r"C:\CNC\Share\a.nc", remaps)
    assert out.replace("/", "\\").casefold().startswith(r"z:\cnc\share".casefold())


def test_longest_prefix_wins():
    remaps = normalize_remaps(
        [
            PathRemap(r"C:\Share", r"Z:\Share"),
            PathRemap(r"C:\Share\Deep", r"Y:\Deep"),
        ]
    )
    out = apply_path_remaps(r"C:\Share\Deep\file.nc", remaps)
    assert out.replace("/", "\\").casefold().startswith(r"y:\deep".casefold())


def test_no_partial_folder_name_match():
    remaps = [PathRemap(r"C:\Share", r"Z:\Share")]
    # C:\ShareX must not match C:\Share
    assert apply_path_remaps(r"C:\ShareX\a.nc", remaps) == r"C:\ShareX\a.nc"


def test_resolve_source_path_remaps_scan_root():
    remaps = [PathRemap(r"C:\Bak", r"Z:\Bak")]
    p = resolve_source_path(
        "2024/HAAS/O1.nc",
        backup_root=r"Z:\Other",
        scan_root=r"C:\Bak",
        path_remaps=remaps,
    )
    s = str(p).replace("/", "\\")
    assert s.casefold().startswith(r"z:\bak".casefold())
    assert "O1.nc" in s


def test_resolve_source_abspath_absolute_source():
    remaps = [PathRemap(r"C:\Bak", r"Z:\Bak")]
    p = resolve_source_abspath(
        r"C:\Bak\x.nc",
        backup_root=None,
        scan_root=None,
        path_remaps=remaps,
    )
    assert str(p).replace("/", "\\").casefold().startswith(r"z:\bak".casefold())


def test_parse_remap_rules_block():
    rules = parse_remap_rules_block(
        """
        C:\\A => Z:\\A
        ; comment
        D:/B -> Y:/B
        """
    )
    assert len(rules) == 2
    assert rules[0].from_prefix.endswith("A") or "A" in rules[0].from_prefix


def test_instance_ini_path_remap_roundtrip(tmp_path: Path):
    path = tmp_path / INSTANCE_INI_FILENAME
    cfg = InstanceConfig(
        target=r"Z:\Index",
        path_remaps=[
            PathRemap(r"C:\CNC\Share", r"Z:\CNC\Share"),
            PathRemap(r"C:\Extra", r"Z:\Extra"),
        ],
    )
    save_instance_ini(path, config=cfg)
    text = path.read_text(encoding="utf-8")
    assert "[path_remap]" in text
    assert "from_prefix" in text
    assert r"C:\CNC\Share" in text or "C:\\\\CNC\\\\Share" in text or "C:\\CNC\\Share" in text

    loaded = load_instance_ini(path)
    assert len(loaded.path_remaps) == 2
    assert loaded.path_remaps[0].from_prefix.replace("/", "\\").casefold() == r"c:\cnc\share"
    assert loaded.path_remaps[0].to_prefix.replace("/", "\\").casefold() == r"z:\cnc\share"
