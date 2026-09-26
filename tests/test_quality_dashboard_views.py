"""Tests for scan quality dashboard metrics and views.yaml presets."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gcode_index.db import open_db, query_instances, write_scan_result
from gcode_index.models import ProgramInstance, ROLE_SYSTEM_PROGRAMS, ScanResult
from gcode_index.presets import (
    VIEWS_FILENAME,
    FilterPreset,
    load_presets_for_target,
    presets_path_for_target,
    save_presets,
    upsert_preset,
)
from gcode_index.scan_report import load_quality_metrics
from gcode_index.scanner import UNKNOWN_MACHINE_ID, UNKNOWN_MACHINE_LABEL


def _inst(
    *,
    program: str,
    machine: str,
    sha: str,
    path: str,
    label: str | None = None,
    role: str | None = None,
    odbiorca_id: str | None = None,
    provenance: str = "backup",
) -> ProgramInstance:
    return ProgramInstance(
        program_number=program,
        part_number=None,
        machine_id=machine,
        machine_label=label or machine,
        backup_date=datetime(2026, 9, 15, tzinfo=timezone.utc),
        date_source="mtime",
        source_path=path,
        source_type="loose_nc",
        source_size=100,
        content_sha256=sha,
        program_sha256=sha,
        control_family="haas",
        provenance=provenance,
        role=role,
        odbiorca_id=odbiorca_id,
    )


def test_quality_metrics_counts(tmp_path: Path):
    conn = open_db(tmp_path / "idx.sqlite")
    result = ScanResult(
        instances=[
            _inst(
                program="1",
                machine="haas-vf-2",
                sha="a" * 64,
                path="a.nc",
                odbiorca_id="acme",
            ),
            _inst(
                program="2",
                machine=UNKNOWN_MACHINE_ID,
                label=UNKNOWN_MACHINE_LABEL,
                sha="b" * 64,
                path="orphan.nc",
            ),
            _inst(
                program="9001",
                machine="haas-st-20y",
                sha="c" * 64,
                path="sys.nc",
                role=ROLE_SYSTEM_PROGRAMS,
                odbiorca_id="acme",
            ),
            # Same body, different roles → colour conflict
            _inst(
                program="10",
                machine="haas-vf-2",
                sha="d" * 64,
                path="p1.nc",
                role="prototype",
                odbiorca_id="acme",
            ),
            _inst(
                program="10",
                machine="haas-st-20y",
                sha="d" * 64,
                path="p2.nc",
                role="fixture",
                odbiorca_id="acme",
            ),
        ]
    )
    write_scan_result(
        conn, backup_root=str(tmp_path), aliases_path=None, result=result
    )
    metrics = load_quality_metrics(conn)
    assert metrics.total_instances == 5
    assert metrics.unknown_machines == 1
    assert metrics.missing_odbiorca == 1
    assert metrics.system_programs == 1
    assert metrics.colour_conflict_groups >= 1
    conn.close()


def test_query_missing_odbiorca(tmp_path: Path):
    conn = open_db(tmp_path / "idx.sqlite")
    result = ScanResult(
        instances=[
            _inst(
                program="1",
                machine="haas-vf-2",
                sha="a" * 64,
                path="a.nc",
                odbiorca_id="acme",
            ),
            _inst(
                program="2",
                machine="haas-vf-2",
                sha="b" * 64,
                path="b.nc",
            ),
        ]
    )
    write_scan_result(
        conn, backup_root=str(tmp_path), aliases_path=None, result=result
    )
    hits = query_instances(conn, odbiorca="__missing__", limit=20)
    assert len(hits) == 1
    assert hits[0]["program_number"] == "2"
    conn.close()


def test_views_yaml_preferred_over_legacy(tmp_path: Path):
    assert presets_path_for_target(tmp_path).name == VIEWS_FILENAME
    legacy = tmp_path / "filter_presets.yaml"
    save_presets(
        legacy,
        [FilterPreset(name="Legacy only", text="1111", odbiorca="acme")],
    )
    # Force legacy filename content for load fallback
    loaded = load_presets_for_target(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].name == "Legacy only"
    assert loaded[0].odbiorca == "acme"

    upsert_preset(tmp_path, FilterPreset(name="New view", text="2222", role="fixture"))
    assert (tmp_path / VIEWS_FILENAME).is_file()
    loaded2 = load_presets_for_target(tmp_path)
    names = {p.name for p in loaded2}
    assert "New view" in names
    assert "Legacy only" in names  # migrated into views.yaml on upsert
