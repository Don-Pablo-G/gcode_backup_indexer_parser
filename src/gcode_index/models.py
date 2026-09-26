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

# ---------------------------------------------------------------------------
# Status = ran on machine? Derived from scan roots only (never folder aliases).
# Internal ids stay ``backup`` / ``extra`` for DB / root YAML compatibility.
# ---------------------------------------------------------------------------
STATUS_ON_MACHINE = "backup"  # 🟢 on_machine
STATUS_NOT_RUN = "extra"  # 🟡 not_run
STATUS_VALUES = (STATUS_ON_MACHINE, STATUS_NOT_RUN)

# Legacy aliases (pre-0.2.64 single-flag era)
PROVENANCE_BACKUP = STATUS_ON_MACHINE
PROVENANCE_EXTRA = STATUS_NOT_RUN
PROVENANCE_WIP = "wip"  # now a *role* id, not a status
PROVENANCE_VALUES = (PROVENANCE_BACKUP, PROVENANCE_EXTRA, PROVENANCE_WIP)

# ---------------------------------------------------------------------------
# Role = production / WIP / fixture / … Editable catalogue + folder aliases.
# ---------------------------------------------------------------------------
ROLE_PRODUCTION = "production"
ROLE_FIXTURE = "fixture"
ROLE_WIP = "wip"
ROLE_TEST = "test"
ROLE_PERSONAL = "personal"
ROLE_SEED_IDS = (
    ROLE_PRODUCTION,
    ROLE_FIXTURE,
    ROLE_WIP,
    ROLE_TEST,
    ROLE_PERSONAL,
)

# Path-role rule that skips indexing a folder branch (not stored on rows)
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
    # Whole source-file SHA-256 (integrity stamp for extract)
    content_sha256: Optional[str] = None
    # Normalized extracted program-body SHA-256 (duplicates / cross-source match)
    program_sha256: Optional[str] = None
    parser_id: Optional[str] = None
    parser_version: Optional[str] = None
    parse_status: str = "ok"
    error_message: Optional[str] = None
    header_kind: Optional[str] = None
    # Status (ran on machine?): backup=on_machine 🟢, extra=not_run 🟡 — from roots only
    provenance: str = STATUS_ON_MACHINE
    # Role (production / wip / …) — from folder-role aliases; None = unset
    role: Optional[str] = None
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
