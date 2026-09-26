"""Layout-aware backup tree scanner.

Read-only against the backup tree: locators open sources as ``rb`` only.
Index/Excel outputs go to the user-chosen target folder, never into the backup.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

from gcode_index.aliases import AliasMap, normalize_folder_name
from gcode_index.birthtime import file_mtime
from gcode_index.folder_map import FolderMachineMap
from gcode_index.locators.fanuc_all_fldr import locate_fanuc_all_fldr
from gcode_index.locators.fanuc_all_prog import locate_fanuc_all_prog
from gcode_index.locators.haas_pgm import locate_haas_pgm
from gcode_index.locators.whole_file_nc import locate_whole_file_nc
from gcode_index.models import (
    PROVENANCE_BACKUP,
    PROVENANCE_EXTRA,
    FileSeen,
    MachineInfo,
    ScanResult,
    UnknownFolder,
)
from gcode_index.scan_cache import ScanCache
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

    def emit(
        self,
        *,
        phase: str,
        message: str,
        message_key: Optional[str] = None,
        message_kwargs: Optional[dict] = None,
    ) -> None:
        if not self.callback:
            return
        elapsed = time.monotonic() - self.t0
        eta = None
        if self.current > 0 and self.current < self.total:
            eta = elapsed / self.current * (self.total - self.current)
        payload = {
            "phase": phase,
            "message": message,
            "current": self.current,
            "total": self.total,
            "elapsed_s": elapsed,
            "eta_s": eta,
        }
        if message_key:
            payload["message_key"] = message_key
            payload["message_kwargs"] = dict(message_kwargs or {})
        self.callback(payload)

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


def _resolve_machine(
    folder_raw: str,
    aliases: AliasMap,
    folder_map: Optional[FolderMachineMap] = None,
) -> MachineInfo:
    """Folder map wins; then aliases; else unmapped."""
    if folder_map is not None:
        mapped = folder_map.resolve(folder_raw, aliases)
        if mapped is not None:
            return mapped
    return aliases.resolve(folder_raw)


def scan_backup_tree(
    backup_root: Path | str,
    aliases: AliasMap,
    *,
    progress: Optional[ProgressCallback] = None,
    folder_map: Optional[FolderMachineMap] = None,
    provenance: str = PROVENANCE_BACKUP,
    cache: Optional[ScanCache] = None,
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
                "message_key": "scan_counting",
                "current": 0,
                "total": 0,
                "elapsed_s": 0.0,
                "eta_s": None,
            }
        )
    total = _count_indexable_files(root)
    prog = _ScanProgress(progress, total)
    prog.emit(
        phase="scanning",
        message=f"Scanning 0 / {total} files…",
        message_key="scan_progress",
        message_kwargs={"current": 0, "total": total},
    )
    scan_root_s = str(root)

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
                folder_map=folder_map,
                cache=cache,
                scan_root=scan_root_s,
            )

    # Individual .nc / .nc.copy: whole tree from backup root (any depth)
    _index_all_nc_files(
        root,
        aliases,
        result,
        prog=prog,
        folder_map=folder_map,
        cache=cache,
        scan_root=scan_root_s,
    )

    _stamp_provenance(result, provenance=provenance, scan_root=root)

    prog.emit(
        phase="done",
        message=f"Scan complete — {prog.current} / {prog.total} files",
        message_key="scan_complete_files",
        message_kwargs={"current": prog.current, "total": prog.total},
    )
    return result


def scan_with_extra_roots(
    backup_root: Path | str,
    aliases: AliasMap,
    *,
    extra_roots: Optional[list[Path | str]] = None,
    root_specs: Optional[list[tuple[Path | str, str] | object]] = None,
    progress: Optional[ProgressCallback] = None,
    folder_map: Optional[FolderMachineMap] = None,
    cache: Optional[ScanCache] = None,
) -> ScanResult:
    """Scan the main backup (green) plus optional additional folders.

    ``extra_roots`` are tagged yellow (``provenance=extra``) for backward compatibility.
    ``root_specs`` is a list of ``(path, provenance)`` or objects with ``.path`` / ``.provenance``
    (e.g. ``ScanRootSpec``) so catch folders can be green (``backup``).
    """
    roots: list[tuple[Path, str]] = [(Path(backup_root), PROVENANCE_BACKUP)]
    seen: set[str] = {str(Path(backup_root).resolve())}

    def _add(path_raw: Path | str, provenance: str) -> None:
        p = Path(path_raw)
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key in seen:
            return
        if not p.is_dir():
            log.warning("extra scan root skipped (not a directory): %s", p)
            return
        seen.add(key)
        prov = (
            PROVENANCE_BACKUP
            if str(provenance).casefold() in ("backup", "green")
            else PROVENANCE_EXTRA
        )
        roots.append((p, prov))

    for item in root_specs or []:
        if isinstance(item, tuple) and len(item) == 2:
            _add(item[0], str(item[1]))
        elif hasattr(item, "path") and hasattr(item, "provenance"):
            _add(getattr(item, "path"), str(getattr(item, "provenance")))
        else:
            _add(item, PROVENANCE_EXTRA)  # type: ignore[arg-type]

    for raw in extra_roots or []:
        _add(raw, PROVENANCE_EXTRA)

    merged = ScanResult()
    for i, (root_path, prov) in enumerate(roots):
        if prov == PROVENANCE_BACKUP and i == 0:
            label = "backup"
        elif prov == PROVENANCE_BACKUP:
            label = f"green {i}"
        else:
            label = f"extra {i}"
        if progress:
            progress(
                {
                    "phase": "scanning",
                    "message": f"Scanning {label}: {root_path}…",
                    "message_key": "scan_root_progress",
                    "message_kwargs": {"label": label, "root": str(root_path)},
                    "current": 0,
                    "total": 0,
                    "elapsed_s": 0.0,
                    "eta_s": None,
                }
            )
        part = scan_backup_tree(
            root_path,
            aliases,
            progress=progress,
            folder_map=folder_map,
            provenance=prov,
            cache=cache,
        )
        merged.instances.extend(part.instances)
        merged.files_seen.extend(part.files_seen)
        merged.unknowns.extend(part.unknowns)

    if progress:
        n_bak = sum(1 for inst in merged.instances if inst.provenance == PROVENANCE_BACKUP)
        n_ext = sum(1 for inst in merged.instances if inst.provenance == PROVENANCE_EXTRA)
        n_cached = sum(1 for fs in merged.files_seen if fs.status == "cached")
        progress(
            {
                "phase": "done",
                "message": (
                    f"Scan complete — {len(merged.instances)} programs "
                    f"({n_bak} backup / green, {n_ext} extra / yellow"
                    f"{f', {n_cached} files reused' if n_cached else ''})"
                ),
                "message_key": "scan_complete_programs",
                "message_kwargs": {
                    "n": len(merged.instances),
                    "roots": len(roots),
                },
                "current": len(merged.instances),
                "total": max(len(merged.instances), 1),
                "elapsed_s": 0.0,
                "eta_s": None,
            }
        )
    return merged


def _stamp_provenance(
    result: ScanResult,
    *,
    provenance: str,
    scan_root: Path,
) -> None:
    root_s = str(scan_root.resolve())
    for inst in result.instances:
        inst.provenance = provenance
        inst.scan_root = root_s


def _scan_machine_folder_dumps(
    *,
    machine_dir: Path,
    root: Path,
    date_folder_raw: str,
    aliases: AliasMap,
    result: ScanResult,
    prog: Optional[_ScanProgress] = None,
    folder_map: Optional[FolderMachineMap] = None,
    cache: Optional[ScanCache] = None,
    scan_root: str = "",
) -> None:
    """Index glued dumps (.pgm / ALL-FLDR / ALL-PROG).

    Unmapped folders still get dumps indexed as MACHINE UNKNOWN (same idea as
    tree-wide .nc) so a slightly odd folder name does not hide all programs.
    """
    machine_folder_raw = machine_dir.name
    info = _resolve_machine(machine_folder_raw, aliases, folder_map)

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
            _index_pgm(
                path, root, date_folder_raw, info, result,
                cache=cache, scan_root=scan_root,
            )
            indexed_any = True
            if prog:
                prog.tick(f"Indexing {rel_path(path, root)}")
        elif _basename_is(path, "ALL-FLDR.TXT"):
            _index_all_fldr(
                path, root, date_folder_raw, info, result,
                cache=cache, scan_root=scan_root,
            )
            indexed_any = True
            if prog:
                prog.tick(f"Indexing {rel_path(path, root)}")
        elif _basename_is(path, "ALL-PROG.TXT"):
            _index_all_prog(
                path, root, date_folder_raw, info, result,
                cache=cache, scan_root=scan_root,
            )
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
    folder_map: Optional[FolderMachineMap] = None,
) -> Tuple[MachineInfo, Optional[str]]:
    """Resolve a machine folder from the path; never invent an assignment.

    Walk ancestor folders deepest→shallowest. First name that maps via folder
    map or aliases wins, so a machine-named folder applies to all files in that
    folder and its subfolders; a deeper machine folder overrides a shallower one.

    Structural dirs (``Memory``, ``HaasBackup(*)``) are skipped. Unmatched →
    MACHINE UNKNOWN.

    Returns (MachineInfo, date_folder_raw).
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

    ancestors = [p for p in parts[:-1] if not _is_structural_dir_name(p)]
    # Deepest first so VF2S/jobs/x.nc → VF2S and date/VF2S/UMC750/x.nc → UMC750
    for name in reversed(ancestors):
        info = _resolve_machine(name, aliases, folder_map)
        if not info.mapped:
            continue
        date_out: Optional[str] = None
        if len(parts) >= 3 and name != parts[0]:
            # Classic-ish: first component is a date (or other non-machine parent)
            # only when it does not itself map as a machine.
            top = _resolve_machine(parts[0], aliases, folder_map)
            if not top.mapped:
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
    # If the only ancestor is itself a non-mapping top folder used as "date", keep it
    if date_out is not None:
        top = _resolve_machine(date_out, aliases, folder_map)
        if top.mapped:
            date_out = None
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
    folder_map: Optional[FolderMachineMap] = None,
    cache: Optional[ScanCache] = None,
    scan_root: str = "",
) -> None:
    """Walk entire backup tree for *.nc / *.nc.copy.

    Machine is taken from the deepest ancestor folder that matches a folder map
    or alias (inherited by subfolders); else MACHINE UNKNOWN.
    """
    seen: set[Path] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not _is_nc_like(path):
            continue
        rp = path.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        _index_one_nc(
            path, root, aliases, result,
            folder_map=folder_map, cache=cache, scan_root=scan_root,
        )
        if prog:
            prog.tick(f"Indexing {rel_path(path, root)}")


