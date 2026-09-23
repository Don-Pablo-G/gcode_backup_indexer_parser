"""FANUC ALL-PROG.TXT glued locator — sibling of ALL-FLDR (no &F= required)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from gcode_index.locators.fanuc_all_fldr import _locate_fanuc_glued

PARSER_ID = "fanuc_all_prog_glued"
SOURCE_TYPE = "fanuc_all_prog"

# Wider O pattern: multi-paren and optional trailing <name>
_O_HEADER = re.compile(r"^O(\d+)(?:\([^)]*\))*(?:<[^>]+>)?\s*$")
_ANGLE = re.compile(r"^<([^>]+)>(?:\([^)]*\))?\s*$")


def locate_fanuc_all_prog(
    path: Path | str,
    *,
    source_path: str,
    machine_id: str,
    machine_label: Optional[str] = None,
    machine_folder_raw: Optional[str] = None,
    date_folder_raw: Optional[str] = None,
    control_family: str = "fanuc",
) -> List:
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
        split_on_folder=True,  # optional &F= if ever present
        o_pattern=_O_HEADER,
        angle_pattern=_ANGLE,
        angle_multi_paren=False,
    )
