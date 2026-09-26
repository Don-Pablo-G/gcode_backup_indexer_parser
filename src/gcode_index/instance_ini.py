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
from gcode_index.path_remap import (
    PathRemap,
    format_remap_rules_block,
    normalize_remaps,
    parse_remap_rules_block,
)
from gcode_index.autostart_win import VIA_STARTUP, normalize_autostart_via
from gcode_index.folder_watch import DEFAULT_WATCH_MODE, normalize_watch_mode
from gcode_index.operator_lock import (
    is_settings_locked,
    settings_locked_from_ini_value,
)
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
    ui_mode: str = "simple"  # legacy mirror of can_index (simple|full)
    can_index: bool = False  # primary capability: indexer PC vs floor client
    settings_locked: bool = False  # deploy lock: force retrieve-only / block dangerous flips
    schedule: str = SCHEDULE_OFF
    schedule_last_run: str = ""
    incremental: bool = True
    watch_folders: bool = False
    watch_mode: str = DEFAULT_WATCH_MODE  # hybrid | poll
    also_excel: bool = False
    newest_only: bool = False
    include_unknown: bool = True  # sticky: keep MACHINE UNKNOWN when filtering machines
    search_auto_refresh: bool = False  # re-query when DB mtime changes
    search_auto_refresh_s: int = 20  # poll interval for DB mtime (seconds)
    geometry: str = "1320x820"
    notes: str = ""
    # Client extract remaps: indexer prefix → local prefix (e.g. C:\\Share → Z:\\Share).
    path_remaps: list[PathRemap] = field(default_factory=list)
    autostart: bool = False
    autostart_via: str = VIA_STARTUP
    close_to_tray: bool = True
    minimize_to_tray: bool = True
    # --- [filters] last find-bar state (restored on restart) ---
    filter_text: str = ""
    filter_machines: list[str] = field(default_factory=list)
    filter_date_from: str = ""
    filter_date_to: str = ""
    filter_size_min: str = ""
    filter_size_max: str = ""
    filter_mtime_from: str = ""
    filter_mtime_to: str = ""
    filter_source_type: str = ""  # empty = (all)
    filter_control: str = ""
    filter_status: str = ""  # backup|extra|"" 
    filter_role: str = ""  # role id or ""
    filter_programmer: str = ""
    # --- [session] chrome / layout ---
    sort_col: str = ""
    sort_reverse: bool = False
    more_filters: bool = False
    folders_expanded: Optional[bool] = None  # None = auto heuristic
    pelny_view: str = "praca"  # praca | indeks
    preview_find: str = ""

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


def ui_mode_from_can_index(can_index: bool) -> str:
    return "full" if can_index else "simple"


def can_index_from_ui_mode(mode: str) -> bool:
    raw = (mode or "").strip().casefold()
    return raw in ("full", "advanced", "expert", "pełny", "pelny", "yes", "true", "1")


