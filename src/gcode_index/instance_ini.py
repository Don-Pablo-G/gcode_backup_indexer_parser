"""Human-readable instance settings (``.ini``) for an installed GUI copy.

Stored next to ``gcode-index-gui.exe`` (frozen) or in the working directory (dev)
so operators reopen the app with the same backup / database / extract / scan-root
folders.
"""

from __future__ import annotations

import sys
from configparser import ConfigParser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from gcode_index.extra_roots import ScanRootSpec
from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA
from gcode_index.schedule import SCHEDULE_OFF, normalize_schedule

INSTANCE_INI_FILENAME = "gcode-index.ini"
ENV_INI_PATH = "GCODE_INDEX_INI"


@dataclass
class InstanceConfig:
    """Flat settings mirror of what the GUI needs to resume indexing."""

    backup: str = ""
    target: str = ""  # database folder (gcode_index.sqlite + sidecar yaml)
    extract: str = ""  # Wydobądź / extract output folder (falls back to target if empty)
    green_roots: list[str] = field(default_factory=list)
    yellow_roots: list[str] = field(default_factory=list)
    language: str = "pl"
    ui_mode: str = "simple"
    schedule: str = SCHEDULE_OFF
    schedule_last_run: str = ""
    incremental: bool = True
    watch_folders: bool = False
    also_excel: bool = False
    newest_only: bool = False
    geometry: str = "1320x820"
    notes: str = ""
    # PBKDF2 hash for Full / Pełny unlock — never store plaintext PIN.
    full_pin_hash: str = ""

    def root_specs(self) -> list[ScanRootSpec]:
        specs: list[ScanRootSpec] = []
        seen: set[str] = set()
        for path in self.green_roots:
            key = path.strip().casefold()
            if not path.strip() or key in seen:
                continue
            seen.add(key)
            specs.append(ScanRootSpec(path=path.strip(), provenance=PROVENANCE_BACKUP))
        for path in self.yellow_roots:
            key = path.strip().casefold()
            if not path.strip() or key in seen:
                continue
            seen.add(key)
            specs.append(ScanRootSpec(path=path.strip(), provenance=PROVENANCE_EXTRA))
        return specs

    def extract_folder(self) -> str:
        """Folder for extracted programs; empty extract falls back to target."""
        return (self.extract or "").strip() or (self.target or "").strip()


def default_instance_ini_path() -> Path:
    """Resolve where this install keeps ``gcode-index.ini``."""
    import os

    env = (os.environ.get(ENV_INI_PATH) or "").strip()
    if env:
        return Path(env).expanduser()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / INSTANCE_INI_FILENAME
    return Path.cwd() / INSTANCE_INI_FILENAME


def _truthy(value: str, default: bool = False) -> bool:
    raw = (value or "").strip().casefold()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "y", "on", "tak"):
        return True
    if raw in ("0", "false", "no", "n", "off", "nie"):
        return False
    return default


