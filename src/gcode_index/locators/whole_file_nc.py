"""Whole-file .nc locators (NGC Memory, manual folder, loose)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

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

# Same O-word shape as older Haas PGM / typical Haas NGC program start.
_O_HEADER = re.compile(r"^O(\d+)(?:\s+\S+)*\s*(?:\([^)]*\))?\s*$")

# Scan only the top of the file for the program header (one program per .nc).
_MAX_HEADER_SCAN_LINES = 40


def _first_o_header(path: Path) -> Tuple[Optional[str], Optional[str]]:
    """Return (program_number, part_number) from the first line-leading O#####…"""
    for line_no, _offset, raw in iter_binary_lines(path):
        if line_no > _MAX_HEADER_SCAN_LINES:
            break
        content_b, _eol = strip_eol(raw)
        content = decode_header_line(content_b)
        if not content or is_percent_line(content):
            continue
        m = _O_HEADER.match(content)
        if m:
            return m.group(1), first_paren_comment(content)
    return None, None


def locate_whole_file_nc(
    path: Path | str,
    *,
    source_path: str,
    source_type: str,
    machine_id: str,
    machine_label: Optional[str] = None,
    machine_folder_raw: Optional[str] = None,
    date_folder_raw: Optional[str] = None,
    control_family: Optional[str] = None,
    folder_path: Optional[str] = None,
    parser_id: Optional[str] = None,
) -> ProgramInstance:
    """One .nc file = one instance.

    Prefer in-file ``O##### (part…)`` when present (Haas NGC sample-backed);
    otherwise fall back to filename stem.
    """
    p = Path(path)
    backup_date, date_source = file_birth_or_mtime(p)
    mtime = file_mtime(p)
    size = p.stat().st_size
    stem = p.stem

    program_number, part_number = _first_o_header(p)
    if program_number is not None:
        header_kind = "o_word"
    else:
        program_number = stem
        part_number = None
        header_kind = "filename"

    digest = file_sha256(p)

    return ProgramInstance(
        program_number=program_number,
        part_number=part_number,
        machine_id=machine_id,
        backup_date=backup_date,
        date_source=date_source,
        source_path=source_path,
        source_type=source_type,
        line_start=None,
        line_end=None,
        byte_start=None,
        byte_end=None,
        machine_label=machine_label,
        machine_folder_raw=machine_folder_raw,
        date_folder_raw=date_folder_raw,
        folder_path=folder_path,
        control_family=control_family,
        source_mtime=mtime,
        source_size=size,
        content_sha256=digest,
        parser_id=parser_id or source_type,
        parser_version=PARSER_VERSION,
        parse_status="ok",
        header_kind=header_kind,
    )
