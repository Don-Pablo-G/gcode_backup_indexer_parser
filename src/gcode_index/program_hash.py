"""Program-body hashing for cross-source duplicate detection.

``content_sha256`` on index rows remains the **whole source file** digest
(integrity / change detection at extract time).

``program_sha256`` hashes a **normalized extracted program body** so a glued
dump slice (Haas ``.pgm`` / FANUC ALL-*) can match a loose ``.nc`` with the
same program text.

Normalization (documented, must stay aligned with extract intent):

1. Decode bytes as ASCII with ``errors="replace"`` (same as glued extract).
2. Apply ``ensure_percent_frame`` (leading/trailing ``%``) — glued extracts
   already do this; loose ``.nc`` files are normalized the same way for
   comparison even though extract copies them as-is to disk.
3. Normalize newlines to ``\\n`` before hashing (CRLF vs LF must not diverge).

Re-index is required for older DBs that lack ``program_sha256``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional


def normalize_program_text(text: str) -> str:
    """Canonical text used for ``program_sha256`` (see module docstring)."""
    from gcode_index.extract import ensure_percent_frame

    framed = ensure_percent_frame(text if text is not None else "")
    return framed.replace("\r\n", "\n").replace("\r", "\n")


def program_sha256_text(text: str) -> str:
    body = normalize_program_text(text).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def program_sha256_bytes(raw: bytes) -> str:
    return program_sha256_text(raw.decode("ascii", errors="replace"))


def program_sha256_file(path: Path | str) -> str:
    return program_sha256_bytes(Path(path).read_bytes())


def program_sha256_slice(
    path: Path | str,
    byte_start: Optional[int],
    byte_end: Optional[int],
) -> Optional[str]:
    """Hash a glued dump byte span; ``None`` if span is incomplete."""
    if byte_start is None or byte_end is None:
        return None
    start = int(byte_start)
    end = int(byte_end)
    if end < start:
        return None
    with open(path, "rb") as f:
        f.seek(start)
        raw = f.read(end - start)
    return program_sha256_bytes(raw)
