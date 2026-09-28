"""Header scan depth for teach-list paren comments (ini-only; auto-match O-line)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gcode_index.header_match import (
    match_machine_from_header,
    match_roles_from_header,
)
from gcode_index.header_token_freq import collect_header_token_frequencies
from gcode_index.i18n import t
from gcode_index.instance_ini import InstanceConfig, load_instance_ini, save_instance_ini
from gcode_index.models import ProgramInstance
from gcode_index.odbiorca_aliases import (
    DEFAULT_HEADER_SCAN_DEPTH,
    MAX_HEADER_SCAN_DEPTH,
    MIN_HEADER_SCAN_DEPTH,
    OdbiorcaAliasMap,
    OdbiorcaRule,
    clamp_header_scan_depth,
    extract_header_paren_comments,
    extract_header_paren_comments_for_teach,
    match_odbiorca_from_header,
)
from gcode_index.aliases import AliasMap
from gcode_index.folder_colour_aliases import FolderColourAliasMap, FolderColourRule


SAMPLE = """\
%
O9001 (VF2S) (PROTO)
(Pawel)
(material stal)
%
(G00 after percent)
"""


def _write(tmp: Path, name: str, body: str) -> Path:
    p = tmp / name
    p.write_text(body, encoding="utf-8")
    return p


def _inst(tmp: Path, *, body: str, name: str = "p.nc") -> ProgramInstance:
    _write(tmp, name, body)
    return ProgramInstance(
        program_number="9001",
        part_number=None,
        machine_id="unknown",
        backup_date=datetime.now(timezone.utc),
        date_source="mtime",
        source_path=name,
        source_type="loose_nc",
        scan_root=str(tmp),
    )


def test_clamp_header_scan_depth():
    assert clamp_header_scan_depth(None) == DEFAULT_HEADER_SCAN_DEPTH
    assert clamp_header_scan_depth("") == DEFAULT_HEADER_SCAN_DEPTH
    assert clamp_header_scan_depth("nope") == DEFAULT_HEADER_SCAN_DEPTH
    assert clamp_header_scan_depth(0) == MIN_HEADER_SCAN_DEPTH
    assert clamp_header_scan_depth(-3) == MIN_HEADER_SCAN_DEPTH
    assert clamp_header_scan_depth(1) == 1
    assert clamp_header_scan_depth(3) == 3
    assert clamp_header_scan_depth(99) == MAX_HEADER_SCAN_DEPTH
    assert clamp_header_scan_depth("2.7") == 2


def test_teach_depth_collects_and_stops_at_percent(tmp_path: Path):
    nc = _write(tmp_path, "a.nc", SAMPLE)
    assert extract_header_paren_comments(nc) == ["VF2S", "PROTO"]
    assert extract_header_paren_comments_for_teach(nc, depth=1) == ["VF2S", "PROTO"]
    assert extract_header_paren_comments_for_teach(nc, depth=2) == [
        "VF2S",
        "PROTO",
        "Pawel",
    ]
    assert extract_header_paren_comments_for_teach(nc, depth=3) == [
        "VF2S",
        "PROTO",
        "Pawel",
        "material stal",
    ]
    # Depth 4+ still stops before % — never takes (G00 after percent)
    assert extract_header_paren_comments_for_teach(nc, depth=4) == [
        "VF2S",
        "PROTO",
        "Pawel",
        "material stal",
    ]
    assert extract_header_paren_comments_for_teach(nc, depth=20) == [
        "VF2S",
        "PROTO",
        "Pawel",
        "material stal",
    ]


def test_auto_match_stays_o_line_only(tmp_path: Path):
    nc = _write(tmp_path, "b.nc", SAMPLE)
    odb = OdbiorcaAliasMap(
        [OdbiorcaRule(alias="Pawel", odbiorca_id="pawel", exact=True)]
    )
    colours = FolderColourAliasMap(
        [FolderColourRule(alias="PROTO", colour="prototype", exact=True)]
    )
    machines = AliasMap(
        {"vf2s": {"machine_id": "haas-vf-2", "label": "VF-2SS"}}
    )
    # Pawel is on line after O — odbiorca auto-match must miss it
    assert match_odbiorca_from_header(nc, odb) is None
    assert match_roles_from_header(nc, colours) == {"prototype": "PROTO"}
    hit = match_machine_from_header(nc, machines)
    assert hit is not None
    assert hit[0] == "haas-vf-2"


def test_glued_byte_start_no_bleed(tmp_path: Path):
    glued = (
        "%\n"
        "O1000 (FIRST) (AAA)\n"
        "(ShouldNotBleed)\n"
        "%\n"
        "O2000 (SECOND) (BBB)\n"
        "(TeachDepth)\n"
        "%\n"
    )
    nc = _write(tmp_path, "glued.nc", glued)
    byte_b = glued.index("O2000")
    assert extract_header_paren_comments(nc, byte_start=byte_b) == ["SECOND", "BBB"]
    assert extract_header_paren_comments_for_teach(
        nc, byte_start=byte_b, depth=2
    ) == ["SECOND", "BBB", "TeachDepth"]
    # Must not pull FIRST/AAA or ShouldNotBleed from the prior instance
    depth3 = extract_header_paren_comments_for_teach(
        nc, byte_start=byte_b, depth=3
    )
    assert "FIRST" not in depth3
    assert "AAA" not in depth3
    assert "ShouldNotBleed" not in depth3


def test_collect_frequencies_respects_depth(tmp_path: Path):
    inst = _inst(tmp_path, body=SAMPLE)
    shallow = collect_header_token_frequencies([inst], depth=1)
    deep = collect_header_token_frequencies([inst], depth=3)
    shallow_keys = {e.key for e in shallow}
    deep_keys = {e.key for e in deep}
    assert "vf2s" in shallow_keys and "proto" in shallow_keys
    assert "pawel" not in shallow_keys
    assert "pawel" in deep_keys
    assert "material" in deep_keys or "stal" in deep_keys
    assert "g00" not in deep_keys  # after %


def test_instance_ini_default_missing_and_clamp(tmp_path: Path):
    assert InstanceConfig().header_scan_depth == 1

    path = tmp_path / "gcode-index.ini"
    path.write_text(
        "[folders]\nbackup = /bak\ntarget = /db\n\n"
        "[scan]\nincremental = yes\n",
        encoding="utf-8",
    )
    loaded = load_instance_ini(path)
    assert loaded.header_scan_depth == 1

    path.write_text(
        "[folders]\nbackup = /bak\ntarget = /db\n\n"
        "[scan]\nheader_scan_depth = 5\n",
        encoding="utf-8",
    )
    assert load_instance_ini(path).header_scan_depth == 5

    path.write_text(
        "[folders]\nbackup = /bak\ntarget = /db\n\n"
        "[scan]\nheader_scan_depth = 99\n",
        encoding="utf-8",
    )
    assert load_instance_ini(path).header_scan_depth == MAX_HEADER_SCAN_DEPTH

    path.write_text(
        "[folders]\nbackup = /bak\ntarget = /db\n\n"
        "[scan]\nheader_scan_depth = 0\n",
        encoding="utf-8",
    )
    assert load_instance_ini(path).header_scan_depth == MIN_HEADER_SCAN_DEPTH


def test_instance_ini_roundtrip_header_scan_depth(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    cfg = InstanceConfig(backup="/bak", target="/db", header_scan_depth=3)
    save_instance_ini(path, config=cfg)
    text = path.read_text(encoding="utf-8")
    assert "header_scan_depth = 3" in text
    loaded = load_instance_ini(path)
    assert loaded.header_scan_depth == 3
    # Pack yaml must not grow this key (ini-only policy).
    from gcode_index.indexer_settings import IndexerSettings

    assert not hasattr(IndexerSettings(), "header_scan_depth")


def test_i18n_header_scan_depth_pl_en():
    assert "Głębokość" in t("pl", "header_scan_depth")
    assert "Header scan depth" in t("en", "header_scan_depth")
    assert "header_scan_depth" in t("pl", "header_scan_depth_hint")
    assert "teach" in t("en", "header_scan_depth_hint").casefold() or "token" in t(
        "en", "header_scan_depth_hint"
    ).casefold()