def _index_one_nc(
    path: Path,
    root: Path,
    aliases: AliasMap,
    result: ScanResult,
    *,
    folder_map: Optional[FolderMachineMap] = None,
    cache: Optional[ScanCache] = None,
    scan_root: str = "",
) -> None:
    sp = rel_path(path, root)
    if cache is not None:
        reused = cache.try_reuse(path, scan_root=scan_root, source_path=sp)
        if reused is not None:
            instances, seen = reused
            result.instances.extend(instances)
            result.files_seen.append(seen)
            return

    parts = _path_parts_under_root(path, root)
    info, date_folder_raw = _infer_machine_and_date(
        path, root, aliases, folder_map=folder_map
    )
    is_copy = _is_nc_copy(path)
    source_type = _classify_nc_source_type(parts, info, is_copy=is_copy)
    folder_under = (
        _folder_under_memory(parts)
        if source_type in {"haas_ngc_nc", "haas_ngc_nc_copy"}
        else None
    )

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
    *,
    cache: Optional[ScanCache] = None,
    scan_root: str = "",
) -> None:
    sp = rel_path(path, root)
    if cache is not None:
        reused = cache.try_reuse(path, scan_root=scan_root, source_path=sp)
        if reused is not None:
            instances, seen = reused
            result.instances.extend(instances)
            result.files_seen.append(seen)
            return
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
    *,
    cache: Optional[ScanCache] = None,
    scan_root: str = "",
) -> None:
    sp = rel_path(path, root)
    if cache is not None:
        reused = cache.try_reuse(path, scan_root=scan_root, source_path=sp)
        if reused is not None:
            instances, seen = reused
            result.instances.extend(instances)
            result.files_seen.append(seen)
            return
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
    *,
    cache: Optional[ScanCache] = None,
    scan_root: str = "",
) -> None:
    sp = rel_path(path, root)
    if cache is not None:
        reused = cache.try_reuse(path, scan_root=scan_root, source_path=sp)
        if reused is not None:
            instances, seen = reused
            result.instances.extend(instances)
            result.files_seen.append(seen)
            return
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
