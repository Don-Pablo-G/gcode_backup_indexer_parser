"""Shared helpers for glued-dump header/locator plugins."""

from __future__ import annotations

import re
from typing import Iterator, Optional, Tuple

# First parenthetical comment on a header line.
_FIRST_PAREN = re.compile(r"\(([^)]*)\)")

# Programmer flag on the line immediately below the program header:
# exactly (two letters + digit 1–9), case-insensitive. Anything else → ignore.
_PROGRAMMER_FLAG = re.compile(r"^\(([A-Za-z]{2})([1-9])\)\s*$")


def first_paren_comment(line: str) -> Optional[str]:
    m = _FIRST_PAREN.search(line)
    if not m:
        return None
    text = m.group(1).strip()
    return text or None


def parse_programmer_flag(line: str) -> Optional[str]:
    """Return ``PG1``-style flag if ``line`` is exactly ``(LLdigit)``, else None.

    Matching is case-insensitive; stored form is uppercase. Non-matching comments
    (part numbers, free text, wrong shape) are ignored — never invented.
    """
    s = (line or "").strip()
    if not s:
        return None
    m = _PROGRAMMER_FLAG.match(s)
    if not m:
        return None
    return (m.group(1) + m.group(2)).upper()


def strip_eol(line_with_eol: bytes) -> Tuple[bytes, bytes]:
    """Split raw line into content + EOL bytes (\\r\\n, \\n, \\r, or empty)."""
    if line_with_eol.endswith(b"\r\n"):
        return line_with_eol[:-2], b"\r\n"
    if line_with_eol.endswith(b"\n"):
        return line_with_eol[:-1], b"\n"
    if line_with_eol.endswith(b"\r"):
        return line_with_eol[:-1], b"\r"
    return line_with_eol, b""


def decode_header_line(raw_content: bytes) -> str:
    return raw_content.decode("ascii", errors="replace").rstrip(" \t")


def iter_binary_lines(path) -> Iterator[Tuple[int, int, bytes]]:
    """Yield (line_no_1based, byte_offset, raw_line_including_eol). Streams."""
    offset = 0
    line_no = 0
    with open(path, "rb") as f:
        while True:
            raw = f.readline()
            if not raw:
                break
            line_no += 1
            yield line_no, offset, raw
            offset += len(raw)


def is_percent_line(content: str) -> bool:
    return content.strip() == "%"
