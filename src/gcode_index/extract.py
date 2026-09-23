"""Extract a program instance from a backup source using index location fields.

Glued dumps (Haas PGM / FANUC ALL-*) use line or byte spans.
Whole-file ``.nc`` types copy the entire source file.
Output is plain text for an *external* parser — this package does not parse G-code bodies.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Mapping, Optional, Union

GLUED_SOURCE_TYPES = frozenset(
    {
        "haas_pgm_glued",
        "fanuc_all_fldr",
        "fanuc_all_prog",
    }
)

RowLike = Union[sqlite3.Row, Mapping[str, object]]


class ExtractError(Exception):
    """Raised when an instance cannot be extracted."""


def resolve_source_path(
    source_path: str | Path,
    backup_root: str | Path | None = None,
) -> Path:
    """Resolve a DB ``source_path`` (relative or absolute) against ``backup_root``."""
    src = Path(source_path)
    if src.is_absolute():
        return src
    if backup_root is None:
        raise ExtractError(
            f"source_path is relative ({source_path!r}) but backup_root was not provided"
        )
    return Path(backup_root) / src


def fetch_instance(
    conn: sqlite3.Connection,
    instance_id: str,
) -> sqlite3.Row:
    """Load one ``program_instances`` row by id, or raise ``ExtractError``."""
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT instance_id, program_number, part_number, machine_id, backup_date,
               source_path, line_start, line_end, byte_start, byte_end, source_type
        FROM program_instances
        WHERE instance_id = ?
        """,
        (instance_id,),
    ).fetchone()
    if row is None:
        raise ExtractError(f"instance_id not found: {instance_id}")
    return row


def extract_text(
    row: RowLike,
    *,
    backup_root: str | Path | None = None,
) -> str:
    """Return the program body text for an index row.

    Preference for glued dumps: byte span when both ends are set, else line span
    (1-based inclusive). Whole-file types return the entire file as text.
    """
    source_type = str(row["source_type"] or "")
    src = resolve_source_path(str(row["source_path"]), backup_root)
    if not src.is_file():
        raise ExtractError(f"source file missing: {src}")

    glued = source_type in GLUED_SOURCE_TYPES
    byte_start = row["byte_start"]
    byte_end = row["byte_end"]
    line_start = row["line_start"]
    line_end = row["line_end"]

    if glued and byte_start is not None and byte_end is not None:
        with open(src, "rb") as f:
            f.seek(int(byte_start))
            data = f.read(int(byte_end) - int(byte_start))
        return data.decode("ascii", errors="replace")

    if glued and line_start is not None and line_end is not None:
        # splitlines(keepends=True) is CRLF-aware (keeps \\r\\n as one line ending).
        lines = src.read_bytes().splitlines(keepends=True)
        start = int(line_start) - 1
        end = int(line_end)
        if start < 0 or end > len(lines) or start >= end:
            raise ExtractError(
                f"invalid line span {line_start}-{line_end} for {src} "
                f"({len(lines)} lines)"
            )
        return b"".join(lines[start:end]).decode("ascii", errors="replace")

    if glued:
        raise ExtractError(
            f"glued source_type={source_type!r} has no line/byte span for {src}"
        )

    return src.read_text(encoding="ascii", errors="replace")


def default_extract_filename(row: RowLike) -> str:
    """Suggest a safe output basename from program/part numbers."""
    prog = str(row["program_number"] or "program").strip() or "program"
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in prog)
    return f"{safe}.nc"


def extract_to_path(
    row: RowLike,
    out_path: str | Path,
    *,
    backup_root: str | Path | None = None,
) -> Path:
    """Extract program text and write UTF-8 to ``out_path``. Returns the path written."""
    text = extract_text(row, backup_root=backup_root)
    dest = Path(out_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest


def extract_instance_to_path(
    conn: sqlite3.Connection,
    instance_id: str,
    out_path: str | Path,
    *,
    backup_root: str | Path | None = None,
) -> Path:
    """Fetch ``instance_id`` from ``conn`` and write the extracted body to ``out_path``."""
    row = fetch_instance(conn, instance_id)
    return extract_to_path(row, out_path, backup_root=backup_root)
