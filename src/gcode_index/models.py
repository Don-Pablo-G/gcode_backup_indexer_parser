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
# UI: green = on machine; yellow = status unknown (never a role / never "fixture").
# ---------------------------------------------------------------------------
STATUS_ON_MACHINE = "backup"  # 🟢 on_machine
STATUS_UNKNOWN = "extra"  # 🟡 status unknown (legacy name: not_run)
STATUS_NOT_RUN = STATUS_UNKNOWN  # back-compat alias
STATUS_VALUES = (STATUS_ON_MACHINE, STATUS_UNKNOWN)

# Legacy aliases (pre-0.2.64 single-flag era)
PROVENANCE_BACKUP = STATUS_ON_MACHINE
PROVENANCE_EXTRA = STATUS_UNKNOWN
PROVENANCE_WIP = "wip"  # now a *role* id, not a status
PROVENANCE_VALUES = (PROVENANCE_BACKUP, PROVENANCE_EXTRA, PROVENANCE_WIP)

# ---------------------------------------------------------------------------
# Role = editable catalogue + folder aliases (never green/yellow status).
# Seed colours: blue=prototype, red=personal, orange=system, purple=fixture.
# ---------------------------------------------------------------------------
ROLE_PROTOTYPE = "prototype"
ROLE_PERSONAL = "personal"
ROLE_SYSTEM_PROGRAMS = "system_programs"
ROLE_FIXTURE = "fixture"
# Legacy role ids (kept for DB / YAML rows; no longer auto-seeded as builtins)
ROLE_PRODUCTION = "production"
ROLE_WIP = "wip"
ROLE_TEST = "test"
ROLE_SEED_IDS = (
    ROLE_PROTOTYPE,
    ROLE_PERSONAL,
    ROLE_SYSTEM_PROGRAMS,
    ROLE_FIXTURE,
)
ROLE_LEGACY_IDS = (ROLE_PRODUCTION, ROLE_WIP, ROLE_TEST)

# Path-role rule that skips indexing a folder branch (not stored on rows)
COLOUR_EXCLUDE = "exclude"


def is_o9_system_program(program_number: Optional[str]) -> bool:
    """True when program number is **O9000–O9099** (case-insensitive O).

    Accepts stored forms with or without a leading ``O`` (locators usually store
    digits only). Leading zeros after ``O`` are fine (``O09001`` → 9001).
    Numbers outside 9000–9099 (e.g. O9, O9100, O99999) do **not** match.
    """
    raw = (program_number or "").strip()
    if not raw:
        return False
    if raw[0] in "Oo":
        raw = raw[1:].lstrip()
    digits = []
    for ch in raw:
        if ch.isdigit():
            digits.append(ch)
        else:
            break
    if not digits:
        return False
    try:
        n = int("".join(digits))
    except ValueError:
        return False
    return 9000 <= n <= 9099


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
    # Status (ran on machine?): backup=on_machine 🟢, extra=status_unknown 🟡 — from roots only
    provenance: str = STATUS_ON_MACHINE
    # Role tags (prototype / personal / …) — CSV of catalogue ids; None = unset.
    # Multiple tags allowed (e.g. "fixture,personal"). Path tree map + name aliases.
    role: Optional[str] = None
    # Recipient / customer (odbiorca) — one id; name aliases + optional path override.
    odbiorca_id: Optional[str] = None
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
    # Optional scan-note counters (odbiorca assignment sources)
    odbiorca_from_folder: int = 0
    odbiorca_from_path: int = 0
    odbiorca_from_header: int = 0
    # Rows that received auto role system_programs from O9… program numbers
    o9_system_programs: int = 0
