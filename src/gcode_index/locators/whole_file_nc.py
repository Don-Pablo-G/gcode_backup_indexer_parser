"""Whole-file .nc locators (NGC Memory, manual folder, loose)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from gcode_index import PARSER_VERSION
from gcode_index.birthtime import file_birth_or_mtime, file_mtime
from gcode_index.models import ProgramInstance


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
    """One .nc file = one instance. Program # from filename stem until samples exist."""
    p = Path(path)
    backup_date, date_source = file_birth_or_mtime(p)
    mtime = file_mtime(p)
    size = p.stat().st_size
    stem = p.stem
    return ProgramInstance(
        program_number=stem,
        part_number=None,
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
        parser_id=parser_id or source_type,
        parser_version=PARSER_VERSION,
        parse_status="ok",
        header_kind="filename",
    )
