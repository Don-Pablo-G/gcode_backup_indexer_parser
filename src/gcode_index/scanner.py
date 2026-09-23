"""Layout-aware backup tree scanner."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from gcode_index.aliases import AliasMap, normalize_folder_name
from gcode_index.birthtime import file_mtime
from gcode_index.locators.fanuc_all_fldr import locate_fanuc_all_fldr
from gcode_index.locators.fanuc_all_prog import locate_fanuc_all_prog
from gcode_index.locators.haas_pgm import locate_haas_pgm
from gcode_index.locators.whole_file_nc import locate_whole_file_nc
from gcode_index.models import FileSeen, MachineInfo, ScanResult, UnknownFolder

log = logging.getLogger("gcode_index.scanner")

_HAAS_BACKUP_DIR = re.compile(r"^HaasBackup\(.*\)$", re.IGNORECASE)


def rel_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _is_nc(path: Path) -> bool:
    return path.suffix.lower() == ".nc"


def _is_pgm(path: Path) -> bool:
    return path.suffix.lower() == ".pgm"


def _basename_is(path: Path, name: str) -> bool:
    return path.name.upper() == name.upper()


def scan_backup_tree(
    backup_root: Path | str,
    aliases: AliasMap,
) -> ScanResult:
    root = Path(backup_root).resolve()
    result = ScanResult()
    if not root.is_dir():
        raise NotADirectoryError(f"backup root is not a directory: {root}")

    # Loose .nc at backup root (not under date/machine)
    for child in sorted(root.iterdir()):
        if child.is_file() and _is_nc(child):
            _index_loose_nc(child, root, result)

    # date → machine
    for date_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        date_folder_raw = date_dir.name
        for machine_dir in sorted(p for p in date_dir.iterdir() if p.is_dir()):
            _scan_machine_folder(
                machine_dir=machine_dir,
                root=root,
                date_folder_raw=date_folder_raw,
                aliases=aliases,
                result=result,
            )

    return result


def _scan_machine_folder(
    *,
    machine_dir: Path,
    root: Path,
    date_folder_raw: str,
    aliases: AliasMap,
    result: ScanResult,
) -> None:
    machine_folder_raw = machine_dir.name
    info = aliases.resolve(machine_folder_raw)

    if not info.mapped:
        key = normalize_folder_name(machine_folder_raw)
        log.warning(
            "unknown machine folder %r (normalized=%r) under %s — not guessing locator",
            machine_folder_raw,
            key,
            date_folder_raw,
        )
        result.unknowns.append(
            UnknownFolder(
                date_folder_raw=date_folder_raw,
                machine_folder_raw=machine_folder_raw,
                normalized_key=key,
            )
        )
        # Still record that we saw the folder; do not invent locators.
        return

    layout = (info.layout or "").lower()

    # Prefer explicit layout routes; also pick up known dump filenames.
    indexed_any = False

    if layout == "haas_ngc" or layout == "haas_ngc_nc":
        indexed_any |= _scan_haas_ngc(
            machine_dir, root, date_folder_raw, info, result
        )
    elif layout == "manual_nc_folder":
        indexed_any |= _scan_manual_nc(
            machine_dir, root, date_folder_raw, info, result
        )

    # Filename-based routes (also for machines whose layout hints dump type)
    for path in sorted(machine_dir.rglob("*")):
        if not path.is_file():
            continue
        # Skip files already covered by NGC / manual routes when under those layouts
        if layout in ("haas_ngc", "haas_ngc_nc") and _is_under_haas_memory(path, machine_dir):
            continue
        if layout == "manual_nc_folder" and _is_nc(path):
            continue

        if _is_pgm(path):
            _index_pgm(path, root, date_folder_raw, info, result)
            indexed_any = True
        elif _basename_is(path, "ALL-FLDR.TXT"):
            _index_all_fldr(path, root, date_folder_raw, info, result)
            indexed_any = True
        elif _basename_is(path, "ALL-PROG.TXT"):
            _index_all_prog(path, root, date_folder_raw, info, result)
            indexed_any = True

    # Haas NGC path discovery even if layout not set (e.g. alias incomplete)
    if layout not in ("haas_ngc", "haas_ngc_nc"):
        if _find_haas_memory(machine_dir) is not None:
            indexed_any |= _scan_haas_ngc(
                machine_dir, root, date_folder_raw, info, result
            )

    if not indexed_any:
        result.files_seen.append(
            FileSeen(
                source_path=rel_path(machine_dir, root),
                source_type=None,
                size=None,
                mtime=None,
                status="skipped",
                note=f"mapped machine ({info.machine_id}) but no known dump/.nc found",
            )
        )


def _find_haas_memory(machine_dir: Path) -> Optional[Path]:
    for child in machine_dir.iterdir():
        if child.is_dir() and _HAAS_BACKUP_DIR.match(child.name):
            mem = child / "Memory"
            if mem.is_dir():
                return mem
    return None


def _is_under_haas_memory(path: Path, machine_dir: Path) -> bool:
    mem = _find_haas_memory(machine_dir)
    if mem is None:
        return False
    try:
        path.resolve().relative_to(mem.resolve())
        return True
    except ValueError:
        return False


def _scan_haas_ngc(
    machine_dir: Path,
    root: Path,
    date_folder_raw: str,
    info: MachineInfo,
    result: ScanResult,
) -> bool:
    mem = _find_haas_memory(machine_dir)
    if mem is None:
        result.files_seen.append(
            FileSeen(
                source_path=rel_path(machine_dir, root),
                source_type="haas_ngc_nc",
                size=None,
                mtime=None,
                status="skipped",
                note="Haas NGC layout expected but HaasBackup(*)/Memory not found",
            )
        )
        return False
    found = False
    for nc in sorted(mem.rglob("*.nc")) + sorted(mem.rglob("*.NC")):
        # rglob may double on case-insensitive FS; dedupe via resolve
        pass
    seen: set[Path] = set()
    for nc in sorted(mem.rglob("*")):
        if not nc.is_file() or not _is_nc(nc):
            continue
        rp = nc.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        found = True
        try:
            folder_under = nc.parent.relative_to(mem).as_posix()
            if folder_under == ".":
                folder_under = None
        except ValueError:
            folder_under = None
        sp = rel_path(nc, root)
        inst = locate_whole_file_nc(
            nc,
            source_path=sp,
            source_type="haas_ngc_nc",
            machine_id=info.machine_id,
            machine_label=info.label,
            machine_folder_raw=info.machine_folder_raw,
            date_folder_raw=date_folder_raw,
            control_family=info.control_family or "haas",
            folder_path=folder_under,
            parser_id="haas_ngc_nc",
        )
        result.instances.append(inst)
        result.files_seen.append(
            FileSeen(
                source_path=sp,
                source_type="haas_ngc_nc",
                size=inst.source_size,
                mtime=inst.source_mtime,
                status="indexed",
            )
        )
    return found


def _scan_manual_nc(
    machine_dir: Path,
    root: Path,
    date_folder_raw: str,
    info: MachineInfo,
    result: ScanResult,
) -> bool:
    found = False
    seen: set[Path] = set()
    for nc in sorted(machine_dir.rglob("*")):
        if not nc.is_file() or not _is_nc(nc):
            continue
        rp = nc.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        found = True
        sp = rel_path(nc, root)
        inst = locate_whole_file_nc(
            nc,
            source_path=sp,
            source_type="manual_nc_folder",
            machine_id=info.machine_id,
            machine_label=info.label,
            machine_folder_raw=info.machine_folder_raw,
            date_folder_raw=date_folder_raw,
            control_family=info.control_family or "sinumerik",
            parser_id="manual_nc_folder",
        )
        result.instances.append(inst)
        result.files_seen.append(
            FileSeen(
                source_path=sp,
                source_type="manual_nc_folder",
                size=inst.source_size,
                mtime=inst.source_mtime,
                status="indexed",
            )
        )
    return found


def _index_loose_nc(path: Path, root: Path, result: ScanResult) -> None:
    sp = rel_path(path, root)
    inst = locate_whole_file_nc(
        path,
        source_path=sp,
        source_type="loose_nc",
        machine_id="loose",
        machine_label="Loose .nc",
        control_family=None,
        parser_id="loose_nc",
    )
    result.instances.append(inst)
    result.files_seen.append(
        FileSeen(
            source_path=sp,
            source_type="loose_nc",
            size=inst.source_size,
            mtime=inst.source_mtime,
            status="indexed",
        )
    )


def _index_pgm(
    path: Path,
    root: Path,
    date_folder_raw: str,
    info: MachineInfo,
    result: ScanResult,
) -> None:
    sp = rel_path(path, root)
    try:
        instances = locate_haas_pgm(
            path,
            source_path=sp,
            machine_id=info.machine_id,
            machine_label=info.label,
            machine_folder_raw=info.machine_folder_raw,
            date_folder_raw=date_folder_raw,
            control_family=info.control_family or "haas",
        )
        result.instances.extend(instances)
        result.files_seen.append(
            FileSeen(
                source_path=sp,
                source_type="haas_pgm_glued",
                size=path.stat().st_size,
                mtime=file_mtime(path),
                status="indexed",
                note=f"{len(instances)} headers",
            )
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("failed to index %s", sp)
        result.files_seen.append(
            FileSeen(
                source_path=sp,
                source_type="haas_pgm_glued",
                size=None,
                mtime=None,
                status="error",
                note=str(exc),
            )
        )


def _index_all_fldr(
    path: Path,
    root: Path,
    date_folder_raw: str,
    info: MachineInfo,
    result: ScanResult,
) -> None:
    sp = rel_path(path, root)
    try:
        instances = locate_fanuc_all_fldr(
            path,
            source_path=sp,
            machine_id=info.machine_id,
            machine_label=info.label,
            machine_folder_raw=info.machine_folder_raw,
            date_folder_raw=date_folder_raw,
            control_family=info.control_family or "fanuc",
        )
        result.instances.extend(instances)
        result.files_seen.append(
            FileSeen(
                source_path=sp,
                source_type="fanuc_all_fldr",
                size=path.stat().st_size,
                mtime=file_mtime(path),
                status="indexed",
                note=f"{len(instances)} headers",
            )
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("failed to index %s", sp)
        result.files_seen.append(
            FileSeen(
                source_path=sp,
                source_type="fanuc_all_fldr",
                size=None,
                mtime=None,
                status="error",
                note=str(exc),
            )
        )


def _index_all_prog(
    path: Path,
    root: Path,
    date_folder_raw: str,
    info: MachineInfo,
    result: ScanResult,
) -> None:
    sp = rel_path(path, root)
    try:
        instances = locate_fanuc_all_prog(
            path,
            source_path=sp,
            machine_id=info.machine_id,
            machine_label=info.label,
            machine_folder_raw=info.machine_folder_raw,
            date_folder_raw=date_folder_raw,
            control_family=info.control_family or "fanuc",
        )
        result.instances.extend(instances)
        result.files_seen.append(
            FileSeen(
                source_path=sp,
                source_type="fanuc_all_prog",
                size=path.stat().st_size,
                mtime=file_mtime(path),
                status="indexed",
                note=f"{len(instances)} headers",
            )
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("failed to index %s", sp)
        result.files_seen.append(
            FileSeen(
                source_path=sp,
                source_type="fanuc_all_prog",
                size=None,
                mtime=None,
                status="error",
                note=str(exc),
            )
        )