def _split_paths(block: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in (block or "").splitlines():
        s = line.strip()
        if not s or s.startswith(";") or s.startswith("#"):
            continue
        # Allow "green:D:\path" / "yellow:D:\path" inside either section
        low = s.casefold()
        if low.startswith("green:"):
            s = s.split(":", 1)[1].strip()
        elif low.startswith("yellow:"):
            s = s.split(":", 1)[1].strip()
        if not s or s.casefold() in seen:
            continue
        seen.add(s.casefold())
        out.append(s)
    return out


def _format_paths(paths: Iterable[str]) -> str:
    items = [p.strip() for p in paths if str(p).strip()]
    if not items:
        return ""
    return "\n" + "\n".join(f"    {p}" for p in items)


def load_instance_ini(path: Path | str | None = None) -> InstanceConfig:
    p = Path(path) if path is not None else default_instance_ini_path()
    cfg = InstanceConfig()
    if not p.is_file():
        return cfg
    parser = ConfigParser(interpolation=None)
    try:
        parser.read(p, encoding="utf-8")
    except OSError:
        return cfg

    if parser.has_section("folders"):
        cfg.backup = parser.get("folders", "backup", fallback="").strip()
        cfg.target = parser.get("folders", "target", fallback="").strip()
        # Prefer explicit extract=; accept legacy extract_folder=
        cfg.extract = parser.get("folders", "extract", fallback="").strip()
        if not cfg.extract:
            cfg.extract = parser.get("folders", "extract_folder", fallback="").strip()

    if parser.has_section("green_roots"):
        cfg.green_roots = _split_paths(parser.get("green_roots", "paths", fallback=""))
    if parser.has_section("yellow_roots"):
        cfg.yellow_roots = _split_paths(parser.get("yellow_roots", "paths", fallback=""))

    # Optional legacy combined section: root1 = green|path
    if parser.has_section("scan_roots"):
        for key, value in parser.items("scan_roots"):
            if key in ("paths", "count") or key.startswith("_"):
                continue
            raw = value.strip()
            if not raw:
                continue
            if "|" in raw:
                flag, path_s = raw.split("|", 1)
                flag_l = flag.strip().casefold()
                path_s = path_s.strip()
            elif raw.casefold().startswith("green:"):
                flag_l, path_s = "green", raw.split(":", 1)[1].strip()
            elif raw.casefold().startswith("yellow:"):
                flag_l, path_s = "yellow", raw.split(":", 1)[1].strip()
            else:
                flag_l, path_s = "yellow", raw
            if not path_s:
                continue
            if flag_l in ("green", "backup", "g"):
                if path_s.casefold() not in {x.casefold() for x in cfg.green_roots}:
                    cfg.green_roots.append(path_s)
            else:
                if path_s.casefold() not in {x.casefold() for x in cfg.yellow_roots}:
                    cfg.yellow_roots.append(path_s)

    if parser.has_section("ui"):
        cfg.language = parser.get("ui", "language", fallback=cfg.language).strip() or "pl"
        cfg.ui_mode = parser.get("ui", "mode", fallback=cfg.ui_mode).strip() or "simple"
        cfg.schedule = normalize_schedule(
            parser.get("ui", "schedule", fallback=cfg.schedule)
        )
        cfg.schedule_last_run = parser.get(
            "ui", "schedule_last_run", fallback=""
        ).strip()

    if parser.has_section("scan"):
        cfg.incremental = _truthy(
            parser.get("scan", "incremental", fallback="yes"), default=True
        )
        cfg.also_excel = _truthy(
            parser.get("scan", "also_excel", fallback="no"), default=False
        )
        cfg.newest_only = _truthy(
            parser.get("scan", "newest_only", fallback="no"), default=False
        )
        cfg.watch_folders = _truthy(
            parser.get("scan", "watch_folders", fallback="no"), default=False
        )

    if parser.has_section("window"):
        geom = parser.get("window", "geometry", fallback=cfg.geometry).strip()
        if geom:
            cfg.geometry = geom

    if parser.has_section("notes"):
        cfg.notes = parser.get("notes", "text", fallback="").strip()

    if parser.has_section("security"):
        cfg.full_pin_hash = parser.get(
            "security", "full_pin_hash", fallback=""
        ).strip()

    return cfg


def save_instance_ini(
    path: Path | str | None = None,
    *,
    config: Optional[InstanceConfig] = None,
    **kwargs,
) -> Path:
    """Write a comment-rich INI. Keyword overrides apply on top of ``config``."""
    p = Path(path) if path is not None else default_instance_ini_path()
    base = config or InstanceConfig()
    data = InstanceConfig(
        backup=str(kwargs.get("backup", base.backup) or ""),
        target=str(kwargs.get("target", base.target) or ""),
        extract=str(kwargs.get("extract", base.extract) or ""),
        green_roots=list(kwargs.get("green_roots", base.green_roots) or []),
        yellow_roots=list(kwargs.get("yellow_roots", base.yellow_roots) or []),
        language=str(kwargs.get("language", base.language) or "pl"),
        ui_mode=str(kwargs.get("ui_mode", base.ui_mode) or "simple"),
        schedule=normalize_schedule(str(kwargs.get("schedule", base.schedule) or SCHEDULE_OFF)),
        schedule_last_run=str(kwargs.get("schedule_last_run", base.schedule_last_run) or ""),
        incremental=bool(kwargs.get("incremental", base.incremental)),
        watch_folders=bool(kwargs.get("watch_folders", base.watch_folders)),
        also_excel=bool(kwargs.get("also_excel", base.also_excel)),
        newest_only=bool(kwargs.get("newest_only", base.newest_only)),
        geometry=str(kwargs.get("geometry", base.geometry) or "1320x820"),
        notes=str(kwargs.get("notes", base.notes) or ""),
        full_pin_hash=str(kwargs.get("full_pin_hash", base.full_pin_hash) or ""),
    )
    p.parent.mkdir(parents=True, exist_ok=True)

    def yn(flag: bool) -> str:
        return "yes" if flag else "no"

    text = f"""\
; ============================================================
; G-code Backup Indexer — settings for THIS installed copy
; File name: {INSTANCE_INI_FILENAME}
; Location: next to gcode-index-gui.exe (or working folder in dev)
; Override path with env var {ENV_INI_PATH}=...
;
; Edit this file in Notepad, or change folders in the GUI —
; the app rewrites this file when you browse / scan / change settings.
; Lines starting with ; are comments.
; ============================================================

[folders]
; Main CNC backup tree (usually DATE\\MACHINE\\... dumps + .nc files)
backup = {data.backup}
; Database folder — gcode_index.sqlite, machine_folders.yaml, aliases.local.yaml
target = {data.target}
; Extract / Wydobądź output folder (leave blank to use the database folder)
extract = {data.extract}

[green_roots]
; ON-MACHINE catch folders (green flag). One full path per indented line.
; Use for loose .nc copies before the control wipes them / backup misses them.
; Subfolders are scanned recursively.
paths ={_format_paths(data.green_roots)}

[yellow_roots]
; EXTRA folders (yellow flag) — not from the machine backup.
; One full path per indented line. Subfolders are scanned recursively.
paths ={_format_paths(data.yellow_roots)}

[ui]
; Language: pl (default) or en
language = {data.language}
; Mode: simple (operators) or full (power users)
mode = {data.ui_mode}
; Auto-index while the GUI stays open: off | hourly | daily | weekly
schedule = {data.schedule}
; Last successful auto/manual index time (UTC ISO). Leave blank to force soon.
schedule_last_run = {data.schedule_last_run}

[scan]
; yes/no — skip unchanged files when re-indexing
incremental = {yn(data.incremental)}
; yes/no — Full mode: watch backup/extra folders and incremental-index on drop
watch_folders = {yn(data.watch_folders)}
; yes/no — also write gcode_index.xlsx after a full-mode scan
also_excel = {yn(data.also_excel)}
; yes/no — default "newest only" filter on startup
newest_only = {yn(data.newest_only)}

[window]
; Width x height in pixels (e.g. 1320x820)
geometry = {data.geometry}

[notes]
; Free-form note for this PC / shop (optional)
text = {data.notes}

[security]
; Hashed PIN for Full / Pełny mode (pbkdf2_sha256$…). Leave blank until set in GUI.
; Never put a plaintext PIN here — the app writes the hash when you create/change it.
full_pin_hash = {data.full_pin_hash}
"""
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def config_from_root_specs(
    specs: Iterable[ScanRootSpec],
    *,
    base: Optional[InstanceConfig] = None,
) -> InstanceConfig:
    """Split typed scan roots into green/yellow lists on a copy of ``base``."""
    cfg = InstanceConfig(**{**base.__dict__}) if base else InstanceConfig()
    greens: list[str] = []
    yellows: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        path = str(spec.path).strip()
        if not path or path.casefold() in seen:
            continue
        seen.add(path.casefold())
        if spec.provenance == PROVENANCE_BACKUP:
            greens.append(path)
        else:
            yellows.append(path)
    cfg.green_roots = greens
    cfg.yellow_roots = yellows
    return cfg
