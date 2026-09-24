"""Layout-aware backup tree scanner."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

from gcode_index.aliases import AliasMap, normalize_folder_name
from gcode_index.birthtime import file_mtime
from gcode_index.locators.fanuc_all_fldr import locate_fanuc_all_fldr
from gcode_index.locators.fanuc_all_prog import locate_fanuc_all_prog
from gcode_index.locators.haas_pgm import locate_haas_pgm
from gcode_index.locators.whole_file_nc import locate_whole_file_nc
from gcode_index.models import FileSeen, MachineInfo, ScanResult, UnknownFolder

log = logging.getLogger("gcode_index.scanner")

_HAAS_BACKUP_DIR = re.compile(r"^HaasBackup\(.*\)$", re.IGNORECASE)

# Authoritative (user 2026-09-23): do not force machine assignment for orphan .nc
UNKNOWN_MACHINE_ID = "unknown"
UNKNOWN_MACHINE_LABEL = "MACHINE UNKNOWN"

ProgressCallback = Callable[[dict], None]


class _ScanProgress:
    """Lightweight progress reporter for GUI / CLI."""

    def __init__(self, callback: Optional[ProgressCallback], total: int) -> None:
        self.callback = callback
        self.total = max(total, 1)
        self.current = 0
        self.t0 = time.monotonic()

    def emit(self, *, phase: str, message: str) -> None:
        if not self.callback:
            return
        elapsed = time.monotonic() - self.t0
        eta = None
        if self.current > 0 and self.current < self.total:
            eta = elapsed / self.current * (self.total - self.current)
        self.callback(
            {
                "phase": phase,
                "message": message,
                "current": self.current,
                "total": self.total,
                "elapsed_s": elapsed,
                "eta_s": eta,
            }
        )

    def tick(self, message: str) -> None:
        self.current += 1
        self.emit(phase="scanning", message=message)


def rel_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _is_nc(path: Path) -> bool:
    return path.suffix.lower() == ".nc"


def _is_nc_copy(path: Path) -> bool:
    """Haas NGC edited/backup sibling: ``*.nc.copy`` (suffix is ``.copy``, not ``.nc``)."""
    return path.name.lower().endswith(".nc.copy")


def _is_nc_like(path: Path) -> bool:
    return _is_nc(path) or _is_nc_copy(path)


def _is_pgm(path: Path) -> bool:
    return path.suffix.lower() == ".pgm"


def _basename_is(path: Path, name: str) -> bool:
    return path.name.upper() == name.upper()


def _count_indexable_files(root: Path) -> int:
    """Count dump + .nc / .nc.copy files we expect to touch (for progress denominator)."""
    n = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if (
            _is_nc_like(path)
            or _is_pgm(path)
            or _basename_is(path, "ALL-FLDR.TXT")
            or _basename_is(path, "ALL-PROG.TXT")
        ):
            n += 1
    return n


def scan_backup_tree(
    backup_root: Path | str,
    aliases: AliasMap,
    *,
    progress: Optional[ProgressCallback] = None,
) -> ScanResult:
    root = Path(backup_root).resolve()
    result = ScanResult()
    if not root.is_dir():
        raise NotADirectoryError(f"backup root is not a directory: {root}")

    if progress:
        progress(
            {
                "phase": "counting",
                "message": "Counting source files…",
                "current": 0,
                "total": 0,
                "elapsed_s": 0.0,
                "eta_s": None,
            }
        )
    total = _count_indexable_files(root)
    prog = _ScanProgress(progress, total)
    prog.emit(phase="scanning", message=f"Scanning 0 / {total} files…")

    # date → machine: glued dumps (.pgm / ALL-FLDR / ALL-PROG) + unknown-folder log
    for date_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        date_folder_raw = date_dir.name
        for machine_dir in sorted(p for p in date_dir.iterdir() if p.is_dir()):
            _scan_machine_folder_dumps(
                machine_dir=machine_dir,
                root=root,
                date_folder_raw=date_folder_raw,
                aliases=aliases,
                result=result,
                prog=prog,
            )

    # Individual .nc / .nc.copy: whole tree from backup root (any depth)
    _index_all_nc_files(root, aliases, result, prog=prog)

    prog.emit(
        phase="done",
        message=f"Scan complete — {prog.current} / {prog.total} files",
    )
    return result


def _scan_machine_folder_dumps(
    *,
    machine_dir: Path,
    root: Path,
    date_folder_raw: str,
    aliases: AliasMap,
    result: ScanResult,
    prog: Optional[_ScanProgress] = None,
) -> None:
    """Index glued dumps (.pgm / ALL-FLDR / ALL-PROG).

    Unmapped folders still get dumps indexed as MACHINE UNKNOWN (same idea as
    tree-wide .nc) so a slightly odd folder name does not hide all programs.
    """
    machine_folder_raw = machine_dir.name
    info = aliases.resolve(machine_folder_raw)

    if not info.mapped:
        key = normalize_folder_name(machine_folder_raw)
        log.warning(
            "unknown machine folder %r (normalized=%r) under %s — "
            "glued dumps indexed as %s; .nc still handled tree-wide",
            machine_folder_raw,
            key,
            date_folder_raw,
            UNKNOWN_MACHINE_LABEL,
        )
        result.unknowns.append(
            UnknownFolder(
                date_folder_raw=date_folder_raw,
                machine_folder_raw=machine_folder_raw,
                normalized_key=key,
            )
        )
        info = MachineInfo(
            machine_id=UNKNOWN_MACHINE_ID,
            label=UNKNOWN_MACHINE_LABEL,
            machine_folder_raw=machine_folder_raw,
            mapped=False,
        )

    indexed_any = False
    for path in sorted(machine_dir.rglob("*")):
        if not path.is_file():
            continue
        if _is_pgm(path):
            _index_pgm(path, root, date_folder_raw, info, result)
            indexed_any = True
            if prog:
                prog.tick(f"Indexing {rel_path(path, root)}")
        elif _basename_is(path, "ALL-FLDR.TXT"):
            _index_all_fldr(path, root, date_folder_raw, info, result)
            indexed_any = True
            if prog:
                prog.tick(f"Indexing {rel_path(path, root)}")
        elif _basename_is(path, "ALL-PROG.TXT"):
            _index_all_prog(path, root, date_folder_raw, info, result)
            indexed_any = True
            if prog:
                prog.tick(f"Indexing {rel_path(path, root)}")

    if not indexed_any and info.mapped:
        # .nc may still be picked up by tree-wide pass; note dump absence only
        result.files_seen.append(
            FileSeen(
                source_path=rel_path(machine_dir, root),
                source_type=None,
                size=None,
                mtime=None,
                status="skipped",
                note=f"mapped machine ({info.machine_id}) but no glued dump found",
            )
        )


def _path_parts_under_root(path: Path, root: Path) -> Tuple[str, ...]:
    try:
        return path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return path.parts


def _is_structural_dir_name(name: str) -> bool:
    if name.lower() == "memory":
        return True
    if _HAAS_BACKUP_DIR.match(name):
        return True
    return False


def _under_haas_memory(parts: Tuple[str, ...]) -> bool:
    """True if path contains …/HaasBackup(*)/Memory/… before the filename."""
    for i, part in enumerate(parts[:-1]):
        if _HAAS_BACKUP_DIR.match(part):
            if i + 1 < len(parts) - 1 and parts[i + 1].lower() == "memory":
                return True
    return False


def _folder_under_memory(parts: Tuple[str, ...]) -> Optional[str]:
    for i, part in enumerate(parts[:-1]):
        if _HAAS_BACKUP_DIR.match(part):
            if i + 1 < len(parts) - 1 and parts[i + 1].lower() == "memory":
                under = parts[i + 2 : -1]
                if under:
                    return "/".join(under)
                return None
    return None


def _infer_machine_and_date(
    path: Path,
    root: Path,
    aliases: AliasMap,
) -> Tuple[MachineInfo, Optional[str]]:
    """Fuzzy-match a machine folder from the path; never invent an assignment.

    Returns (MachineInfo, date_folder_raw). Unmatched → MACHINE UNKNOWN.
    """
    parts = _path_parts_under_root(path, root)
    if not parts:
        return (
            MachineInfo(
                machine_id=UNKNOWN_MACHINE_ID,
                label=UNKNOWN_MACHINE_LABEL,
                mapped=False,
            ),
            None,
        )

    # Conventional layout: <date>/<machine>/...
    date_folder_raw: Optional[str] = None
    if len(parts) >= 2:
        # first component is a directory name when file is nested
        date_folder_raw = parts[0]

    candidates: list[str] = []
    # Prefer classic machine slot (second path component)
    if len(parts) >= 3:
        candidates.append(parts[1])
    # Root-level nest: <maybe-machine>/file.nc
    elif len(parts) == 2:
        candidates.append(parts[0])

    for part in parts[:-1]:
        if part in candidates:
            continue
        if date_folder_raw and part == date_folder_raw:
            continue
        if _is_structural_dir_name(part):
            continue
        candidates.append(part)

    for name in candidates:
        info = aliases.resolve(name)
        if info.mapped:
            # date folder only when classic date/machine/... and machine is 2nd slot
            date_out: Optional[str] = None
            if len(parts) >= 3 and name == parts[1]:
                date_out = parts[0]
            elif len(parts) >= 3 and name != parts[0]:
                date_out = parts[0]
            return (
                MachineInfo(
                    machine_id=info.machine_id,
                    label=info.label,
                    control_family=info.control_family,
                    layout=info.layout,
                    machine_folder_raw=name,
                    mapped=True,
                ),
                date_out,
            )

    # No fuzzy hit — do not force
    raw_guess = parts[1] if len(parts) >= 3 else (parts[0] if len(parts) >= 2 else None)
    date_out = parts[0] if len(parts) >= 3 else None
    return (
        MachineInfo(
            machine_id=UNKNOWN_MACHINE_ID,
            label=UNKNOWN_MACHINE_LABEL,
            machine_folder_raw=raw_guess,
            mapped=False,
        ),
        date_out,
    )


def _classify_nc_source_type(
    parts: Tuple[str, ...],
    info: MachineInfo,
    *,
    is_copy: bool = False,
) -> str:
    if _under_haas_memory(parts):
        return "haas_ngc_nc_copy" if is_copy else "haas_ngc_nc"
    layout = (info.layout or "").lower() if info.mapped else ""
    if layout == "manual_nc_folder":
        return "manual_nc_folder_copy" if is_copy else "manual_nc_folder"
    return "loose_nc_copy" if is_copy else "loose_nc"


def _index_all_nc_files(
    root: Path,
    aliases: AliasMap,
    result: ScanResult,
    *,
    prog: Optional[_ScanProgress] = None,
) -> None:
    """Walk entire backup tree for *.nc / *.nc.copy; fuzzy-match machine or leave unknown."""
    seen: set[Path] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not _is_nc_like(path):
            continue
        rp = path.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        _index_one_nc(path, root, aliases, result)
        if prog:
            prog.tick(f"Indexing {rel_path(path, root)}")


def _index_one_nc(
    path: Path,
    root: Path,
    aliases: AliasMap,
    result: ScanResult,
) -> None:
    parts = _path_parts_under_root(path, root)
    info, date_folder_raw = _infer_machine_and_date(path, root, aliases)
    is_copy = _is_nc_copy(path)
    source_type = _classify_nc_source_type(parts, info, is_copy=is_copy)
    folder_under = (
        _folder_under_memory(parts)
        if source_type in {"haas_ngc_nc", "haas_ngc_nc_copy"}
        else None
    )
    sp = rel_path(path, root)

    if not info.mapped:
        log.info(
            "indexing %s %s with %s (no fuzzy machine match)",
            ".nc.copy" if is_copy else ".nc",
            sp,
            UNKNOWN_MACHINE_LABEL,
        )

    control = info.control_family
    if control is None and source_type in {"haas_ngc_nc", "haas_ngc_nc_copy"}:
        control = "haas"
    elif control is None and source_type in {"manual_nc_folder", "manual_nc_folder_copy"}:
        control = "sinumerik"

    inst = locate_whole_file_nc(
        path,
        source_path=sp,
        source_type=source_type,
        machine_id=info.machine_id,
        machine_label=info.label,
        machine_folder_raw=info.machine_folder_raw,
        date_folder_raw=date_folder_raw,
        control_family=control,
        folder_path=folder_under,
        parser_id=source_type,
    )
    result.instances.append(inst)
    notes: list[str] = []
    if is_copy:
        notes.append("Haas NGC .nc.copy")
    if not info.mapped:
        notes.append(UNKNOWN_MACHINE_LABEL)
    result.files_seen.append(
        FileSeen(
            source_path=sp,
            source_type=source_type,
            size=inst.source_size,
            mtime=inst.source_mtime,
            status="indexed",
            note="; ".join(notes) if notes else None,
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
