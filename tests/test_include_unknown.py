"""Include-UNKNOWN sticky filter (default ON) + floor lock."""

from __future__ import annotations

from pathlib import Path

from gcode_index.db import open_db, query_instances
from gcode_index.i18n import t
from gcode_index.instance_ini import load_instance_ini, save_instance_ini


def _seed(tmp_path: Path):
    conn = open_db(tmp_path / "idx.sqlite")
    conn.execute(
        """
        INSERT INTO index_runs (run_id, started_at, backup_root, indexer_version)
        VALUES ('r1', '2026-01-01T00:00:00+00:00', '/bak', '0.2.57')
        """
    )
    rows = [
        ("vf", "O1", "haas-vf-2", "HAAS VF-2"),
        ("umc", "O2", "haas-umc750", "HAAS UMC750"),
        ("unk", "O3", "unknown", "MACHINE UNKNOWN"),
        ("unmap", "O4", "unmapped:OddFolder", "MACHINE UNKNOWN"),
    ]
    for iid, prog, mid, label in rows:
        conn.execute(
            """
            INSERT INTO program_instances (
              instance_id, program_number, part_number, machine_id, machine_label,
              backup_date, file_ctime, date_source, source_path, source_type,
              indexed_at, run_id
            ) VALUES (?, ?, NULL, ?, ?, '2026-01-01T00:00:00+00:00',
                      '2026-01-01T00:00:00+00:00', 'birth',
                      'x.nc', 'loose_nc', '2026-01-01T00:00:00+00:00', 'r1')
            """,
            (iid, prog, mid, label),
        )
    conn.commit()
    return conn


def test_include_unknown_keeps_unassigned_when_filtering(tmp_path: Path):
    conn = _seed(tmp_path)
    try:
        only_vf = query_instances(
            conn, machines=["haas-vf-2"], include_unknown=False, limit=50
        )
        assert {r["instance_id"] for r in only_vf} == {"vf"}

        with_unk = query_instances(
            conn, machines=["haas-vf-2"], include_unknown=True, limit=50
        )
        assert {r["instance_id"] for r in with_unk} == {"vf", "unk", "unmap"}

        # No machine filter → include_unknown has no effect (all rows)
        all_rows = query_instances(conn, include_unknown=True, limit=50)
        assert len(all_rows) == 4
    finally:
        conn.close()


def test_include_unknown_ini_default_yes(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    save_instance_ini(path, can_index=True)
    loaded = load_instance_ini(path)
    assert loaded.include_unknown is True
    text = path.read_text(encoding="utf-8")
    assert "include_unknown = yes" in text

    save_instance_ini(path, include_unknown=False)
    loaded = load_instance_ini(path)
    assert loaded.include_unknown is False
    assert "include_unknown = no" in path.read_text(encoding="utf-8")


def test_include_unknown_i18n():
    assert "nieprzypisane" in t("pl", "include_unknown").casefold()
    assert "unassigned" in t("en", "include_unknown").casefold()
    assert t("pl", "include_unknown_off_warn")
    assert t("en", "include_unknown_locked")


def test_floor_lock_forces_include_unknown_concept(tmp_path: Path):
    """operator.lock / can_index=no → GUI forces ON; ini load still reports flag."""
    path = tmp_path / "gcode-index.ini"
    save_instance_ini(path, can_index=False, include_unknown=False)
    # Floor PC without lock file: can_index=no; GUI will force effective ON
    cfg = load_instance_ini(path)
    assert cfg.can_index is False
    # Saved preference may be no, but floor UI must ignore it (effective ON)
    assert cfg.include_unknown is False

    # With lock file, can_index forced off as well
    save_instance_ini(path, can_index=True, include_unknown=False)
    (tmp_path / "can_index.lock").write_text("locked\n", encoding="utf-8")
    locked = load_instance_ini(path)
    assert locked.can_index is False
    assert locked.settings_locked is True
