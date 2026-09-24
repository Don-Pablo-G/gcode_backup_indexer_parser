"""Older Haas glued *.pgm locator — headers + spans only (CRLF-aware)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

from gcode_index import PARSER_VERSION
from gcode_index.birthtime import file_birth_or_mtime, file_mtime
from gcode_index.integrity import file_sha256
from gcode_index.locators import (
    decode_header_line,
    first_paren_comment,
    is_percent_line,
    iter_binary_lines,
    strip_eol,
)
from gcode_index.models import ProgramInstance

PARSER_ID = "haas_pgm_glued"
SOURCE_TYPE = "haas_pgm_glued"

# Line-leading O#####… (optional mid-tokens, optional same-line paren comment).
_O_HEADER = re.compile(r"^O(\d+)(?:\s+\S+)*\s*(?:\([^)]*\))?\s*$")


@dataclass
class _HeaderHit:
    line_no: int
    byte_start: int
    program_number: str
    part_number: Optional[str]


def locate_haas_pgm(
    path: Path | str,
    *,
    source_path: str,
    machine_id: str,
    machine_label: Optional[str] = None,
    machine_folder_raw: Optional[str] = None,
    date_folder_raw: Optional[str] = None,
    control_family: str = "haas",
) -> List[ProgramInstance]:
    p = Path(path)
    backup_date, date_source = file_birth_or_mtime(p)
    mtime = file_mtime(p)
    size = p.stat().st_size

    hits: List[_HeaderHit] = []
    closing_pct_line: Optional[int] = None
    closing_pct_byte: Optional[int] = None
    last_line_no = 0
    eof_byte = 0

    for line_no, offset, raw in iter_binary_lines(p):
        last_line_no = line_no
        eof_byte = offset + len(raw)
        content_b, _eol = strip_eol(raw)
        content = decode_header_line(content_b)

        if is_percent_line(content):
            # Keep updating; last % is the closing frame.
            closing_pct_line = line_no
            closing_pct_byte = offset
            continue

        m = _O_HEADER.match(content)
        if m:
            hits.append(
                _HeaderHit(
                    line_no=line_no,
                    byte_start=offset,
                    program_number=m.group(1),
                    part_number=first_paren_comment(content),
                )
            )

    instances: List[ProgramInstance] = []
    digest = file_sha256(p)
    for i, hit in enumerate(hits):
        if i + 1 < len(hits):
            nxt = hits[i + 1]
            line_end = nxt.line_no - 1
            byte_end = nxt.byte_start
        elif closing_pct_line is not None and closing_pct_byte is not None:
            line_end = closing_pct_line - 1
            byte_end = closing_pct_byte
        else:
            line_end = last_line_no
            byte_end = eof_byte

        # Prefer trim: if line_end points at blank lines before next marker, keep as-is
        # (inclusive line_end). Ensure line_end >= line_start.
        if line_end < hit.line_no:
            line_end = hit.line_no

        instances.append(
            ProgramInstance(
                program_number=hit.program_number,
                part_number=hit.part_number,
                machine_id=machine_id,
                backup_date=backup_date,
                date_source=date_source,
                source_path=source_path,
                source_type=SOURCE_TYPE,
                line_start=hit.line_no,
                line_end=line_end,
                byte_start=hit.byte_start,
                byte_end=byte_end,
                machine_label=machine_label,
                machine_folder_raw=machine_folder_raw,
                date_folder_raw=date_folder_raw,
                folder_path=None,
                control_family=control_family,
                source_mtime=mtime,
                source_size=size,
                content_sha256=digest,
                parser_id=PARSER_ID,
                parser_version=PARSER_VERSION,
                parse_status="ok",
                header_kind="o_number",
            )
        )
    return instances