def normalize_can_index(value: Optional[str | bool], *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    raw = str(value).strip().casefold()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "y", "on", "tak", "full", "index", "indexer"):
        return True
    if raw in ("0", "false", "no", "n", "off", "nie", "simple", "client", "retrieve"):
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

    # Capabilities (primary). Migrate from legacy ui.mode when absent.
    settings_locked_flag = False
    if parser.has_section("capabilities"):
        settings_locked_flag = settings_locked_from_ini_value(
            parser.get("capabilities", "settings_locked", fallback="")
        )
        cfg.settings_locked = settings_locked_flag
        cfg.can_index = normalize_can_index(
            parser.get("capabilities", "can_index", fallback=""),
            default=can_index_from_ui_mode(cfg.ui_mode),
        )
    else:
        cfg.can_index = can_index_from_ui_mode(cfg.ui_mode)

    # Deploy-time lock file / flag forces retrieve-only (floor PCs).
    locked = is_settings_locked(
        ini_path=p, settings_locked_flag=settings_locked_flag
    )
    cfg.settings_locked = locked or cfg.settings_locked
    if locked:
        cfg.can_index = False
    cfg.ui_mode = ui_mode_from_can_index(cfg.can_index)

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
        cfg.include_unknown = _truthy(
            parser.get("scan", "include_unknown", fallback="yes"), default=True
        )
        cfg.watch_folders = _truthy(
            parser.get("scan", "watch_folders", fallback="no"), default=False
        )
        cfg.watch_mode = normalize_watch_mode(
            parser.get("scan", "watch_mode", fallback=DEFAULT_WATCH_MODE)
        )
        cfg.search_auto_refresh = _truthy(
            parser.get("scan", "search_auto_refresh", fallback="no"), default=False
        )
        try:
            cfg.search_auto_refresh_s = max(
                5,
                int(
                    float(
                        parser.get(
                            "scan", "search_auto_refresh_s", fallback="20"
                        ).strip()
                        or "20"
                    )
                ),
            )
        except ValueError:
            cfg.search_auto_refresh_s = 20

    if parser.has_section("window"):
        geom = parser.get("window", "geometry", fallback=cfg.geometry).strip()
        if geom:
            cfg.geometry = geom

    if parser.has_section("notes"):
        cfg.notes = parser.get("notes", "text", fallback="").strip()


    if parser.has_section("path_remap"):
        rules = parse_remap_rules_block(
            parser.get("path_remap", "rules", fallback="")
        )
        # Shorthand single pair (also fills when rules empty)
        fr = parser.get("path_remap", "from_prefix", fallback="").strip()
        to = parser.get("path_remap", "to_prefix", fallback="").strip()
        if fr and to:
            rules = normalize_remaps([PathRemap(fr, to), *rules])
        cfg.path_remaps = rules

    if parser.has_section("desktop"):
        cfg.autostart = _truthy(
            parser.get("desktop", "autostart", fallback="no"), default=False
        )
        cfg.autostart_via = normalize_autostart_via(
            parser.get("desktop", "autostart_via", fallback=VIA_STARTUP)
        )
        cfg.close_to_tray = _truthy(
            parser.get("desktop", "close_to_tray", fallback="yes"), default=True
        )
        cfg.minimize_to_tray = _truthy(
            parser.get("desktop", "minimize_to_tray", fallback="yes"), default=True
        )

    if parser.has_section("filters"):
        cfg.filter_text = parser.get("filters", "text", fallback="").strip()
        cfg.filter_machines = _split_paths(
            parser.get("filters", "machines", fallback="")
        )
        # Also accept comma-separated machines=
        machines_raw = parser.get("filters", "machines", fallback="").strip()
        if machines_raw and not cfg.filter_machines and "\n" not in machines_raw:
            cfg.filter_machines = [
                p.strip() for p in machines_raw.split(",") if p.strip()
            ]
        cfg.filter_date_from = parser.get("filters", "date_from", fallback="").strip()
        cfg.filter_date_to = parser.get("filters", "date_to", fallback="").strip()
        cfg.filter_size_min = parser.get("filters", "size_min", fallback="").strip()
        cfg.filter_size_max = parser.get("filters", "size_max", fallback="").strip()
        cfg.filter_mtime_from = parser.get("filters", "mtime_from", fallback="").strip()
        cfg.filter_mtime_to = parser.get("filters", "mtime_to", fallback="").strip()
        cfg.filter_source_type = _filter_all_to_empty(
            parser.get("filters", "source_type", fallback="")
        )
        cfg.filter_control = _filter_all_to_empty(
            parser.get("filters", "control", fallback="")
        )
        cfg.filter_status = _filter_all_to_empty(
            parser.get("filters", "status", fallback="")
            or parser.get("filters", "provenance", fallback="")
        )
        cfg.filter_role = _filter_all_to_empty(
            parser.get("filters", "role", fallback="")
        )
        cfg.filter_programmer = _filter_all_to_empty(
            parser.get("filters", "programmer", fallback="")
        )

    if parser.has_section("session"):
        cfg.sort_col = parser.get("session", "sort_col", fallback="").strip()
        cfg.sort_reverse = _truthy(
            parser.get("session", "sort_reverse", fallback="no"), default=False
        )
        cfg.more_filters = _truthy(
            parser.get("session", "more_filters", fallback="no"), default=False
        )
        fe_raw = parser.get("session", "folders_expanded", fallback="").strip()
        if fe_raw == "":
            cfg.folders_expanded = None
        else:
            cfg.folders_expanded = _truthy(fe_raw, default=True)
        view = parser.get("session", "pelny_view", fallback="praca").strip().casefold()
        cfg.pelny_view = view if view in ("praca", "indeks", "index") else "praca"
        if cfg.pelny_view == "index":
            cfg.pelny_view = "indeks"
        cfg.preview_find = parser.get("session", "preview_find", fallback="").strip()

    return cfg


