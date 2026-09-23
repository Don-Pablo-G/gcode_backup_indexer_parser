from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from gcode_index import PARSER_VERSION, __version__
from gcode_index.models import FileSeen, ProgramInstance, ScanResult, UnknownFolder

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS index_runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  backup_root TEXT NOT NULL,
  aliases_path TEXT,
  indexer_version TEXT,
  instance_count INTEGER,
  file_count INTEGER,
  unknown_count INTEGER
);

CREATE TABLE IF NOT EXISTS program_instances (
  instance_id TEXT PRIMARY KEY,
  program_number TEXT NOT NULL,
  part_number TEXT,
  machine_id TEXT NOT NULL,
  machine_label TEXT,
  machine_folder_raw TEXT,
  date_folder_raw TEXT,
  backup_date TEXT NOT NULL,
  file_ctime TEXT NOT NULL,
  date_source TEXT NOT NULL,
  source_path TEXT NOT NULL,
  line_start INTEGER,
  line_end INTEGER,
  byte_start INTEGER,
  byte_end INTEGER,
  source_type TEXT NOT NULL,
  folder_path TEXT,
  control_family TEXT,
  source_mtime TEXT,
  source_size INTEGER,
  indexed_at TEXT NOT NULL,
  parser_id TEXT,
  parser_version TEXT,
  parse_status TEXT,
  error_message TEXT,
  header_kind TEXT,
  run_id TEXT,
  FOREIGN KEY (run_id) REFERENCES index_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_pi_program ON program_instances(program_number);
CREATE INDEX IF NOT EXISTS idx_pi_part ON program_instances(part_number);
CREATE INDEX IF NOT EXISTS idx_pi_machine_date ON program_instances(machine_id, backup_date);
CREATE INDEX IF NOT EXISTS idx_pi_source_type ON program_instances(source_type);

CREATE TABLE IF NOT EXISTS files_seen (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT,
  source_path TEXT NOT NULL,
  source_type TEXT,
  size INTEGER,
  mtime TEXT,
  status TEXT NOT NULL,
  note TEXT,
  FOREIGN KEY (run_id) REFERENCES index_runs(run_id)
);

CREATE TABLE IF NOT EXISTS unknowns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT,
  date_folder_raw TEXT,
  machine_folder_raw TEXT NOT NULL,
  normalized_key TEXT,
  note TEXT,
  FOREIGN KEY (run_id) REFERENCES index_runs(run_id)
);
"""


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def open_db(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    return conn


def write_scan_result(
    conn: sqlite3.Connection,
    *,
    backup_root: str,
    aliases_path: Optional[str],
    result: ScanResult,
) -> str:
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    conn.execute(
        """
        INSERT INTO index_runs (
          run_id, started_at, backup_root, aliases_path, indexer_version
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (run_id, _iso(started), backup_root, aliases_path, __version__),
    )

    indexed_at = _iso(datetime.now(timezone.utc))
    rows = []
    for inst in result.instances:
        rows.append(
            (
                str(uuid.uuid4()),
                inst.program_number,
                inst.part_number,
                inst.machine_id,
                inst.machine_label,
                inst.machine_folder_raw,
                inst.date_folder_raw,
                _iso(inst.backup_date),
                _iso(inst.backup_date),  # file_ctime alias
                inst.date_source,
                inst.source_path,
                inst.line_start,
                inst.line_end,
                inst.byte_start,
                inst.byte_end,
                inst.source_type,
                inst.folder_path,
                inst.control_family,
                _iso(inst.source_mtime),
                inst.source_size,
                indexed_at,
                inst.parser_id,
                inst.parser_version or PARSER_VERSION,
                inst.parse_status,
                inst.error_message,
                inst.header_kind,
                run_id,
            )
        )

    conn.executemany(
        """
        INSERT INTO program_instances (
          instance_id, program_number, part_number, machine_id, machine_label,
          machine_folder_raw, date_folder_raw, backup_date, file_ctime, date_source,
          source_path, line_start, line_end, byte_start, byte_end, source_type,
          folder_path, control_family, source_mtime, source_size, indexed_at,
          parser_id, parser_version, parse_status, error_message, header_kind, run_id
        ) VALUES (
          ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
        """,
        rows,
    )

    for fs in result.files_seen:
        conn.execute(
            """
            INSERT INTO files_seen (
              run_id, source_path, source_type, size, mtime, status, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                fs.source_path,
                fs.source_type,
                fs.size,
                _iso(fs.mtime),
                fs.status,
                fs.note,
            ),
        )

    for u in result.unknowns:
        conn.execute(
            """
            INSERT INTO unknowns (
              run_id, date_folder_raw, machine_folder_raw, normalized_key, note
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                run_id,
                u.date_folder_raw,
                u.machine_folder_raw,
                u.normalized_key,
                u.note,
            ),
        )

    finished = datetime.now(timezone.utc)
    conn.execute(
        """
        UPDATE index_runs SET
          finished_at = ?,
          instance_count = ?,
          file_count = ?,
          unknown_count = ?
        WHERE run_id = ?
        """,
        (
            _iso(finished),
            len(result.instances),
            len(result.files_seen),
            len(result.unknowns),
            run_id,
        ),
    )
    conn.commit()
    return run_id


