from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from gcode_index import PARSER_VERSION, __version__
from gcode_index.models import FileSeen, ProgramInstance, ScanResult, UnknownFolder

# Optional leading O + digits only → treat as a program-number search (#20)
_PROGRAM_QUERY_RE = re.compile(r"^O?\d+$", re.IGNORECASE)

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
  content_sha256 TEXT,
  indexed_at TEXT NOT NULL,
  parser_id TEXT,
  parser_version TEXT,
  parse_status TEXT,
  error_message TEXT,
  header_kind TEXT,
  provenance TEXT NOT NULL DEFAULT 'backup',
  scan_root TEXT,
  programmer TEXT,
  run_id TEXT,
  FOREIGN KEY (run_id) REFERENCES index_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_pi_program ON program_instances(program_number);
CREATE INDEX IF NOT EXISTS idx_pi_part ON program_instances(part_number);
CREATE INDEX IF NOT EXISTS idx_pi_machine_date ON program_instances(machine_id, backup_date);
CREATE INDEX IF NOT EXISTS idx_pi_source_type ON program_instances(source_type);
CREATE INDEX IF NOT EXISTS idx_pi_provenance ON program_instances(provenance);
CREATE INDEX IF NOT EXISTS idx_pi_programmer ON program_instances(programmer);

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
    _migrate_schema(conn)
    return conn


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Add columns introduced after older DB files were created."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(program_instances)")}
    if "content_sha256" not in cols:
        conn.execute("ALTER TABLE program_instances ADD COLUMN content_sha256 TEXT")
    if "provenance" not in cols:
        conn.execute(
            "ALTER TABLE program_instances ADD COLUMN provenance TEXT NOT NULL DEFAULT 'backup'"
        )
    if "scan_root" not in cols:
        conn.execute("ALTER TABLE program_instances ADD COLUMN scan_root TEXT")
    if "programmer" not in cols:
        conn.execute("ALTER TABLE program_instances ADD COLUMN programmer TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pi_provenance ON program_instances(provenance)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pi_programmer ON program_instances(programmer)"
    )
    conn.commit()


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
                inst.content_sha256,
                indexed_at,
                inst.parser_id,
                inst.parser_version or PARSER_VERSION,
                inst.parse_status,
                inst.error_message,
                inst.header_kind,
                inst.provenance or "backup",
                inst.scan_root,
                inst.programmer,
                run_id,
            )
        )

    conn.executemany(
        """
        INSERT INTO program_instances (
          instance_id, program_number, part_number, machine_id, machine_label,
          machine_folder_raw, date_folder_raw, backup_date, file_ctime, date_source,
          source_path, line_start, line_end, byte_start, byte_end, source_type,
          folder_path, control_family, source_mtime, source_size, content_sha256,
          indexed_at, parser_id, parser_version, parse_status, error_message,
          header_kind, provenance, scan_root, programmer, run_id
        ) VALUES (
          ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
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


def validate_search_query(query: str, *, min_chars: int = 1) -> str:
    """Normalize a free-text search string (letters, digits, punctuation OK).

    Empty after strip raises ``ValueError``. Digit-count gates were removed —
    part names like ``P-00253232 VA`` and paths need letters / dashes.
    """
    q = (query or "").strip()
    if len(q) < min_chars:
        raise ValueError("search query is empty")
    return q


def is_program_number_query(query: str) -> bool:
    """True when ``query`` is only an optional ``O`` plus digits (program search)."""
    q = (query or "").strip()
    return bool(q) and _PROGRAM_QUERY_RE.fullmatch(q) is not None


def program_digit_core(value: Optional[str]) -> Optional[str]:
    """Strip optional leading ``O`` and leading zeros → digit core.

    ``O03232`` / ``03232`` / ``3232`` → ``3232``. All-zeros → ``0``.
    Returns ``None`` if the value is not program-number-shaped.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or not _PROGRAM_QUERY_RE.fullmatch(s):
        return None
    if s[:1] in "Oo":
        s = s[1:]
    if not s.isdigit():
        return None
    core = s.lstrip("0")
    return core if core else "0"


def program_search_variants(query: str) -> list[str]:
    """LIKE needles for a program-ish query (``O`` / padding variants).

    Non-program queries return a single casefolded needle (caller uses as-is).
    """
    q = (query or "").strip()
    if not q:
        return []
    fold = q.casefold()
    if not is_program_number_query(q):
        return [fold]
    variants: set[str] = {fold}
    digits = q[1:] if q[:1] in "Oo" else q
    variants.add(digits.casefold())
    core = program_digit_core(q)
    if core is not None:
        variants.add(core)
        for width in (4, 5, 6):
            if len(core) <= width:
                variants.add(core.zfill(width))
        # Also try with a leading O (for any future storage that keeps O)
        variants.add(f"o{core}")
        for width in (4, 5):
            if len(core) <= width:
                variants.add(f"o{core.zfill(width)}")
    # Longest first so SQL OR order is irrelevant but lists are stable
    return sorted(variants, key=lambda s: (-len(s), s))


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


def _program_match_rank(program_number: Optional[str], query: str) -> int:
    """Rank program # with O/zero-padding normalize when query is program-ish."""
    literal = _match_rank(program_number, query)
    if not is_program_number_query(query):
        return literal
    q_core = program_digit_core(query)
    p_core = program_digit_core(program_number)
    if q_core is not None and p_core is not None and q_core == p_core:
        return 0  # same logical O-number
    # Also try literal variants (O03232 vs stored 03232)
    best = literal
    for needle in program_search_variants(query):
        best = min(best, _match_rank(program_number, needle))
        # stored may lack O while needle has it — compare without O on value
        if program_number:
            best = min(best, _match_rank(f"O{program_number}", needle))
    return best


def rank_match(
    program_number: Optional[str],
    part_number: Optional[str],
    query: str,
    *,
    source_path: Optional[str] = None,
    machine_id: Optional[str] = None,
    machine_label: Optional[str] = None,
) -> int:
    """Combined rank for a row (prefer program #, then part, then path/machine)."""
    ranks = [
        _program_match_rank(program_number, query) * 2,
        _match_rank(part_number, query) * 2 + 1,
        _match_rank(source_path, query) * 2 + 2,
        _match_rank(machine_label, query) * 2 + 3,
        _match_rank(machine_id, query) * 2 + 4,
    ]
    return min(ranks)


_INSTANCE_SELECT = """
        SELECT instance_id, program_number, part_number, machine_id, machine_label,
               machine_folder_raw, date_folder_raw, backup_date, source_path,
               line_start, line_end, byte_start, byte_end, source_type,
               folder_path, control_family, source_size, content_sha256,
               provenance, scan_root, programmer
        FROM program_instances
"""


def _normalize_date_bound(value: Optional[str], *, end: bool = False) -> Optional[str]:
    """Accept ``DD.MM.YYYY``, ``YYYY-MM-DD``, or ISO datetime → comparable ISO string."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    day: Optional[str] = None
    # Preferred GUI form: DD.MM.YYYY (also DD-MM-YYYY / DD/MM/YYYY)
    if len(s) == 10 and s[2] in ".-/" and s[5] in ".-/":
        dd, mm, yyyy = s[0:2], s[3:5], s[6:10]
        if yyyy.isdigit() and mm.isdigit() and dd.isdigit():
            day = f"{yyyy}-{mm}-{dd}"
    # ISO date-only: YYYY-MM-DD
    elif len(s) == 10 and s[4] == "-" and s[7] == "-":
        day = s

    if day is not None:
        # Validate calendar date
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"invalid date: {value!r}") from exc
        return f"{day}T23:59:59.999999+00:00" if end else f"{day}T00:00:00+00:00"

    # Already an ISO datetime (or other comparable string) — pass through
    return s


def format_display_date(iso_value: Optional[str]) -> str:
    """Format stored backup_date for GUI tables as ``DD.MM.YYYY`` when possible."""
    if not iso_value:
        return ""
    s = str(iso_value).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            d = datetime.strptime(s[:10], "%Y-%m-%d")
            return d.strftime("%d.%m.%Y")
        except ValueError:
            pass
    return s[:19].replace("T", " ")


def collapse_newest_per_program_machine(rows: list) -> list:
    """Keep one row per (program_number, machine_id) — the newest ``backup_date``.

    Ties keep the first-seen row among equals. Output is sorted newest-first,
    then machine, then program.
    """
    best: dict[tuple[str, str], object] = {}
    for r in rows:
        prog = str(r["program_number"] or "").casefold()
        mid = str(r["machine_id"] or "").casefold()
        key = (prog, mid)
        prev = best.get(key)
        if prev is None:
            best[key] = r
            continue
        prev_date = str(prev["backup_date"] or "")
        cur_date = str(r["backup_date"] or "")
        if cur_date > prev_date:
            best[key] = r
    out = list(best.values())
    out.sort(key=lambda r: (str(r["machine_id"] or ""), str(r["program_number"] or "")))
    out.sort(key=lambda r: str(r["backup_date"] or ""), reverse=True)
    return out


def query_instances(
    conn: sqlite3.Connection,
    *,
    text: Optional[str] = None,
    machine: Optional[str] = None,
    machines: Optional[Iterable[str]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    source_type: Optional[str] = None,
    control_family: Optional[str] = None,
    provenance: Optional[str] = None,
    programmer: Optional[str] = None,
    newest_only: bool = False,
    limit: int = 500,
) -> list[sqlite3.Row]:
    """Flexible filter/search for GUI and CLI.

    ``text`` — free substring (any characters) across program #, part #, path,
    machine id/label/folder, FANUC folder_path, date folder, programmer.
    Program-shaped queries (optional ``O`` + digits) also match ``program_number``
    after stripping ``O`` / leading zeros (``1234`` ↔ ``O01234`` ↔ ``01234``).
    ``machine`` — single machine id/label (CLI); ignored if ``machines`` is set.
    ``machines`` — one or more machine ids/labels (multi-select GUI).
    ``date_from`` / ``date_to`` — inclusive bounds on ``backup_date``
    (``DD.MM.YYYY`` or ``YYYY-MM-DD``).
    ``source_type`` / ``control_family`` — exact match when set.
    ``provenance`` — ``backup`` (green / ran on machine) or ``extra`` (yellow).
    ``programmer`` — exact uppercase flag e.g. ``PG1`` (case-insensitive input).
    ``newest_only`` — keep newest row per program+machine after filtering.
    """
    conn.row_factory = sqlite3.Row
    clauses: list[str] = []
    params: list[object] = []

    q: Optional[str] = None
    if text is not None and str(text).strip():
        q = validate_search_query(str(text))
        # LOWER() on both sides → case-insensitive for ASCII letters
        # (P-00045613 Va == p-00045613 va)
        like = f"%{q.casefold()}%"
        field_ors = [
            "LOWER(program_number) LIKE ?",
            "LOWER(IFNULL(part_number,'')) LIKE ?",
            "LOWER(source_path) LIKE ?",
            "LOWER(machine_id) LIKE ?",
            "LOWER(IFNULL(machine_label,'')) LIKE ?",
            "LOWER(IFNULL(machine_folder_raw,'')) LIKE ?",
            "LOWER(IFNULL(folder_path,'')) LIKE ?",
            "LOWER(IFNULL(date_folder_raw,'')) LIKE ?",
            "LOWER(IFNULL(programmer,'')) LIKE ?",
        ]
        field_params: list[object] = [like] * 9
        # #20: also match program_number against O/padding variants
        if is_program_number_query(q):
            for needle in program_search_variants(q):
                if needle == q.casefold():
                    continue  # already covered
                field_ors.append("LOWER(program_number) LIKE ?")
                field_params.append(f"%{needle}%")
                # Stored value with synthetic leading O (rare / future-proof)
                field_ors.append("LOWER('o' || program_number) LIKE ?")
                field_params.append(f"%{needle}%")
        clauses.append("(" + " OR ".join(field_ors) + ")")
        params.extend(field_params)

    machine_list: list[str] = []
    if machines is not None:
        machine_list = [str(m).strip() for m in machines if str(m).strip() and str(m).strip() != "(all)"]
    elif machine is not None and str(machine).strip() and str(machine).strip() != "(all)":
        machine_list = [str(machine).strip()]

    if machine_list:
        or_parts: list[str] = []
        for raw in machine_list:
            m = raw
            if m.endswith(")") and "(" in m:
                inner = m[m.rfind("(") + 1 : -1].strip()
                if inner:
                    m = inner
            m_fold = m.casefold()
            or_parts.append(
                """(
                  LOWER(machine_id) = ?
                  OR LOWER(IFNULL(machine_label,'')) = ?
                  OR LOWER(IFNULL(machine_folder_raw,'')) = ?
                  OR LOWER(machine_id) LIKE ?
                  OR LOWER(IFNULL(machine_label,'')) LIKE ?
                )"""
            )
            params.extend([m_fold, m_fold, m_fold, f"%{m_fold}%", f"%{m_fold}%"])
        clauses.append("(" + " OR ".join(or_parts) + ")")

    d_from = _normalize_date_bound(date_from, end=False)
    d_to = _normalize_date_bound(date_to, end=True)
    if d_from:
        clauses.append("backup_date >= ?")
        params.append(d_from)
    if d_to:
        clauses.append("backup_date <= ?")
        params.append(d_to)

    if source_type is not None and str(source_type).strip() and str(source_type).strip() != "(all)":
        clauses.append("source_type = ?")
        params.append(str(source_type).strip())

    if (
        control_family is not None
        and str(control_family).strip()
        and str(control_family).strip() != "(all)"
    ):
        clauses.append("IFNULL(control_family,'') = ?")
        params.append(str(control_family).strip())

    if provenance is not None and str(provenance).strip() and str(provenance).strip() != "(all)":
        clauses.append("IFNULL(provenance,'backup') = ?")
        params.append(str(provenance).strip())

    if programmer is not None and str(programmer).strip() and str(programmer).strip() != "(all)":
        clauses.append("UPPER(IFNULL(programmer,'')) = ?")
        params.append(str(programmer).strip().upper())

    sql = _INSTANCE_SELECT
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    # Pull extra rows when collapsing so newest-per-key survives the LIMIT
    if newest_only:
        fetch_limit = max(limit * 20, 1000)
    elif q:
        fetch_limit = max(limit * 5, 200)
    else:
        fetch_limit = limit
    sql += " LIMIT ?"
    params.append(fetch_limit)

    rows = list(conn.execute(sql, params).fetchall())
    if q:
        rows.sort(key=lambda r: (r["machine_id"] or "", r["program_number"] or ""))
        rows.sort(key=lambda r: r["backup_date"] or "", reverse=True)
        rows.sort(
            key=lambda r: rank_match(
                r["program_number"],
                r["part_number"],
                q,
                source_path=r["source_path"],
                machine_id=r["machine_id"],
                machine_label=r["machine_label"],
            )
        )
    else:
        rows.sort(key=lambda r: (r["machine_id"] or "", r["program_number"] or ""))
        rows.sort(key=lambda r: r["backup_date"] or "", reverse=True)
    if newest_only:
        rows = collapse_newest_per_program_machine(rows)
    return rows[:limit]


def search_instances(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 100,
) -> list[sqlite3.Row]:
    """Free-text search (any characters) across program / part / path / machine."""
    return query_instances(conn, text=query, limit=limit)


def list_instances(
    conn: sqlite3.Connection,
    *,
    limit: int = 500,
) -> list[sqlite3.Row]:
    """Browse newest program instances (no query) — used by GUI after scan."""
    return query_instances(conn, limit=limit)


def list_filter_values(
    conn: sqlite3.Connection,
    *,
    seed_machines: Optional[Iterable[str]] = None,
) -> dict[str, list[str]]:
    """Distinct values for GUI filter dropdowns.

    ``seed_machines`` — optional catalog labels (e.g. from aliases.yaml) so known
    shop machines like HAAS UMC750 appear even when the last scan found none.
    """
    conn.row_factory = sqlite3.Row
    machines: list[str] = []
    seen: set[str] = set()

    def _add(display: str) -> None:
        d = (display or "").strip()
        if d and d not in seen:
            seen.add(d)
            machines.append(d)

    for display in seed_machines or []:
        _add(str(display))

    for r in conn.execute(
        """
        SELECT DISTINCT machine_id, machine_label
        FROM program_instances
        ORDER BY IFNULL(machine_label, machine_id)
        """
    ):
        mid = r["machine_id"] or ""
        label = (r["machine_label"] or "").strip()
        display = f"{label} ({mid})" if label and label != mid else mid
        _add(display)

    machines.sort(key=lambda s: s.casefold())

    types = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT source_type FROM program_instances ORDER BY source_type"
        )
        if r[0]
    ]
    families = [
        r[0]
        for r in conn.execute(
            """
            SELECT DISTINCT control_family FROM program_instances
            WHERE control_family IS NOT NULL AND control_family != ''
            ORDER BY control_family
            """
        )
    ]
    programmers = [
        r[0]
        for r in conn.execute(
            """
            SELECT DISTINCT programmer FROM program_instances
            WHERE programmer IS NOT NULL AND programmer != ''
            ORDER BY programmer
            """
        )
    ]
    return {
        "machines": machines,
        "source_types": types,
        "control_families": families,
        "programmers": programmers,
    }


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
