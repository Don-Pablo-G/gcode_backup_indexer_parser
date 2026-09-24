"""Tests for O-number search normalize (#20) and filter presets (#2)."""

from __future__ import annotations

from pathlib import Path

from gcode_index.db import (
    is_program_number_query,
    open_db,
    program_digit_core,
    program_search_variants,
    query_instances,
    rank_match,
)
from gcode_index.presets import (
    FilterPreset,
    delete_preset,
    get_preset,
    load_presets,
    presets_path_for_target,
    save_presets,
    upsert_preset,
)


def test_program_digit_core_and_variants():
    assert program_digit_core("O03232") == "3232"
    assert program_digit_core("03232") == "3232"
    assert program_digit_core("3232") == "3232"
    assert program_digit_core("O00001") == "1"
    assert program_digit_core("00000") == "0"
    assert program_digit_core("P-00253") is None
    assert is_program_number_query("O03232")
    assert is_program_number_query("1234")
    assert not is_program_number_query("P-00253232 VA")
    variants = program_search_variants("O03232")
    assert "03232" in variants
    assert "3232" in variants
    assert "o03232" in variants


def test_search_o_prefix_and_padding(tmp_path: Path):
    conn = open_db(tmp_path / "idx.sqlite")
    conn.execute(
        """
        INSERT INTO index_runs (run_id, started_at, backup_root, indexer_version)
        VALUES ('r1', '2026-01-01T00:00:00+00:00', '/bak', '0.2.23')
        """
    )
    rows = [
        ("a", "03232", "haas-vf-2"),
        ("b", "9278", "haas-st-20y"),
        ("c", "00001", "haas-sl-20"),
        ("d", "O9999", "noise"),  # unlikely storage, still searchable
    ]
    for iid, prog, machine in rows:
        conn.execute(
            """
            INSERT INTO program_instances (
              instance_id, program_number, part_number, machine_id,
              backup_date, file_ctime, date_source, source_path, source_type,
              indexed_at, run_id
            ) VALUES (?, ?, NULL, ?, '2026-09-15T00:00:00+00:00',
                      '2026-09-15T00:00:00+00:00', 'birth', 'x.nc', 'loose_nc',
                      '2026-09-15T00:00:00+00:00', 'r1')
            """,
            (iid, prog, machine),
        )
    conn.commit()

    # Typing what you see on the control (with O)
    hits = query_instances(conn, text="O03232", limit=20)
    assert any(r["instance_id"] == "a" for r in hits)

    # Filename-style unpadded vs padded header
    hits_pad = query_instances(conn, text="O09278", limit=20)
    assert any(r["instance_id"] == "b" for r in hits_pad)
    hits_short = query_instances(conn, text="09278", limit=20)
    assert any(r["instance_id"] == "b" for r in hits_short)

    # Leading zeros
    hits1 = query_instances(conn, text="O00001", limit=20)
    assert any(r["instance_id"] == "c" for r in hits1)
    assert rank_match("03232", None, "O03232") == 0
    assert rank_match("03232", None, "3232") == 0
    # Non-program query unchanged — part-style still works via literal
    assert not is_program_number_query("P-00253232")
    conn.close()


def test_filter_presets_roundtrip(tmp_path: Path):
    path = presets_path_for_target(tmp_path)
    assert path.name == "filter_presets.yaml"
    assert load_presets(path) == []

    a = FilterPreset(
        name="UMC week",
        text="3232",
        machines=["HAAS UMC750 (haas-umc750)"],
        date_from="01.09.2026",
        date_to="15.09.2026",
        source_type="loose_nc",
        control="haas",
        provenance="green — backup (ran)",
        programmer="PG1",
        newest_only=True,
    )
    upsert_preset(path, a)
    loaded = load_presets(path)
    assert len(loaded) == 1
    assert loaded[0].name == "UMC week"
    assert loaded[0].newest_only is True
    assert loaded[0].machines == ["HAAS UMC750 (haas-umc750)"]

    # Replace same name (case-insensitive)
    b = FilterPreset(name="umc week", text="9999", newest_only=False)
    upsert_preset(path, b)
    loaded = load_presets(path)
    assert len(loaded) == 1
    assert loaded[0].text == "9999"
    assert get_preset(path, "UMC WEEK") is not None

    delete_preset(path, "umc week")
    assert load_presets(path) == []

    save_presets(path, [a, FilterPreset(name="Yellow extras", provenance="yellow — extra (not run)")])
    names = {p.name for p in load_presets(path)}
    assert names == {"UMC week", "Yellow extras"}
