"""FANUC ALL-FLDR.TXT glued locator — headers + spans only."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

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

PARSER_ID = "fanuc_all_fldr_glued"
SOURCE_TYPE = "fanuc_all_fldr"

_ANGLE = re.compile(r"^<([^>]+)>(?:\([^)]*\))*\s*$")
_O_HEADER = re.compile(r"^O(\d+)(\([^)]*\))?\s*$")
_FOLDER = re.compile(r"^&F=(.*)$")


@dataclass
class _Hit:
    kind: str  # header | folder | percent
    line_no: int
    byte_start: int
    program_number: Optional[str] = None
    part_number: Optional[str] = None
    header_kind: Optional[str] = None
    folder_path: Optional[str] = None


def locate_fanuc_all_fldr(
    path: Path | str,
    *,
    source_path: str,
    machine_id: str,
    machine_label: Optional[str] = None,
    machine_folder_raw: Optional[str] = None,
    date_folder_raw: Optional[str] = None,
    control_family: str = "fanuc",
) -> List[ProgramInstance]:
    return _locate_fanuc_glued(
        path,
        source_path=source_path,
        machine_id=machine_id,
        machine_label=machine_label,
        machine_folder_raw=machine_folder_raw,
        date_folder_raw=date_folder_raw,
        control_family=control_family,
        source_type=SOURCE_TYPE,
        parser_id=PARSER_ID,
        split_on_folder=True,
        o_pattern=_O_HEADER,
        angle_pattern=_ANGLE,
        angle_multi_paren=True,
    )


def _locate_fanuc_glued(
    path: Path | str,
    *,
    source_path: str,
    machine_id: str,
    machine_label: Optional[str],
    machine_folder_raw: Optional[str],
    date_folder_raw: Optional[str],
    control_family: str,
    source_type: str,
    parser_id: str,
    split_on_folder: bool,
    o_pattern: re.Pattern[str],
    angle_pattern: re.Pattern[str],
    angle_multi_paren: bool,
) -> List[ProgramInstance]:
    p = Path(path)
    backup_date, date_source = file_birth_or_mtime(p)
    mtime = file_mtime(p)
    size = p.stat().st_size

    headers: List[_Hit] = []
    current_folder: Optional[str] = None
    last_line_no = 0
    eof_byte = 0

    # Collect headers and folder/percent as boundary markers.
    boundaries: List[_Hit] = []

    for line_no, offset, raw in iter_binary_lines(p):
        last_line_no = line_no
        eof_byte = offset + len(raw)
        content_b, _ = strip_eol(raw)
        content = decode_header_line(content_b)

        if is_percent_line(content):
            hit = _Hit(kind="percent", line_no=line_no, byte_start=offset)
            boundaries.append(hit)
            continue

        if split_on_folder:
            fm = _FOLDER.match(content)
            if fm:
                current_folder = fm.group(1).rstrip()
                boundaries.append(
                    _Hit(
                        kind="folder",
                        line_no=line_no,
                        byte_start=offset,
                        folder_path=current_folder,
                    )
                )
                continue

        om = o_pattern.match(content)
        if om:
            prog = om.group(1)
            headers.append(
                _Hit(
                    kind="header",
                    line_no=line_no,
                    byte_start=offset,
                    program_number=prog,
                    part_number=first_paren_comment(content),
                    header_kind="o_number",
                    folder_path=current_folder,
                )
            )
            boundaries.append(headers[-1])
            continue

        am = angle_pattern.match(content)
        if am:
            name = am.group(1)
            headers.append(
                _Hit(
                    kind="header",
                    line_no=line_no,
                    byte_start=offset,
                    program_number=name,
                    part_number=first_paren_comment(content),
                    header_kind="angle",
                    folder_path=current_folder,
                )
            )
            boundaries.append(headers[-1])
            continue

    instances: List[ProgramInstance] = []
    digest = file_sha256(p)
    header_indices = [i for i, b in enumerate(boundaries) if b.kind == "header"]
    for hi, b_idx in enumerate(header_indices):
        hit = boundaries[b_idx]
        # Next structural boundary after this header
        next_boundary: Optional[_Hit] = None
        for j in range(b_idx + 1, len(boundaries)):
            cand = boundaries[j]
            if cand.kind in ("header", "folder", "percent"):
                next_boundary = cand
                break

        if next_boundary is not None:
            line_end = next_boundary.line_no - 1
            byte_end = next_boundary.byte_start
        else:
            line_end = last_line_no
            byte_end = eof_byte

        if line_end < hit.line_no:
            line_end = hit.line_no

        instances.append(
            ProgramInstance(
                program_number=hit.program_number or "",
                part_number=hit.part_number,
                machine_id=machine_id,
                backup_date=backup_date,
                date_source=date_source,
                source_path=source_path,
                source_type=source_type,
                line_start=hit.line_no,
                line_end=line_end,
                byte_start=hit.byte_start,
                byte_end=byte_end,
                machine_label=machine_label,
                machine_folder_raw=machine_folder_raw,
                date_folder_raw=date_folder_raw,
                folder_path=hit.folder_path,
                control_family=control_family,
                source_mtime=mtime,
                source_size=size,
                content_sha256=digest,
                parser_id=parser_id,
                parser_version=PARSER_VERSION,
                parse_status="ok",
                header_kind=hit.header_kind,
            )
        )
    return instances