def _filter_all_to_empty(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    low = raw.casefold()
    if low in ("(all)", "(wszystkie)", "all", "wszystkie", "*"):
        return ""
    return raw


def save_instance_ini(
    path: Path | str | None = None,
    *,
    config: Optional[InstanceConfig] = None,
    **kwargs,
) -> Path:
    """Write a comment-rich INI. Keyword overrides apply on top of ``config``."""
    p = Path(path) if path is not None else default_instance_ini_path()
    base = config or InstanceConfig()

    if "can_index" in kwargs:
        can_index = normalize_can_index(
            kwargs["can_index"], default=bool(base.can_index)
        )
    elif "ui_mode" in kwargs:
        can_index = can_index_from_ui_mode(str(kwargs.get("ui_mode", base.ui_mode)))
    else:
        can_index = bool(base.can_index)

    settings_locked_flag = bool(
        kwargs.get("settings_locked", base.settings_locked)
    )
    # Lock file beside the ini always wins (deploy-time floor protection).
    if is_settings_locked(ini_path=p, settings_locked_flag=settings_locked_flag):
        settings_locked_flag = True
        can_index = False
    ui_mode = ui_mode_from_can_index(can_index)

    try:
        refresh_s = int(
            kwargs.get("search_auto_refresh_s", base.search_auto_refresh_s) or 20
        )
    except (TypeError, ValueError):
        refresh_s = 20
    refresh_s = max(5, refresh_s)

    data = InstanceConfig(
        backup=str(kwargs.get("backup", base.backup) or ""),
        target=str(kwargs.get("target", base.target) or ""),
        extract=str(kwargs.get("extract", base.extract) or ""),
        green_roots=list(kwargs.get("green_roots", base.green_roots) or []),
        yellow_roots=list(kwargs.get("yellow_roots", base.yellow_roots) or []),
        language=str(kwargs.get("language", base.language) or "pl"),
        can_index=can_index,
        settings_locked=settings_locked_flag,
        ui_mode=ui_mode,
        schedule=normalize_schedule(
            str(kwargs.get("schedule", base.schedule) or SCHEDULE_OFF)
        ),
        schedule_last_run=str(
            kwargs.get("schedule_last_run", base.schedule_last_run) or ""
        ),
        incremental=bool(kwargs.get("incremental", base.incremental)),
        watch_folders=bool(kwargs.get("watch_folders", base.watch_folders)),
        watch_mode=normalize_watch_mode(
            str(kwargs.get("watch_mode", base.watch_mode) or DEFAULT_WATCH_MODE)
        ),
        also_excel=bool(kwargs.get("also_excel", base.also_excel)),
        newest_only=bool(kwargs.get("newest_only", base.newest_only)),
        include_unknown=bool(kwargs.get("include_unknown", base.include_unknown)),
        search_auto_refresh=bool(
            kwargs.get("search_auto_refresh", base.search_auto_refresh)
        ),
        search_auto_refresh_s=refresh_s,
        geometry=str(kwargs.get("geometry", base.geometry) or "1320x820"),
        notes=str(kwargs.get("notes", base.notes) or ""),
        path_remaps=normalize_remaps(
            kwargs.get("path_remaps", base.path_remaps) or []
        ),
        autostart=bool(kwargs.get("autostart", base.autostart)),
        autostart_via=normalize_autostart_via(
            str(kwargs.get("autostart_via", base.autostart_via) or VIA_STARTUP)
        ),
        close_to_tray=bool(kwargs.get("close_to_tray", base.close_to_tray)),
        minimize_to_tray=bool(
            kwargs.get("minimize_to_tray", base.minimize_to_tray)
        ),
        filter_text=str(kwargs.get("filter_text", base.filter_text) or ""),
        filter_machines=list(
            kwargs.get("filter_machines", base.filter_machines) or []
        ),
        filter_date_from=str(
            kwargs.get("filter_date_from", base.filter_date_from) or ""
        ),
        filter_date_to=str(kwargs.get("filter_date_to", base.filter_date_to) or ""),
        filter_size_min=str(kwargs.get("filter_size_min", base.filter_size_min) or ""),
        filter_size_max=str(kwargs.get("filter_size_max", base.filter_size_max) or ""),
        filter_mtime_from=str(
            kwargs.get("filter_mtime_from", base.filter_mtime_from) or ""
        ),
        filter_mtime_to=str(kwargs.get("filter_mtime_to", base.filter_mtime_to) or ""),
        filter_source_type=_filter_all_to_empty(
            str(kwargs.get("filter_source_type", base.filter_source_type) or "")
        ),
        filter_control=_filter_all_to_empty(
            str(kwargs.get("filter_control", base.filter_control) or "")
        ),
        filter_status=_filter_all_to_empty(
            str(kwargs.get("filter_status", base.filter_status) or "")
        ),
        filter_role=_filter_all_to_empty(
            str(kwargs.get("filter_role", base.filter_role) or "")
        ),
        filter_programmer=_filter_all_to_empty(
            str(kwargs.get("filter_programmer", base.filter_programmer) or "")
        ),
        sort_col=str(kwargs.get("sort_col", base.sort_col) or ""),
        sort_reverse=bool(kwargs.get("sort_reverse", base.sort_reverse)),
        more_filters=bool(kwargs.get("more_filters", base.more_filters)),
        folders_expanded=kwargs.get("folders_expanded", base.folders_expanded),
        pelny_view=str(kwargs.get("pelny_view", base.pelny_view) or "praca"),
        preview_find=str(kwargs.get("preview_find", base.preview_find) or ""),
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
; Deploy tip:
;   Shop / floor PCs  →  can_index = no  (+ optional operator.lock)
;   Indexer PC        →  can_index = yes (no lock file)
;
; Edit this file in Notepad, or change folders in the GUI —
; the app rewrites this file when you browse / scan / change settings.
; Lines starting with ; are comments.
; ============================================================

[capabilities]
; Primary capability flag for this PC (not a runtime UI toggle).
; yes = indexer: scan / map / watch / schedule / folder setup available
; no  = floor client: search + preview + extract only (open DB / remap / extract folder)
; Legacy [ui] mode=simple|full still loads when this key is absent (simple→no, full→yes).
can_index = {yn(data.can_index)}
; Deploy-time lock: yes = force retrieve-only (can_index ignored / forced no).
; Same effect as placing an empty operator.lock (or can_index.lock) next to this ini.
; Floor PCs: set yes OR drop operator.lock so nobody can elevate to indexer by editing can_index.
settings_locked = {yn(data.settings_locked)}

[folders]
; Main CNC backup tree (usually DATE\\MACHINE\\... dumps + .nc files)
; Used by the indexer; optional on floor clients that only open a shared DB.
backup = {data.backup}
; Database folder — gcode_index.sqlite, machine_folders.yaml, aliases.local.yaml
target = {data.target}
; Extract / Wydobądź output folder (leave blank to use the database folder)
extract = {data.extract}

[green_roots]
; ON-MACHINE catch folders (green flag). One full path per indented line.
; Use for loose .nc copies before the control wipes them / backup misses them.
; Subfolders are scanned recursively. Indexer (can_index=yes) only.
paths ={_format_paths(data.green_roots)}

[yellow_roots]
; EXTRA folders (yellow flag) — not from the machine backup.
; One full path per indented line. Subfolders are scanned recursively.
; Indexer (can_index=yes) only.
paths ={_format_paths(data.yellow_roots)}

[ui]
; Language: pl (default) or en
language = {data.language}
; Legacy mirror of [capabilities] can_index (simple = no, full = yes).
; Prefer can_index above; this is kept so older tools still read the file.
mode = {data.ui_mode}
; Auto-index while the GUI stays open (indexer only): off | 30s | 15m | 2h | 1d
; Legacy hourly/daily/weekly still load as 1h / 1d / 7d
schedule = {data.schedule}
; Last successful auto/manual index time (UTC ISO). Leave blank to force soon.
schedule_last_run = {data.schedule_last_run}

[scan]
; yes/no — skip unchanged files when re-indexing (indexer)
incremental = {yn(data.incremental)}
; yes/no — watch backup/extra folders and incremental-index on drop (indexer)
watch_folders = {yn(data.watch_folders)}
; Watch method when watch_folders=yes (indexer):
;   hybrid = Auto — OS events on local disks, stamp-poll on network/UNC shares
;   poll   = stamp-poll everywhere (safe fallback)
; Accepted aliases: auto/hybryda → hybrid; safe/stamp → poll
watch_mode = {data.watch_mode}
; yes/no — also write gcode_index.xlsx after a scan (indexer)
also_excel = {yn(data.also_excel)}
; yes/no — default "newest only" filter on startup
newest_only = {yn(data.newest_only)}
; yes/no — when filtering by machines, still show MACHINE UNKNOWN / unassigned
; Default yes. Floor clients (can_index=no / operator.lock) keep this on.
include_unknown = {yn(data.include_unknown)}
; yes/no — auto-refresh search results when the DB file changes (mtime)
; Useful on floor clients sharing a network DB — no need to retype search.
search_auto_refresh = {yn(data.search_auto_refresh)}
; How often to check DB mtime while auto-refresh is on (seconds, min 5)
search_auto_refresh_s = {data.search_auto_refresh_s}

[window]
; Width x height in pixels (e.g. 1320x820)
geometry = {data.geometry}

[notes]
; Free-form note for this PC / shop (optional)
text = {data.notes}

[path_remap]
; Client extract remaps when the indexer and this PC use different drive letters
; for the same share (e.g. indexer C:\\CNC\\Share → client Z:\\CNC\\Share).
; Applies to scan_root for main backup AND green/yellow roots on that prefix.
; One rule per indented line: FROM => TO   (also accepted: from_prefix / to_prefix)
from_prefix = {(data.path_remaps[0].from_prefix if data.path_remaps else "")}
to_prefix = {(data.path_remaps[0].to_prefix if data.path_remaps else "")}
rules ={format_remap_rules_block(data.path_remaps[1:] if len(data.path_remaps) > 1 else [])}

[desktop]
; Windows logon autostart (indexer helper). yes/no
autostart = {yn(data.autostart)}
; startup = Startup folder shortcut | task = Task Scheduler ONLOGON
autostart_via = {data.autostart_via}
; Window X closes to tray (yes) or quits (no) — indexer / tray builds
close_to_tray = {yn(data.close_to_tray)}
; Minimize / iconify also hides to tray
minimize_to_tray = {yn(data.minimize_to_tray)}

[filters]
; Last find-bar / search filters — restored on restart (no re-setup).
; Empty / blank = no filter (same as UI “(all)”).
; machines = one display name per indented line (or comma-separated).
text = {data.filter_text}
machines ={_format_paths(data.filter_machines)}
date_from = {data.filter_date_from}
date_to = {data.filter_date_to}
size_min = {data.filter_size_min}
size_max = {data.filter_size_max}
mtime_from = {data.filter_mtime_from}
mtime_to = {data.filter_mtime_to}
; Source type code (loose_nc, haas_pgm_glued, …) or blank = all
source_type = {data.filter_source_type}
; Control family (haas / fanuc / sinumerik) or blank = all
control = {data.filter_control}
; Status: blank = all | backup = on-machine 🟢 | extra = not-run 🟡
status = {data.filter_status}
; Role catalogue id (production / wip / fixture / …) or blank = all
role = {data.filter_role}
; Programmer flag (LP1 / MS1) or blank = all
programmer = {data.filter_programmer}

[session]
; Results sort column id (flag/program/part/machine/date/size/…) or blank
sort_col = {data.sort_col}
sort_reverse = {yn(data.sort_reverse)}
; yes = “More filters” panel open
more_filters = {yn(data.more_filters)}
; Folders panel: yes = expanded path editors | no = collapsed summary | blank = auto
folders_expanded = {("" if data.folders_expanded is None else yn(bool(data.folders_expanded)))}
; Indexer primary nav: praca | indeks
pelny_view = {data.pelny_view}
; Preview “find in program” last string (optional)
preview_find = {data.preview_find}

; ------------------------------------------------------------
; Sidecars next to the database folder (auto-loaded; do not delete):
;   machine_folders.yaml       — Map folders… assignments
;   aliases.local.yaml         — Machines & aliases…
;   folder_colour_aliases.yaml — Folder roles… (catalogue + name aliases)
;   folder_tree_map.yaml       — Map tree… (path machine/tags/exclude)
;   extra_scan_roots.yaml      — mirror of green/yellow roots (INI is primary)
;   filter_presets.yaml        — named filter presets (Save preset…)
;   ui_settings.yaml           — schedule_last_run mirror (optional)
;   scan_history.json          — scan run history
; Ustawienia wracają po restarcie — everything above + this ini is reloaded on start.
; ------------------------------------------------------------
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
