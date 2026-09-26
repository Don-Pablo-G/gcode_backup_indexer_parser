from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


SOURCE_TYPES = (
    "haas_pgm_glued",
    "fanuc_all_fldr",
    "fanuc_all_prog",
    "haas_ngc_nc",
    "manual_nc_folder",
    "loose_nc",
)

# Provenance / run flag:
# backup = green (ran on machine / catch);
# extra = yellow (additional folder, not from backup);
# wip = red (work-in-progress / not production-ready)
PROVENANCE_BACKUP = "backup"
PROVENANCE_EXTRA = "extra"
PROVENANCE_WIP = "wip"
PROVENANCE_VALUES = (PROVENANCE_BACKUP, PROVENANCE_EXTRA, PROVENANCE_WIP)

# Path-colour rule that skips indexing a folder branch (not stored on rows)
COLOUR_EXCLUDE = "exclude"


@dataclass
class MachineInfo:
    machine_id: str
    label: Optional[str] = None
    control_family: Optional[str] = None
    layout: Optional[str] = None
    machine_folder_raw: Optional[str] = None
    mapped: bool = True


@dataclass
class ProgramInstance:
    program_number: str
    part_number: Optional[str]
    machine_id: str
    backup_date: datetime
    date_source: str  # birth | mtime
    source_path: str
    source_type: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    byte_start: Optional[int] = None
    byte_end: Optional[int] = None
    machine_label: Optional[str] = None
    machine_folder_raw: Optional[str] = None
    date_folder_raw: Optional[str] = None
    folder_path: Optional[str] = None
    control_family: Optional[str] = None
    source_mtime: Optional[datetime] = None
    source_size: Optional[int] = None
    content_sha256: Optional[str] = None
    parser_id: Optional[str] = None
    parser_version: Optional[str] = None
    parse_status: str = "ok"
    error_message: Optional[str] = None
    header_kind: Optional[str] = None
    # backup = green; extra = yellow; wip = red (WIP / not production)
    provenance: str = PROVENANCE_BACKUP
    scan_root: Optional[str] = None
    # Next-line comment (LP1) / (MS1); null if absent or non-matching
    programmer: Optional[str] = None


@dataclass
class FileSeen:
    source_path: str
    source_type: Optional[str]
    size: Optional[int]
    mtime: Optional[datetime]
    status: str  # indexed | skipped | unknown | error
    note: Optional[str] = None


@dataclass
class UnknownFolder:
    date_folder_raw: str
    machine_folder_raw: str
    normalized_key: str
    note: str = "unmapped machine folder"


@dataclass
class ScanResult:
    instances: list[ProgramInstance] = field(default_factory=list)
    files_seen: list[FileSeen] = field(default_factory=list)
    unknowns: list[UnknownFolder] = field(default_factory=list)
