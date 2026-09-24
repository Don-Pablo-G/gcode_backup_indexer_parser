from __future__ import annotations

from pathlib import Path
from typing import Iterable

from openpyxl import Workbook

from gcode_index.models import ProgramInstance

COLUMNS = [
    ("program_number", "Program #"),
    ("part_number", "Part #"),
    ("programmer", "Programmer"),
    ("machine_id", "Machine"),
    ("machine_label", "Machine label"),
    ("backup_date", "Date"),
    ("date_source", "Date source"),
    ("provenance", "Flag (backup/extra)"),
    ("scan_root", "Scan root"),
    ("source_type", "Source type"),
    ("source_path", "Source path"),
    ("line_start", "Line start"),
    ("line_end", "Line end"),
    ("byte_start", "Byte start"),
    ("byte_end", "Byte end"),
    ("source_size", "Source size"),
    ("content_sha256", "Content SHA-256"),
    ("folder_path", "Folder path"),
    ("date_folder_raw", "Date folder"),
    ("machine_folder_raw", "Machine folder"),
    ("control_family", "Control"),
    ("parse_status", "Status"),
]


def export_excel(path: Path | str, instances: Iterable[ProgramInstance]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "program_instances"
    ws.append([title for _, title in COLUMNS])
    for inst in instances:
        row = []
        for attr, _ in COLUMNS:
            val = getattr(inst, attr)
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            row.append(val)
        ws.append(row)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
