"""Extract a program instance from a backup source using index location fields.

Glued dumps (Haas PGM / FANUC ALL-*) use line or byte spans.
Whole-file ``.nc`` types copy the entire source file.
Output is plain text for an *external* parser — this package does not parse G-code bodies.

Before reading, verifies optional ``content_sha256`` / ``source_size`` from the index
so a file changed after scan cannot silently yield the wrong program.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Mapping, Optional, Union

from gcode_index.integrity import file_sha256

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
    *,
    scan_root: str | Path | None = None,
) -> Path:
    """Resolve a DB ``source_path`` (relative or absolute) against scan/backup root."""
    src = Path(source_path)
    if src.is_absolute():
        return src
    base = scan_root or backup_root
    if base is None:
        raise ExtractError(
            f"source_path is relative ({source_path!r}) but scan_root/backup_root "
            "was not provided"
        )
    return Path(base) / src


def _row_get(row: RowLike, key: str):
    keys = row.keys() if hasattr(row, "keys") else row  # type: ignore[arg-type]
    if key not in keys:
        return None
    return row[key]


def verify_source_integrity(row: RowLike, src: Path) -> None:
    """Refuse extract/copy when the on-disk file no longer matches the index stamp."""
    if not src.is_file():
        raise ExtractError(f"source file missing: {src}")

    expected_size = _row_get(row, "source_size")
    expected_sha = _row_get(row, "content_sha256")

    st = src.stat()
    if expected_size is not None and int(st.st_size) != int(expected_size):
        raise ExtractError(
            f"source file changed since index (size {st.st_size} ≠ indexed "
            f"{expected_size}): {src}\nRe-run scan before extract/copy."
        )

    if expected_sha:
        actual = file_sha256(src)
        if actual.casefold() != str(expected_sha).casefold():
            raise ExtractError(
                f"source file changed since index (SHA-256 mismatch): {src}\n"
                f"indexed={expected_sha}\nactual ={actual}\n"
                f"Re-run scan before extract/copy."
            )


def fetch_instance(
    conn: sqlite3.Connection,
    instance_id: str,
) -> sqlite3.Row:
    """Load one ``program_instances`` row by id, or raise ``ExtractError``."""
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT instance_id, program_number, part_number, machine_id, backup_date,
               source_path, line_start, line_end, byte_start, byte_end, source_type,
               source_size, content_sha256
        FROM program_instances
        WHERE instance_id = ?
        """,
        (instance_id,),
    ).fetchone()
    if row is None:
        raise ExtractError(f"instance_id not found: {instance_id}")
    return row


def ensure_percent_frame(text: str) -> str:
    """Wrap program text with leading/trailing ``%`` lines when missing.

    Used for **glued** Haas/FANUC extracts only (dump spans omit the file-level
    ``%`` frame). Whole-file ``.nc`` copies must not call this.
    """
    if text is None:
        return "%\n%\n"
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    nonempty = [ln.strip() for ln in lines if ln.strip() != ""]
    has_open = bool(nonempty) and nonempty[0] == "%"
    has_close = bool(nonempty) and nonempty[-1] == "%"
    if has_open and has_close:
        return text if text.endswith(("\n", "\r")) else text + eol

    body = text
    if body and not body.endswith(("\n", "\r")):
        body = body + eol
    if not has_open:
        body = f"%{eol}" + body
    if not has_close:
        body = body + f"%{eol}"
    return body


def extract_text(
    row: RowLike,
    *,
    backup_root: str | Path | None = None,
    skip_integrity: bool = False,
) -> str:
    """Return the program body text for an index row.

    Preference for glued dumps: byte span when both ends are set, else line span
    (1-based inclusive). Whole-file types return the entire file as text.

    Output for **glued** dumps is wrapped with ``%`` … ``%`` when missing
    (those spans omit the dump’s file-level frame). Whole-file ``.nc`` /
    ``.nc.copy`` are copied **as-is** — no ``%`` is invented.

    By default verifies ``content_sha256`` / ``source_size`` when present in ``row``.
    """
    source_type = str(row["source_type"] or "")
    scan_root = _row_get(row, "scan_root")
    src = resolve_source_path(
        str(row["source_path"]),
        backup_root,
        scan_root=str(scan_root) if scan_root else None,
    )
    if not skip_integrity:
        verify_source_integrity(row, src)
    elif not src.is_file():
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
        return ensure_percent_frame(data.decode("ascii", errors="replace"))

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
        return ensure_percent_frame(
            b"".join(lines[start:end]).decode("ascii", errors="replace")
        )

    if glued:
        raise ExtractError(
            f"glued source_type={source_type!r} has no line/byte span for {src}"
        )

    # Whole-file .nc / .nc.copy: copy as-is (do not invent a % frame)
    return src.read_text(encoding="ascii", errors="replace")


def default_extract_filename(row: RowLike) -> str:
    """Suggest a safe output basename from program/part numbers."""
    prog = str(row["program_number"] or "program").strip() or "program"
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in prog)
    source_type = str(row["source_type"] or "")
    if source_type.endswith("_copy"):
        return f"{safe}.nc.copy"
    return f"{safe}.nc"


def batch_extract_filename(row: RowLike, *, used: Optional[set[str]] = None) -> str:
    """Filename for batch extract: program + machine + date, unique within ``used``."""
    prog = str(row["program_number"] or "program").strip() or "program"
    mid = str(row["machine_id"] or "machine").strip() or "machine"
    date_raw = str(row["backup_date"] or "")[:10].replace("-", "")
    if len(date_raw) != 8 or not date_raw.isdigit():
        date_raw = "nodate"
    # DDMMYYYY display preference for humans
    try:
        from datetime import datetime as _dt

        d = _dt.strptime(str(row["backup_date"])[:10], "%Y-%m-%d")
        date_raw = d.strftime("%d.%m.%Y")
    except Exception:  # noqa: BLE001
        pass

    def _safe(s: str) -> str:
        return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in s)

    source_type = str(row["source_type"] or "")
    ext = ".nc.copy" if source_type.endswith("_copy") else ".nc"
    base = f"{_safe(prog)}_{_safe(mid)}_{_safe(date_raw)}{ext}"
    if used is None:
        return base
    if base not in used:
        used.add(base)
        return base
    n = 2
    while True:
        stem = base[: -len(ext)]
        candidate = f"{stem}_{n}{ext}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        n += 1


def extract_to_path(
    row: RowLike,
    out_path: str | Path,
    *,
    backup_root: str | Path | None = None,
    skip_integrity: bool = False,
) -> Path:
    """Extract program text and write UTF-8 to ``out_path``. Returns the path written."""
    text = extract_text(row, backup_root=backup_root, skip_integrity=skip_integrity)
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
    skip_integrity: bool = False,
) -> Path:
    """Fetch ``instance_id`` from ``conn`` and write the extracted body to ``out_path``."""
    row = fetch_instance(conn, instance_id)
    return extract_to_path(
        row, out_path, backup_root=backup_root, skip_integrity=skip_integrity
    )
