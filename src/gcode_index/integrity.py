"""Source-file hashing for index-time integrity stamps."""

from __future__ import annotations

import hashlib
from pathlib import Path


def file_sha256(path: Path | str, *, chunk_size: int = 1024 * 1024) -> str:
    """SHA-256 hex digest of the entire file (streaming)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
