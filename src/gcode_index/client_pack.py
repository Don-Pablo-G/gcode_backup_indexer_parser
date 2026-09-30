"""Client export pack — zip/folder of DB + sidecars a Work PC needs to read finds.

Never includes local ``gcode-index.ini``, locks, teach caches, or ``can_index``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence

from gcode_index import PARSER_VERSION, __version__
from gcode_index.aliases import LOCAL_ALIASES_FILENAME
from gcode_index.extra_roots import EXTRA_ROOTS_FILENAME
from gcode_index.folder_colour_aliases import FOLDER_COLOUR_ALIASES_FILENAME
from gcode_index.folder_map import MAP_FILENAME
from gcode_index.folder_tree_map import TREE_MAP_FILENAME
from gcode_index.header_token_freq import HEADER_TOKEN_FREQ_FILENAME
from gcode_index.i18n import UI_SETTINGS_FILENAME
from gcode_index.indexer_lock import LOCK_FILENAME as INDEXER_LOCK_FILENAME
from gcode_index.indexer_settings import INDEXER_SETTINGS_FILENAME
from gcode_index.odbiorca_aliases import ODBIORCY_FILENAME
from gcode_index.presets import PRESETS_FILENAME, VIEWS_FILENAME
from gcode_index.scan_history import HISTORY_FILENAME

log = logging.getLogger(__name__)

DEFAULT_DB_NAME = "gcode_index.sqlite"
CLIENT_PACK_ZIP_NAME = "gcode-index-client-pack.zip"
PACK_MANIFEST_FILENAME = "pack-manifest.json"
EXCEL_FILENAME = "gcode_index.xlsx"

# Required for a truthful Work pack (fail export if missing).
MANDATORY_PACK_FILES: tuple[str, ...] = (
    DEFAULT_DB_NAME,
    FOLDER_COLOUR_ALIASES_FILENAME,
)

# Included when present on disk.
OPTIONAL_PACK_FILES: tuple[str, ...] = (
    TREE_MAP_FILENAME,
    ODBIORCY_FILENAME,
    LOCAL_ALIASES_FILENAME,
    VIEWS_FILENAME,
    PRESETS_FILENAME,
    EXTRA_ROOTS_FILENAME,
    INDEXER_SETTINGS_FILENAME,
    MAP_FILENAME,
    UI_SETTINGS_FILENAME,
)

# Never ship these in a client pack.
NEVER_PACK_FILES: frozenset[str] = frozenset(
    {
        "gcode-index.ini",
        "operator.lock",
        "can_index.lock",
        INDEXER_LOCK_FILENAME,
        HEADER_TOKEN_FREQ_FILENAME,
        HISTORY_FILENAME,
        CLIENT_PACK_ZIP_NAME,
        # temp / editor debris
        f"{CLIENT_PACK_ZIP_NAME}.tmp",
        f"{PACK_MANIFEST_FILENAME}.tmp",
    }
)

# Live folder watch list for Work soft sync (sqlite + catalogues).
WATCHED_PACK_FILES: tuple[str, ...] = (
    DEFAULT_DB_NAME,
    FOLDER_COLOUR_ALIASES_FILENAME,
    TREE_MAP_FILENAME,
    ODBIORCY_FILENAME,
    LOCAL_ALIASES_FILENAME,
    VIEWS_FILENAME,
    PRESETS_FILENAME,
    PACK_MANIFEST_FILENAME,
)


@dataclass
class PackValidation:
    """Result of checking a database folder before export."""

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PackFile:
    """One file selected for the pack."""

    name: str
    path: Path
    size: int
    mtime: float
    sha256: str
    mandatory: bool = False


@dataclass
class PackExportResult:
    """Outcome of building a zip and/or folder pack."""

    ok: bool
    files: list[PackFile] = field(default_factory=list)
    zip_path: Optional[Path] = None
    folder_path: Optional[Path] = None
    manifest_path: Optional[Path] = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    byte_size: int = 0


def default_pack_zip_path(target: Path | str) -> Path:
    return Path(target) / CLIENT_PACK_ZIP_NAME


def validate_pack_source(target: Path | str) -> PackValidation:
    """Fail when sqlite or colour sidecar is missing."""
    dest = Path(target)
    errors: list[str] = []
    warnings: list[str] = []
    if not dest.is_dir():
        return PackValidation(ok=False, errors=[f"not a directory: {dest}"])
    for name in MANDATORY_PACK_FILES:
        if not (dest / name).is_file():
            errors.append(f"missing mandatory file: {name}")
    for name in (
        TREE_MAP_FILENAME,
        ODBIORCY_FILENAME,
        LOCAL_ALIASES_FILENAME,
        VIEWS_FILENAME,
        EXTRA_ROOTS_FILENAME,
        INDEXER_SETTINGS_FILENAME,
    ):
        if not (dest / name).is_file():
            warnings.append(f"optional file absent: {name}")
    return PackValidation(ok=not errors, errors=errors, warnings=warnings)


def _file_sha256(path: Path, *, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _stat_pack_file(path: Path, *, mandatory: bool) -> Optional[PackFile]:
    try:
        st = path.stat()
    except OSError:
        return None
    if not path.is_file():
        return None
    try:
        digest = _file_sha256(path)
    except OSError as exc:
        log.warning("hash failed for %s: %s", path, exc)
        return None
    return PackFile(
        name=path.name,
        path=path,
        size=int(st.st_size),
        mtime=float(st.st_mtime),
        sha256=digest,
        mandatory=mandatory,
    )


def collect_pack_files(
    target: Path | str,
    *,
    include_excel: bool = False,
) -> tuple[list[PackFile], PackValidation]:
    """Select files from the database folder for the client pack."""
    dest = Path(target)
    validation = validate_pack_source(dest)
    if not validation.ok:
        return [], validation

    selected: list[PackFile] = []
    seen: set[str] = set()

    def _add(name: str, *, mandatory: bool) -> None:
        if name in seen or name in NEVER_PACK_FILES:
            return
        pf = _stat_pack_file(dest / name, mandatory=mandatory)
        if pf is None:
            return
        seen.add(name)
        selected.append(pf)

    for name in MANDATORY_PACK_FILES:
        _add(name, mandatory=True)
    for name in OPTIONAL_PACK_FILES:
        _add(name, mandatory=False)
    if include_excel:
        _add(EXCEL_FILENAME, mandatory=False)

    # Prefer views.yaml; still allow legacy presets when views absent.
    if VIEWS_FILENAME in seen and PRESETS_FILENAME in seen:
        selected = [p for p in selected if p.name != PRESETS_FILENAME]
        seen.discard(PRESETS_FILENAME)

    return selected, validation


def build_manifest(
    files: Sequence[PackFile],
    *,
    exported_at: Optional[str] = None,
) -> dict:
    """Build ``pack-manifest.json`` payload (no can_index)."""
    when = exported_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "format": 1,
        "kind": "gcode-index-client-pack",
        "exported_at": when,
        "app_version": __version__,
        "parser_version": PARSER_VERSION,
        "files": [
            {
                "name": f.name,
                "size": f.size,
                "mtime": f.mtime,
                "sha256": f.sha256,
                "mandatory": bool(f.mandatory),
            }
            for f in files
        ],
    }


def _write_manifest_file(path: Path, manifest: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return path


def _copy_with_retry(src: Path, dest: Path, *, attempts: int = 5) -> None:
    last: Optional[BaseException] = None
    for i in range(max(1, attempts)):
        try:
            shutil.copy2(src, dest)
            return
        except OSError as exc:
            last = exc
            time.sleep(0.05 * (i + 1))
    assert last is not None
    raise last


def _stage_pack_files(
    files: Sequence[PackFile],
    staging: Path,
    *,
    manifest: dict,
) -> list[Path]:
    staging.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for pf in files:
        out = staging / pf.name
        _copy_with_retry(pf.path, out)
        written.append(out)
    man_path = staging / PACK_MANIFEST_FILENAME
    _write_manifest_file(man_path, manifest)
    written.append(man_path)
    return written


def export_client_pack_zip(
    target: Path | str,
    zip_path: Path | str | None = None,
    *,
    include_excel: bool = False,
) -> PackExportResult:
    """Build ``gcode-index-client-pack.zip`` (atomic temp → replace)."""
    dest = Path(target)
    out = Path(zip_path) if zip_path else default_pack_zip_path(dest)
    files, validation = collect_pack_files(dest, include_excel=include_excel)
    if not validation.ok:
        return PackExportResult(
            ok=False,
            errors=list(validation.errors),
            warnings=list(validation.warnings),
        )
    manifest = build_manifest(files)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="gcode-pack-") as tmp:
            staging = Path(tmp) / "pack"
            staged = _stage_pack_files(files, staging, manifest=manifest)
            tmp_zip = out.with_suffix(out.suffix + ".tmp")
            if tmp_zip.is_file():
                tmp_zip.unlink()
            with zipfile.ZipFile(
                tmp_zip, "w", compression=zipfile.ZIP_DEFLATED
            ) as zf:
                for path in staged:
                    zf.write(path, arcname=path.name)
            tmp_zip.replace(out)
        # Also drop manifest next to the live DB for Work soft sync.
        live_man = dest / PACK_MANIFEST_FILENAME
        _write_manifest_file(live_man, manifest)
        size = int(out.stat().st_size) if out.is_file() else 0
        return PackExportResult(
            ok=True,
            files=list(files),
            zip_path=out,
            manifest_path=live_man,
            warnings=list(validation.warnings),
            byte_size=size,
        )
    except OSError as exc:
        log.exception("export client pack zip failed")
        return PackExportResult(
            ok=False,
            files=list(files),
            errors=[str(exc)],
            warnings=list(validation.warnings),
        )


def export_client_pack_folder(
    target: Path | str,
    folder_path: Path | str,
    *,
    include_excel: bool = False,
) -> PackExportResult:
    """Copy the same file set into a destination folder (manual only)."""
    dest = Path(target)
    out_dir = Path(folder_path)
    files, validation = collect_pack_files(dest, include_excel=include_excel)
    if not validation.ok:
        return PackExportResult(
            ok=False,
            errors=list(validation.errors),
            warnings=list(validation.warnings),
        )
    manifest = build_manifest(files)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for pf in files:
            _copy_with_retry(pf.path, out_dir / pf.name)
        man_path = _write_manifest_file(out_dir / PACK_MANIFEST_FILENAME, manifest)
        # Refresh live manifest too (same revision signal for soft sync).
        live_man = dest / PACK_MANIFEST_FILENAME
        _write_manifest_file(live_man, manifest)
        total = sum(f.size for f in files)
        return PackExportResult(
            ok=True,
            files=list(files),
            folder_path=out_dir,
            manifest_path=man_path,
            warnings=list(validation.warnings),
            byte_size=total,
        )
    except OSError as exc:
        log.exception("export client pack folder failed")
        return PackExportResult(
            ok=False,
            files=list(files),
            errors=[str(exc)],
            warnings=list(validation.warnings),
        )


def snapshot_pack_mtimes(target: Path | str) -> dict[str, float]:
    """Map watched filename → mtime (missing files omitted)."""
    dest = Path(target)
    out: dict[str, float] = {}
    if not dest.is_dir():
        return out
    for name in WATCHED_PACK_FILES:
        path = dest / name
        try:
            if path.is_file():
                out[name] = float(path.stat().st_mtime)
        except OSError:
            continue
    return out


def pack_mtimes_changed(
    previous: Optional[dict[str, float]],
    current: dict[str, float],
    *,
    epsilon: float = 0.01,
) -> tuple[bool, bool, bool]:
    """Return ``(any_changed, db_changed, sidecar_changed)``.

    ``sidecar_changed`` is True when any non-sqlite watched file changed
    (including ``pack-manifest.json``).
    """
    prev = previous or {}
    if not current and not prev:
        return False, False, False
    keys = set(prev) | set(current)
    db_changed = False
    sidecar_changed = False
    for key in keys:
        a = prev.get(key)
        b = current.get(key)
        if a is None and b is None:
            continue
        if a is None or b is None or abs(float(b) - float(a)) > epsilon:
            if key == DEFAULT_DB_NAME:
                db_changed = True
            else:
                sidecar_changed = True
    return (db_changed or sidecar_changed), db_changed, sidecar_changed


def format_pack_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KiB"
    return f"{n / (1024 * 1024):.1f} MiB"


def never_pack_names() -> frozenset[str]:
    return NEVER_PACK_FILES


def is_packable_name(name: str) -> bool:
    return name not in NEVER_PACK_FILES