def query_digit_count(query: str) -> int:
    """Count digit characters in a search query."""
    return sum(1 for ch in query if ch.isdigit())


def validate_search_query(query: str) -> str:
    """Normalize and validate a search string. Must contain ≥4 digits.

    Returns the stripped query used for matching.
    """
    q = (query or "").strip()
    if query_digit_count(q) < 4:
        raise ValueError("search query must contain at least 4 digits")
    return q


def _match_rank(value: Optional[str], query: str) -> int:
    """Lower is better: 0 exact, 1 prefix, 2 substring, 3 no match on this field."""
    if not value:
        return 3
    v = value.casefold()
    q = query.casefold()
    if v == q:
        return 0
    if v.startswith(q):
        return 1
    if q in v:
        return 2
    return 3


def rank_match(program_number: Optional[str], part_number: Optional[str], query: str) -> int:
    """Combined rank for a row: best of program # / part # (prefer program on ties)."""
    prog = _match_rank(program_number, query)
    part = _match_rank(part_number, query)
    # Prefer program_number when ranks equal (prog*2 vs part*2+1).
    return min(prog * 2, part * 2 + 1)


def search_instances(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 100,
) -> list[sqlite3.Row]:
    """Substring search on program_number, part_number, and source_path.

    Query must contain ≥4 digits. Results prefer prefix matches over mid-string
    hits, then newer ``backup_date``, then machine / program number.
    """
    q = validate_search_query(query)
    conn.row_factory = sqlite3.Row
    # Wider fetch, then re-rank in Python (LIKE alone cannot prefer prefixes).
    fetch_limit = max(limit * 5, 200)
    cur = conn.execute(
        """
        SELECT instance_id, program_number, part_number, machine_id, machine_label,
               backup_date, source_path, line_start, line_end, byte_start, byte_end,
               source_type
        FROM program_instances
        WHERE program_number LIKE '%' || ? || '%'
           OR part_number LIKE '%' || ? || '%'
           OR source_path LIKE '%' || ? || '%'
        LIMIT ?
        """,
        (q, q, q, fetch_limit),
    )
    rows = list(cur.fetchall())
    # Stable multi-key sort: least → most significant.
    rows.sort(key=lambda r: (r["machine_id"] or "", r["program_number"] or ""))
    rows.sort(key=lambda r: r["backup_date"] or "", reverse=True)
    rows.sort(key=lambda r: rank_match(r["program_number"], r["part_number"], q))
    return rows[:limit]


def list_instances(
    conn: sqlite3.Connection,
    *,
    limit: int = 500,
) -> list[sqlite3.Row]:
    """Browse newest program instances (no query) — used by GUI after scan."""
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT instance_id, program_number, part_number, machine_id, machine_label,
               backup_date, source_path, line_start, line_end, byte_start, byte_end,
               source_type
        FROM program_instances
        ORDER BY backup_date DESC, machine_id, program_number
        LIMIT ?
        """,
        (limit,),
    )
    return list(cur.fetchall())


def format_location(row: sqlite3.Row | dict) -> str:
    """Human-readable in-file location for GUI / consumers."""
    source_type = str(row["source_type"] or "")
    line_start = row["line_start"]
    line_end = row["line_end"]
    byte_start = row["byte_start"]
    byte_end = row["byte_end"]
    glued = source_type in {"haas_pgm_glued", "fanuc_all_fldr", "fanuc_all_prog"}
    if not glued or line_start is None:
        return "whole file"
    loc = f"L{line_start}–{line_end}"
    if byte_start is not None and byte_end is not None:
        loc += f"  B{byte_start}–{byte_end}"
    return loc
