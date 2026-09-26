"""Windows-friendly tkinter GUI for scan / live search / extract.

Stdlib only (no MSVC / extra GUI wheels). Launch::

    gcode-index-gui
    python -m gcode_index.gui
"""

from __future__ import annotations

import logging
import sys
import threading
import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from typing import Any, Optional

from gcode_index.aliases import (
    AliasMap,
    LOCAL_ALIASES_FILENAME,
    default_aliases_path,
    local_aliases_path_for_target,
    normalize_folder_name,
)
from gcode_index.compare import (
    instance_label,
    preview_text,
    unified_diff_programs,
)
from gcode_index.db import (
    format_display_date,
    format_display_size,
    format_location,
    list_filter_values,
    open_db,
    query_instances,
    sort_instances,
    write_scan_result,
)
from gcode_index.excel_export import export_excel
from gcode_index.extract import (
    ExtractError,
    batch_extract_filename,
    default_extract_filename,
    extract_to_path,
)
from gcode_index.extra_roots import (
    ScanRootSpec,
    extra_roots_path_for_target,
    format_root_label,
    load_scan_roots,
    normalize_scan_roots,
    parse_root_label,
    save_scan_roots,
)
from gcode_index.folder_map import (
    UNKNOWN_ID,
    UNKNOWN_LABEL,
    FolderMachineMap,
    FolderPartition,
    discover_machine_folders,
    display_for_machine,
    map_path_for_target,
    parse_machine_display,
    partition_folders,
    suggest_assignments,
)
from gcode_index.folder_tree_map import (
    TREE_MAP_FILENAME,
    FolderTreeMap,
    collect_tree_map_roots,
    list_child_dirs,
    load_folder_tree_map,
    roles_from_db,
    save_folder_tree_map,
    tree_map_path_for_target,
)
from gcode_index.badge_style import (
    DOT,
    STATUS_SWATCH,
    flag_tag,
    flag_text,
    make_swatch,
    pack_status_legend,
    role_dot,
    status_dot,
    status_swatch,
)
from gcode_index.models import (
    COLOUR_EXCLUDE,
    PROVENANCE_BACKUP,
    PROVENANCE_EXTRA,
    ROLE_FIXTURE,
    ROLE_PERSONAL,
    ROLE_WIP,
)
from gcode_index.folder_colour_aliases import (
    FOLDER_COLOUR_ALIASES_FILENAME,
    COLOUR_PRESET_SWATCHES,
    ColourCatalog,
    ColourDef,
    FolderColourAliasMap,
    FolderColourRule,
    count_same_name_dirs,
    default_colours,
    folder_colour_aliases_path_for_target,
    is_risky_alias_name,
    is_status_colour_id,
    load_colour_catalog,
    normalize_colour_id,
    normalize_hex_colour,
    save_colour_catalog,
)
from gcode_index.path_util import (
    format_eta,
    open_path_in_file_manager,
    resolve_source_abspath,
    source_exists_on_disk,
)
from gcode_index.path_remap import PathRemap, normalize_remaps
from gcode_index.instance_ini import (
    InstanceConfig,
    default_instance_ini_path,
    load_instance_ini,
    save_instance_ini,
    ui_mode_from_can_index,
)
from gcode_index.i18n import (
    DEFAULT_LANG,
    load_ui_settings,
    normalize_lang,
    save_ui_settings,
    t,
    ui_settings_path_for_target,
)
from gcode_index.presets import (
    PRESETS_FILENAME,
    FilterPreset,
    delete_preset,
    get_preset,
    load_presets,
    presets_path_for_target,
    upsert_preset,
)
from gcode_index.schedule import (
    SCHEDULE_OFF,
    UNIT_DAYS,
    UNIT_HOURS,
    UNIT_MINUTES,
    UNIT_SECONDS,
    format_countdown,
    format_iso_datetime,
    format_schedule,
    is_schedule_due,
    normalize_schedule,
    parse_iso_datetime,
    parse_schedule,
    schedule_poll_ms,
    seconds_until_next,
)
from gcode_index.scan_cache import load_scan_cache
from gcode_index.scan_report import (
    DuplicateGroup,
    ScanReport,
    find_duplicate_groups,
    format_scan_report,
    load_scan_report,
    scan_report_from_result,
)
from gcode_index.scanner import scan_backup_tree, scan_with_extra_roots, roots_nest
from gcode_index.folder_watch import (
    DEFAULT_WATCH_MODE,
    METHOD_EVENTS,
    WATCH_MODE_HYBRID,
    WATCH_MODE_POLL,
    FolderWatcher,
    normalize_watch_mode,
)
from gcode_index.scan_history import (
    DEFAULT_HISTORY_LIMIT,
    append_scan_history,
    build_history_entry,
    history_path_for_target,
    load_scan_history,
    prior_paths_from_cache,
)
from gcode_index.operator_lock import is_settings_locked
from gcode_index.autostart_win import (
    VIA_STARTUP,
    VIA_TASK,
    is_windows as autostart_is_windows,
    normalize_autostart_via,
    sync_autostart,
)
from gcode_index.tray_ui import TrayController, tray_available
from gcode_index.indexer_lock import (
    read_lock,
    release_lock,
    try_acquire_lock,
    we_hold_lock,
)
from gcode_index.help_docs import docs_roots, read_manual, resolve_manual
from gcode_index.app_meta import format_version_build, window_title
from gcode_index.ui_theme import (
    UI_ACCENT,
    UI_ACCENT_HOVER,
    UI_ACCENT_TEXT,
    UI_KEY_FG,
    UI_MUTED_FG,
    UI_NAV_BORDER,
    UI_NAV_IDLE_BG,
    UI_NAV_IDLE_FG,
    UI_NAV_IDLE_HOVER,
)

log = logging.getLogger(__name__)

SEARCH_DEBOUNCE_MS = 250
DEFAULT_DB_NAME = "gcode_index.sqlite"
BROWSE_LIMIT = 500
ALL = "(all)"
ALL_TOKENS = frozenset({"(all)", "(wszystkie)"})
UNKNOWN_MACHINE_DISPLAY = "MACHINE UNKNOWN (unknown)"

# Re-export theme colors for callers / tests that import from gui
__all__ = [
    "IndexerApp",
    "main",
    "SEARCH_DEBOUNCE_MS",
    "format_eta",
    "open_path_in_file_manager",
    "resolve_source_abspath",
    "UI_ACCENT",
    "UI_KEY_FG",
]



def _tr(master, key: str, **kwargs) -> str:
    """Translate via IndexerApp._ when available, else default language."""
    fn = getattr(master, "_", None)
    if callable(fn):
        try:
            return fn(key, **kwargs)
        except Exception:  # noqa: BLE001
            pass
    from gcode_index.i18n import DEFAULT_LANG, t

    return t(DEFAULT_LANG, key, **kwargs)


class IndexerApp(tk.Tk):
    """Main window: backup + database + extract folders, scan, live search, extract."""

    def __init__(self) -> None:
        super().__init__()
        self.title(window_title("G-code Backup Indexer"))
        self.minsize(1040, 700)
        self.geometry("1320x820")

        self.backup_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.extract_var = tk.StringVar()
        self.remap_from_var = tk.StringVar()
        self.remap_to_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.date_from_var = tk.StringVar()
        self.date_to_var = tk.StringVar()
        self.size_min_var = tk.StringVar()
        self.size_max_var = tk.StringVar()
        self.mtime_from_var = tk.StringVar()
        self.mtime_to_var = tk.StringVar()
        self.source_type_var = tk.StringVar(value=ALL)
        self.control_var = tk.StringVar(value=ALL)
        self.provenance_var = tk.StringVar(value=ALL)
        self.role_var = tk.StringVar(value=ALL)
        self.programmer_var = tk.StringVar(value=ALL)
        self.newest_only_var = tk.BooleanVar(value=False)
        self.include_unknown_var = tk.BooleanVar(value=True)
        self.incremental_var = tk.BooleanVar(value=True)
        self.watch_var = tk.BooleanVar(value=False)
        self.watch_mode_var = tk.StringVar(value="")
        self.search_auto_refresh_var = tk.BooleanVar(value=False)
        self.excel_var = tk.BooleanVar(value=True)
        self.lang_var = tk.StringVar(value=DEFAULT_LANG)
        self._colour_catalog = ColourCatalog()
        self.schedule_var = tk.StringVar(value=SCHEDULE_OFF)
        self.schedule_amount_var = tk.StringVar(value="1")
        self.schedule_unit_var = tk.StringVar(value="")
        self.schedule_status_var = tk.StringVar(value="")
        self.watch_status_var = tk.StringVar(value="")
        self.watch_strip_var = tk.StringVar(value="")
        self.autostart_var = tk.BooleanVar(value=False)
        self.autostart_via_var = tk.StringVar(value="")
        self.close_to_tray_var = tk.BooleanVar(value=True)
        self.minimize_to_tray_var = tk.BooleanVar(value=True)
        self.preset_var = tk.StringVar(value="")
        self.preview_header_var = tk.StringVar(value="")
        self.preview_find_var = tk.StringVar(value="")
        self.preview_find_status_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_label_var = tk.StringVar(value="")

        self._preview_find_matches: list[str] = []
        self._preview_find_index: int = -1
        self._pelny_view = "praca"
        self._search_after_id: Optional[str] = None
        self._schedule_after_id: Optional[str] = None
        self._schedule_amount_debounce_id: Optional[str] = None
        self._result_rows: list = []
        self._missing_source_count: int = 0
        self._sort_col: Optional[str] = None
        self._sort_reverse: bool = False
        self._heading_labels: dict[str, str] = {}
        self._scan_busy = False
        self._watch_rescan_pending = False
        self._folder_watcher: Optional[FolderWatcher] = None
        self._watch_enabled = False
        self._watch_mode = DEFAULT_WATCH_MODE
        self._tray: Optional[TrayController] = None
        self._tray_hidden = False
        self._iconify_guard = False
        self._last_watch_scan_at = None
        self._filter_trace_lock = False
        self._machine_names: list[str] = []
        self._last_scan_report: Optional[ScanReport] = None
        self._root_frame: Optional[ttk.Frame] = None
        self._lang = DEFAULT_LANG
        self._can_index = False  # from [capabilities] can_index in gcode-index.ini
        self._settings_locked = False
        self._search_auto_refresh_s = 20
        self._auto_refresh_after_id: Optional[str] = None
        self._db_mtime_seen: Optional[float] = None
        self._hidden_root_specs: list[ScanRootSpec] = []
        self._schedule = SCHEDULE_OFF
        self._schedule_last_run: Optional[str] = None
        self._machine_sel: set[str] = set()
        self._folders_expanded = True
        self._more_filters_open = False
        self._folders_summary_var = tk.StringVar(value="")
        self._machines_btn_var = tk.StringVar(value="")
        self._instance_ini_path = default_instance_ini_path()
        self._ini_notes = ""
        self._path_remaps: list[PathRemap] = []

        self._apply_instance_ini(load_instance_ini(self._instance_ini_path))
        self._configure_styles()
        self._build()
        # Seed machine list from aliases before any scan
        self._refresh_filter_choices()
        self._load_colour_catalog()
        self._apply_session_from_ini()
        # Only auto-collapse when session did not pin folders_expanded
        if getattr(self, "_session_pinned_folders", False) is not True:
            self._maybe_auto_collapse_folders()
        self._arm_schedule_timer()
        self._sync_folder_watch(initial=True)
        self._arm_search_auto_refresh()
        if self._folders_ready():
            self.status_var.set(
                self._(
                    "status_loaded_ini",
                    filename=self._instance_ini_path.name,
                )
            )
        if self._settings_locked:
            self.status_var.set(
                (self.status_var.get() + " — " if self.status_var.get() else "")
                + self._("settings_locked_status")
            )
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Unmap>", self._on_minimize_event)
        self.search_var.trace_add("write", self._on_filter_changed)
        for var in (
            self.date_from_var,
            self.date_to_var,
            self.size_min_var,
            self.size_max_var,
            self.mtime_from_var,
            self.mtime_to_var,
            self.source_type_var,
            self.control_var,
            self.provenance_var,
            self.role_var,
            self.programmer_var,
            self.newest_only_var,
        ):
            var.trace_add("write", self._on_filter_changed)
        # Persist scan/option toggles immediately (also covered by quit save)
        for var in (
            self.excel_var,
            self.incremental_var,
            self.newest_only_var,
        ):
            var.trace_add("write", self._on_scan_option_changed)
        # Persist folder edits typed by hand (debounced)
        self.backup_var.trace_add("write", self._on_folder_path_changed)
        self.target_var.trace_add("write", self._on_folder_path_changed)
        self.extract_var.trace_add("write", self._on_folder_path_changed)
        self.remap_from_var.trace_add("write", self._on_remap_changed)
        self.remap_to_var.trace_add("write", self._on_remap_changed)
        self._folder_save_after_id: Optional[str] = None
        self._filter_save_after_id: Optional[str] = None
        self._geometry_save_after_id: Optional[str] = None
        self.bind("<Configure>", self._on_window_configure)

    def _(self, key: str, **kwargs) -> str:
        return t(self._lang, key, **kwargs)

    def _apply_instance_ini(self, cfg: InstanceConfig) -> None:
        """Load last session paths/settings before the first widget build."""
        self._lang = normalize_lang(cfg.language)
        self._settings_locked = bool(cfg.settings_locked) or is_settings_locked(
            ini_path=self._instance_ini_path,
            settings_locked_flag=bool(cfg.settings_locked),
        )
        self._can_index = bool(cfg.can_index) and not self._settings_locked
        self.lang_var.set(self._lang)
        self._schedule = normalize_schedule(cfg.schedule)
        self._schedule_last_run = cfg.schedule_last_run or None
        self._sync_schedule_widgets()
        self.backup_var.set(cfg.backup or "")
        self.target_var.set(cfg.target or "")
        self.extract_var.set(cfg.extract or "")
        self.incremental_var.set(bool(cfg.incremental))
        self.watch_var.set(bool(cfg.watch_folders))
        self._watch_mode = normalize_watch_mode(cfg.watch_mode)
        self.watch_mode_var.set(self._watch_mode_label(self._watch_mode))
        self.search_auto_refresh_var.set(bool(cfg.search_auto_refresh))
        self._search_auto_refresh_s = max(5, int(cfg.search_auto_refresh_s or 20))
        self.autostart_var.set(bool(cfg.autostart))
        self.autostart_via_var.set(
            self._autostart_via_label(normalize_autostart_via(cfg.autostart_via))
        )
        self.close_to_tray_var.set(bool(cfg.close_to_tray))
        self.minimize_to_tray_var.set(bool(cfg.minimize_to_tray))
        self.excel_var.set(bool(cfg.also_excel))
        self.newest_only_var.set(bool(cfg.newest_only))
        # Floor lock forces include-UNKNOWN on; indexer may load saved preference.
        if self._is_simple() or self._settings_locked:
            self.include_unknown_var.set(True)
        else:
            self.include_unknown_var.set(bool(cfg.include_unknown))
        self._watch_enabled = bool(cfg.watch_folders) and not self._is_simple()
        self._hidden_root_specs = list(cfg.root_specs())
        self._ini_notes = cfg.notes or ""
        self._path_remaps = normalize_remaps(cfg.path_remaps)
        self._sync_remap_vars_from_list()
        if cfg.geometry:
            try:
                self.geometry(cfg.geometry)
            except tk.TclError:
                pass
        # Target-side YAML is a backup copy; INI wins when it already lists roots.
        target = (cfg.target or "").strip()
        if target and not self._hidden_root_specs:
            roots_path = extra_roots_path_for_target(target)
            if roots_path.is_file():
                disk_roots = list(load_scan_roots(roots_path))
                if disk_roots:
                    self._hidden_root_specs = disk_roots
        # Keep schedule_last_run from target ui_settings only when INI left it blank
        if target:
            settings = load_ui_settings(ui_settings_path_for_target(target))
            if not self._schedule_last_run and settings.get("schedule_last_run"):
                self._schedule_last_run = settings["schedule_last_run"]
        # Stash session/filters for apply after widgets exist
        self._pending_session_cfg = cfg

    def _apply_session_from_ini(self) -> None:
        """Restore find-bar filters + session chrome after widgets are built."""
        cfg = getattr(self, "_pending_session_cfg", None)
        if cfg is None:
            return
        self._pending_session_cfg = None
        self._filter_trace_lock = True
        try:
            self.search_var.set(cfg.filter_text or "")
            self.date_from_var.set(cfg.filter_date_from or "")
            self.date_to_var.set(cfg.filter_date_to or "")
            self.size_min_var.set(cfg.filter_size_min or "")
            self.size_max_var.set(cfg.filter_size_max or "")
            self.mtime_from_var.set(cfg.filter_mtime_from or "")
            self.mtime_to_var.set(cfg.filter_mtime_to or "")
            self.source_type_var.set(
                cfg.filter_source_type or self._all_token()
            )
            self.control_var.set(cfg.filter_control or self._all_token())
            # Status
            st = (cfg.filter_status or "").strip().casefold()
            if st in ("backup", "green", "on_machine"):
                self.provenance_var.set(self._("status_on_machine"))
            elif st in (
                "extra",
                "yellow",
                "not_run",
                "unknown",
                "status_unknown",
                "status nieznany",
                "nie uruchomiony",
                "not run",
            ):
                self.provenance_var.set(self._("status_unknown"))
            else:
                self.provenance_var.set(self._all_token())
            # Role — prefer catalogue label for current language
            role_id = (cfg.filter_role or "").strip()
            if role_id:
                catalog = getattr(self, "_colour_catalog", ColourCatalog())
                c = catalog.get(role_id)
                self.role_var.set(c.label(self._lang) if c else role_id)
            else:
                self.role_var.set(self._all_token())
            self.programmer_var.set(
                cfg.filter_programmer or self._all_token()
            )
            wanted = {
                m.strip() for m in (cfg.filter_machines or []) if str(m).strip()
            }
            if wanted and getattr(self, "_machine_names", None):
                self._machine_sel = {
                    n for n in self._machine_names if n in wanted
                }
            elif wanted:
                self._machine_sel = set(wanted)
            else:
                self._machine_sel = set()
            if hasattr(self, "_update_machines_button"):
                self._update_machines_button()
            self._sort_col = (cfg.sort_col or "").strip() or None
            self._sort_reverse = bool(cfg.sort_reverse)
            if hasattr(self, "_refresh_heading_labels"):
                self._refresh_heading_labels()
            self._more_filters_open = bool(cfg.more_filters)
            if hasattr(self, "_apply_more_filters_visibility"):
                self._apply_more_filters_visibility()
            if cfg.folders_expanded is not None and hasattr(
                self, "_set_folders_expanded"
            ):
                self._session_pinned_folders = True
                self._set_folders_expanded(
                    bool(cfg.folders_expanded), persist=False
                )
            else:
                self._session_pinned_folders = False
            view = (cfg.pelny_view or "praca").strip().casefold()
            if view in ("indeks", "index") and not self._is_simple():
                self._pelny_view = "indeks"
                if hasattr(self, "_show_pelny_view"):
                    try:
                        self._show_pelny_view("indeks")
                    except Exception:  # noqa: BLE001
                        pass
            else:
                self._pelny_view = "praca"
            if cfg.preview_find and hasattr(self, "preview_find_var"):
                self.preview_find_var.set(cfg.preview_find)
        finally:
            self._filter_trace_lock = False
        # Kick a query so restored filters show results
        try:
            self.after(50, lambda: self._run_query_now(status_prefix=""))
        except tk.TclError:
            pass
    def _collect_instance_config(self) -> InstanceConfig:
        specs = self._scan_root_specs()
        greens = [s.path for s in specs if s.provenance == PROVENANCE_BACKUP]
        yellows = [s.path for s in specs if s.provenance == PROVENANCE_EXTRA]
        try:
            geom = self.geometry()
        except tk.TclError:
            geom = "1320x820"
        return InstanceConfig(
            backup=self.backup_var.get().strip(),
            target=self.target_var.get().strip(),
            extract=self.extract_var.get().strip(),
            green_roots=greens,
            yellow_roots=yellows,
            language=self._lang,
            can_index=False if self._settings_locked else self._can_index,
            settings_locked=self._settings_locked,
            ui_mode=ui_mode_from_can_index(
                False if self._settings_locked else self._can_index
            ),
            schedule=self._schedule,
            schedule_last_run=self._schedule_last_run or "",
            incremental=bool(self.incremental_var.get()),
            watch_folders=bool(self.watch_var.get()),
            watch_mode=self._watch_mode,
            also_excel=bool(self.excel_var.get()),
            autostart=bool(self.autostart_var.get()),
            autostart_via=self._autostart_via_code(),
            close_to_tray=bool(self.close_to_tray_var.get()),
            minimize_to_tray=bool(self.minimize_to_tray_var.get()),
            newest_only=bool(self.newest_only_var.get()),
            include_unknown=self._effective_include_unknown(),
            search_auto_refresh=bool(self.search_auto_refresh_var.get()),
            search_auto_refresh_s=self._search_auto_refresh_s,
            geometry=geom,
            notes=self._ini_notes,
            path_remaps=self._collect_path_remaps(),
            filter_text=self.search_var.get().strip(),
            filter_machines=self._selected_machines(),
            filter_date_from=self.date_from_var.get().strip(),
            filter_date_to=self.date_to_var.get().strip(),
            filter_size_min=self.size_min_var.get().strip(),
            filter_size_max=self.size_max_var.get().strip(),
            filter_mtime_from=self.mtime_from_var.get().strip(),
            filter_mtime_to=self.mtime_to_var.get().strip(),
            filter_source_type=self._combo_filter_for_ini(self.source_type_var.get()),
            filter_control=self._combo_filter_for_ini(self.control_var.get()),
            filter_status=self._status_filter_value() or "",
            filter_role=self._role_filter_value() or "",
            filter_programmer=self._combo_filter_for_ini(self.programmer_var.get()),
            sort_col=self._sort_col or "",
            sort_reverse=bool(self._sort_reverse),
            more_filters=bool(self._more_filters_open),
            folders_expanded=bool(self._folders_expanded)
            if hasattr(self, "_folders_expanded")
            else None,
            pelny_view=str(getattr(self, "_pelny_view", "praca") or "praca"),
            preview_find=self.preview_find_var.get().strip()
            if hasattr(self, "preview_find_var")
            else "",
        )

    def _combo_filter_for_ini(self, raw: str) -> str:
        s = (raw or "").strip()
        if not s or self._is_all_token(s):
            return ""
        return s

    def _sync_remap_vars_from_list(self) -> None:
        if self._path_remaps:
            self.remap_from_var.set(self._path_remaps[0].from_prefix)
            self.remap_to_var.set(self._path_remaps[0].to_prefix)
        else:
            self.remap_from_var.set("")
            self.remap_to_var.set("")

    def _collect_path_remaps(self) -> list[PathRemap]:
        """Primary from/to fields + any extra rules kept from the INI."""
        fr = self.remap_from_var.get().strip()
        to = self.remap_to_var.get().strip()
        extras = list(self._path_remaps[1:]) if len(self._path_remaps) > 1 else []
        if fr and to:
            return normalize_remaps([PathRemap(fr, to), *extras])
        return normalize_remaps(extras)

    def _active_path_remaps(self) -> list[PathRemap]:
        return self._collect_path_remaps()

    def _on_remap_changed(self, *_args) -> None:
        self._path_remaps = self._collect_path_remaps()
        self._on_folder_path_changed()

    def _pick_remap_to(self) -> None:
        path = filedialog.askdirectory(title=self._("path_remap_to"))
        if path:
            self.remap_to_var.set(path)
            self._on_remap_changed()

    def _add_path_remap_fields(self, parent: ttk.Frame, start_row: int) -> int:
        """Render client path-prefix remap (C:→Z:) fields; return next free row."""
        box = ttk.LabelFrame(
            parent, text=self._("path_remap"), padding=6
        )
        box.grid(
            row=start_row, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0)
        )
        ttk.Label(box, text=self._("path_remap_from")).grid(
            row=0, column=0, sticky=tk.W
        )
        ttk.Entry(box, textvariable=self.remap_from_var).grid(
            row=0, column=1, sticky=tk.EW, padx=4
        )
        ttk.Label(box, text="→").grid(row=0, column=2, padx=2)
        ttk.Label(box, text=self._("path_remap_to")).grid(
            row=1, column=0, sticky=tk.W, pady=(4, 0)
        )
        ttk.Entry(box, textvariable=self.remap_to_var).grid(
            row=1, column=1, sticky=tk.EW, padx=4, pady=(4, 0)
        )
        ttk.Button(
            box, text=self._("browse"), command=self._pick_remap_to
        ).grid(row=1, column=2, pady=(4, 0))
        ttk.Label(
            box, text=self._("path_remap_hint"), style="Muted.TLabel", wraplength=520
        ).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(4, 0))
        box.columnconfigure(1, weight=1)
        return start_row + 1

    def _on_scan_option_changed(self, *_args) -> None:
        if self._filter_trace_lock:
            return
        self._save_instance_ini()

    def _on_window_configure(self, event=None) -> None:
        # Only top-level geometry changes
        if event is not None and event.widget is not self:
            return
        if getattr(self, "_geometry_save_after_id", None):
            try:
                self.after_cancel(self._geometry_save_after_id)
            except tk.TclError:
                pass
        self._geometry_save_after_id = self.after(1200, self._save_instance_ini)

    def _save_instance_ini(self) -> None:
        try:
            save_instance_ini(self._instance_ini_path, config=self._collect_instance_config())
        except OSError:
            log.exception("save instance ini failed: %s", self._instance_ini_path)

    def _schedule_filter_ini_save(self) -> None:
        if getattr(self, "_filter_save_after_id", None):
            try:
                self.after_cancel(self._filter_save_after_id)
            except tk.TclError:
                pass
        self._filter_save_after_id = self.after(1000, self._save_instance_ini)

    def _on_folder_path_changed(self, *_args) -> None:
        if getattr(self, "_folder_save_after_id", None):
            try:
                self.after_cancel(self._folder_save_after_id)
            except tk.TclError:
                pass
        self._folder_save_after_id = self.after(800, self._save_instance_ini)
        # Debounced colour-catalog reload when the database folder changes
        if getattr(self, "_colour_load_after_id", None):
            try:
                self.after_cancel(self._colour_load_after_id)
            except tk.TclError:
                pass
        self._colour_load_after_id = self.after(400, self._load_colour_catalog)

    def _on_close(self) -> None:
        if (
            (not self._is_simple())
            and bool(self.close_to_tray_var.get())
            and tray_available()
        ):
            self._hide_to_tray()
            return
        self._quit_app()

    def _quit_app(self) -> None:
        if self._auto_refresh_after_id is not None:
            try:
                self.after_cancel(self._auto_refresh_after_id)
            except tk.TclError:
                pass
            self._auto_refresh_after_id = None
        self._stop_tray()
        self._stop_folder_watch(release=True)
        self._save_instance_ini()
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _hide_to_tray(self) -> None:
        if self._tray_hidden:
            return
        # Persist filters / geometry / toggles before hiding (X does not quit)
        self._save_instance_ini()
        if not self._ensure_tray():
            self._quit_app()
            return
        self._tray_hidden = True
        self._iconify_guard = True
        try:
            self.withdraw()
        except tk.TclError:
            pass
        finally:
            self._iconify_guard = False
        self.status_var.set(self._("tray_hint"))

    def _restore_from_tray(self) -> None:
        def _show() -> None:
            self._tray_hidden = False
            try:
                self.deiconify()
                self.lift()
                self.focus_force()
            except tk.TclError:
                pass
            self._bring_to_foreground()

        try:
            self.after(0, _show)
        except tk.TclError:
            _show()

    def _activate_from_second_launch(self) -> None:
        """Second process asked us to show — restore tray or raise window."""
        def _go() -> None:
            if getattr(self, "_tray_hidden", False):
                self._restore_from_tray()
                return
            try:
                self.deiconify()
                self.state("normal")
                self.lift()
                self.focus_force()
            except tk.TclError:
                pass
            self._bring_to_foreground()

        try:
            self.after(0, _go)
        except tk.TclError:
            _go()

    def _bring_to_foreground(self) -> None:
        """Windows: force Z-order when allowed (second-launch restore)."""
        if sys.platform != "win32":
            return
        try:
            import ctypes

            hwnd = int(self.winfo_id())
            user32 = ctypes.windll.user32
            # Climb to toplevel HWND
            cur = hwnd
            for _ in range(8):
                parent = user32.GetParent(cur)
                if not parent:
                    break
                cur = parent
            user32.ShowWindow(cur, 9)  # SW_RESTORE
            user32.SetForegroundWindow(cur)
        except Exception:  # noqa: BLE001
            log.debug("bring to foreground failed", exc_info=True)

    def _ensure_tray(self) -> bool:
        if not tray_available():
            return False
        if self._tray is not None and self._tray.running:
            return True
        self._tray = TrayController(
            title=self._("app_title"),
            on_restore=self._restore_from_tray,
            on_quit=lambda: self.after(0, self._quit_app),
            restore_label=self._("tray_restore"),
            quit_label=self._("tray_quit"),
        )
        return self._tray.start()

    def _stop_tray(self) -> None:
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:  # noqa: BLE001
                log.exception("stop tray failed")
            self._tray = None
        self._tray_hidden = False

    def _on_minimize_event(self, _event=None) -> None:
        if self._iconify_guard or self._is_simple():
            return
        if not bool(self.minimize_to_tray_var.get()) or not tray_available():
            return
        try:
            if self.state() == "iconic":
                self._hide_to_tray()
        except tk.TclError:
            pass

    def _ui_font(self, *, size: int = 10, bold: bool = False) -> tuple:
        family = "Segoe UI" if sys.platform == "win32" else "TkDefaultFont"
        weight = "bold" if bold else "normal"
        return (family, size, weight)

    def _configure_styles(self) -> None:
        """Emphasize primary labels / sections; secondary widgets stay muted."""
        style = ttk.Style(self)
        style.configure(
            "Key.TLabel",
            font=self._ui_font(size=10, bold=True),
            foreground=UI_KEY_FG,
        )
        style.configure(
            "Muted.TLabel",
            foreground=UI_MUTED_FG,
        )
        style.configure(
            "Primary.TLabelframe.Label",
            font=self._ui_font(size=10, bold=True),
            foreground=UI_ACCENT,
        )
        style.configure("Primary.TLabelframe", padding=8)
        style.configure(
            "Key.TEntry",
            font=self._ui_font(size=11, bold=False),
        )

    def _make_primary_button(self, parent: tk.Misc, text: str, command) -> tk.Button:
        """Colored primary CTA — tk.Button so accent survives Windows ttk themes."""
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=UI_ACCENT,
            fg=UI_ACCENT_TEXT,
            activebackground=UI_ACCENT_HOVER,
            activeforeground=UI_ACCENT_TEXT,
            disabledforeground="#c8c8c8",
            relief=tk.RAISED,
            borderwidth=1,
            padx=14,
            pady=5,
            font=self._ui_font(size=10, bold=True),
            cursor="hand2",
            highlightthickness=0,
        )

    def _set_primary_button_enabled(self, btn: tk.Button | None, enabled: bool) -> None:
        if btn is None:
            return
        try:
            if not btn.winfo_exists():
                return
        except tk.TclError:
            return
        if enabled:
            btn.configure(
                state=tk.NORMAL,
                bg=UI_ACCENT,
                fg=UI_ACCENT_TEXT,
                activebackground=UI_ACCENT_HOVER,
                activeforeground=UI_ACCENT_TEXT,
                cursor="hand2",
            )
        else:
            btn.configure(state=tk.DISABLED, cursor="arrow")

    def _all_token(self) -> str:
        return self._("all_paren")

    def _is_all_token(self, value: Optional[str]) -> bool:
        raw = (value or "").strip()
        return (not raw) or raw in ALL_TOKENS or raw == self._all_token()

    def _is_simple(self) -> bool:
        """Retrieve-only floor client when can_index is off."""
        return not self._can_index

    def _snapshot_ui(self) -> dict:
        return {
            "backup": self.backup_var.get(),
            "target": self.target_var.get(),
            "extract": self.extract_var.get(),
            "remap_from": self.remap_from_var.get(),
            "remap_to": self.remap_to_var.get(),
            "path_remaps": list(self._path_remaps),
            "search": self.search_var.get(),
            "date_from": self.date_from_var.get(),
            "date_to": self.date_to_var.get(),
            "size_min": self.size_min_var.get(),
            "size_max": self.size_max_var.get(),
            "mtime_from": self.mtime_from_var.get(),
            "mtime_to": self.mtime_to_var.get(),
            "source_type": self.source_type_var.get(),
            "control": self.control_var.get(),
            "provenance": self.provenance_var.get(),
            "role": self.role_var.get(),
            "programmer": self.programmer_var.get(),
            "newest": bool(self.newest_only_var.get()),
            "include_unknown": bool(self.include_unknown_var.get()),
            "incremental": bool(self.incremental_var.get()),
            "watch": bool(self.watch_var.get()),
            "watch_mode": self._watch_mode,
            "search_auto_refresh": bool(self.search_auto_refresh_var.get()),
            "excel": bool(self.excel_var.get()),
            "machines": self._selected_machines(),
            "roots": list(self._scan_root_specs()),
            "folders_expanded": bool(self._folders_expanded),
            "more_filters": bool(self._more_filters_open),
            "schedule": self._schedule,
            "sort_col": self._sort_col,
            "sort_reverse": bool(self._sort_reverse),
            "pelny_view": getattr(self, "_pelny_view", "praca"),
            "preview_find": self.preview_find_var.get(),
        }

    def _persist_ui_settings(self, target: Optional[str] = None) -> None:
        dest = (target if target is not None else self.target_var.get()).strip()
        if dest:
            try:
                save_ui_settings(
                    ui_settings_path_for_target(dest),
                    language=self._lang,
                    ui_mode=ui_mode_from_can_index(self._can_index),
                    schedule=self._schedule,
                    schedule_last_run=self._schedule_last_run or "",
                )
            except OSError:
                log.exception("save ui settings failed")
        self._save_instance_ini()

    def _set_language(self, lang: str, *, persist: bool = True) -> None:
        code = normalize_lang(lang)
        if code == self._lang and self._root_frame is not None:
            return
        preserved = self._snapshot_ui()
        self._lang = code
        self.lang_var.set(code)
        if persist:
            self._persist_ui_settings(preserved["target"])
        self._rebuild(preserved)

    def _rebuild(self, preserved: Optional[dict] = None) -> None:
        if self._root_frame is not None:
            self._root_frame.destroy()
            self._root_frame = None
        self._build()
        if preserved:
            self.backup_var.set(preserved.get("backup") or "")
            self.target_var.set(preserved.get("target") or "")
            self.extract_var.set(preserved.get("extract") or "")
            remaps = preserved.get("path_remaps")
            if remaps is not None:
                self._path_remaps = normalize_remaps(remaps)
            else:
                fr = str(preserved.get("remap_from") or "").strip()
                to = str(preserved.get("remap_to") or "").strip()
                self._path_remaps = (
                    normalize_remaps([PathRemap(fr, to)]) if fr and to else []
                )
            self._sync_remap_vars_from_list()
            self.search_var.set(preserved.get("search") or "")
            self.date_from_var.set(preserved.get("date_from") or "")
            self.date_to_var.set(preserved.get("date_to") or "")
            self.size_min_var.set(preserved.get("size_min") or "")
            self.size_max_var.set(preserved.get("size_max") or "")
            self.mtime_from_var.set(preserved.get("mtime_from") or "")
            self.mtime_to_var.set(preserved.get("mtime_to") or "")
            st = preserved.get("source_type") or self._all_token()
            if st in ALL_TOKENS:
                st = self._all_token()
            self.source_type_var.set(st)
            ctl = preserved.get("control") or self._all_token()
            if ctl in ALL_TOKENS:
                ctl = self._all_token()
            self.control_var.set(ctl)
            prog = preserved.get("programmer") or self._all_token()
            if prog in ALL_TOKENS:
                prog = self._all_token()
            self.programmer_var.set(prog)
            prov = str(preserved.get("provenance") or "")
            if prov in (PROVENANCE_BACKUP, "green", "on_machine") or prov == self._(
                "status_on_machine"
            ):
                self.provenance_var.set(self._("status_on_machine"))
            elif prov in (
                PROVENANCE_EXTRA,
                "yellow",
                "not_run",
                "unknown",
                "status_unknown",
            ) or prov in (self._("status_not_run"), self._("status_unknown")):
                self.provenance_var.set(self._("status_unknown"))
            else:
                self.provenance_var.set(self._all_token())
            role_raw = str(preserved.get("role") or "")
            if role_raw and not self._is_all_token(role_raw):
                c = self._colour_catalog.get(role_raw) or self._colour_catalog.get(
                    self._colour_id_from_filter_label(role_raw) or ""
                )
                self.role_var.set(c.label(self._lang) if c else self._all_token())
            else:
                self.role_var.set(self._all_token())
            self.newest_only_var.set(bool(preserved.get("newest")))
            if "include_unknown" in preserved:
                self.include_unknown_var.set(bool(preserved.get("include_unknown")))
            self.incremental_var.set(bool(preserved.get("incremental", True)))
            self.watch_var.set(bool(preserved.get("watch", False)))
            if preserved.get("watch_mode") is not None:
                self._watch_mode = normalize_watch_mode(str(preserved.get("watch_mode")))
                self.watch_mode_var.set(self._watch_mode_label(self._watch_mode))
            if "search_auto_refresh" in preserved:
                self.search_auto_refresh_var.set(
                    bool(preserved.get("search_auto_refresh"))
                )
            self.excel_var.set(bool(preserved.get("excel", True)))
            sort_col = preserved.get("sort_col")
            self._sort_col = str(sort_col) if sort_col else None
            self._sort_reverse = bool(preserved.get("sort_reverse"))
            roots = list(preserved.get("roots") or [])
            self._hidden_root_specs = [
                r if isinstance(r, ScanRootSpec) else ScanRootSpec(path=str(r))
                for r in roots
            ]
            self._fill_extra_list(self._hidden_root_specs)
            if preserved.get("schedule") is not None:
                self._set_schedule(str(preserved.get("schedule") or SCHEDULE_OFF), persist=False)
        self._refresh_filter_choices()
        if preserved and preserved.get("machines"):
            self._machine_sel = {
                m for m in preserved["machines"] if m in set(self._machine_names)
            }
            self._update_machines_button()
        if preserved is not None:
            if "folders_expanded" in preserved:
                self._set_folders_expanded(bool(preserved["folders_expanded"]), persist=False)
            else:
                self._maybe_auto_collapse_folders()
            if "more_filters" in preserved:
                self._more_filters_open = bool(preserved["more_filters"])
                self._apply_more_filters_visibility()
            if "preview_find" in preserved:
                self.preview_find_var.set(str(preserved.get("preview_find") or ""))
            view = str(preserved.get("pelny_view") or "").strip().casefold()
            if view in ("praca", "indeks") and not self._is_simple():
                self._show_pelny_view(view)
        self._sync_include_unknown_widget()
        self._run_query_now()
        self._sync_folder_watch()
        self._arm_search_auto_refresh()

    def _short_path(self, path: str, *, maxlen: int = 42) -> str:
        raw = (path or "").strip()
        if not raw:
            return self._("path_unset")
        if len(raw) <= maxlen:
            return raw
        return "…" + raw[-(maxlen - 1) :]

    def _folders_ready(self) -> bool:
        # Floor client (can_index=no): target/DB folder is enough; backup optional for extract.
        if self._is_simple():
            return bool(self.target_var.get().strip())
        return bool(self.backup_var.get().strip() and self.target_var.get().strip())

    def _update_folders_summary(self) -> None:
        if not hasattr(self, "_folders_summary_var"):
            return
        bak = self.backup_var.get().strip()
        tgt = self.target_var.get().strip()
        ext = self.extract_var.get().strip()
        unset = self._("path_unset")
        # Display resolved extract path (explicit or same as DB)
        extract_disp = self._short_path(ext or tgt) if (ext or tgt) else unset
        if self._is_simple():
            if not tgt:
                self._folders_summary_var.set(self._("folders_summary_empty_simple"))
            else:
                self._folders_summary_var.set(
                    self._(
                        "folders_summary_simple",
                        target=self._short_path(tgt),
                        extract=extract_disp,
                    )
                )
            self._sync_praca_path_from_summary()
            return
        if not bak and not tgt and not ext:
            self._folders_summary_var.set(self._("folders_summary_empty"))
        else:
            self._folders_summary_var.set(
                self._(
                    "folders_summary",
                    backup=self._short_path(bak) if bak else unset,
                    target=self._short_path(tgt) if tgt else unset,
                    extract=extract_disp,
                )
            )
        self._sync_praca_path_from_summary()

    def _sync_praca_path_from_summary(self) -> None:
        if hasattr(self, "_praca_path_var") and hasattr(self, "_folders_summary_var"):
            self._praca_path_var.set(self._folders_summary_var.get())

    def _extract_dir(self) -> str:
        """Resolved extract output folder (explicit extract, else database/target)."""
        return self.extract_var.get().strip() or self.target_var.get().strip()

    def _set_folders_expanded(self, expanded: bool, *, persist: bool = True) -> None:
        self._folders_expanded = bool(expanded)
        if not hasattr(self, "_folders_expanded_frame"):
            return
        before = getattr(self, "_actions_frame", None)
        pack_opts: dict = {"fill": tk.X, "padx": 8, "pady": 4}
        # Pack above index actions when they share a parent.
        try:
            if (
                before is not None
                and before.winfo_exists()
                and str(before.master) == str(self._folders_expanded_frame.master)
            ):
                pack_opts["before"] = before
        except tk.TclError:
            pass
        if self._folders_expanded:
            self._folders_summary_frame.pack_forget()
            self._folders_expanded_frame.pack(**pack_opts)
        else:
            self._folders_expanded_frame.pack_forget()
            self._update_folders_summary()
            self._folders_summary_frame.pack(**pack_opts)
        self._sync_praca_path_from_summary()
        if persist:
            self._schedule_filter_ini_save()

    def _maybe_auto_collapse_folders(self) -> None:
        """Collapse only when folders are already complete (startup / scan).

        Path pickers must **not** call this — operators need the panel to stay
        open so they can set extract (and extras) after choosing the DB folder.
        Explicit collapse is via **Gotowe** / **Done**.
        """
        if self._folders_ready() and self._folders_expanded:
            self._set_folders_expanded(False)

    def _expand_folders(self) -> None:
        self._set_folders_expanded(True)

    def _collapse_folders(self) -> None:
        if not self._folders_ready():
            messagebox.showinfo(
                self._("folders"),
                self._(
                    "folders_summary_empty_simple"
                    if self._is_simple()
                    else "folders_summary_empty"
                ),
            )
            return
        self._set_folders_expanded(False)

    def _update_machines_button(self) -> None:
        if not hasattr(self, "_machines_btn_var"):
            return
        selected = self._selected_machines()
        if not selected:
            self._machines_btn_var.set(self._("machines_all"))
        else:
            self._machines_btn_var.set(self._("machines_n", n=len(selected)))

    def _open_machine_picker(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title(self._("machines_pick"))
        dlg.transient(self)
        dlg.grab_set()
        dlg.geometry("420x360")
        frame = ttk.Frame(dlg, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=self._("machines"), style="Key.TLabel").pack(anchor=tk.W)
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 8))
        lb = tk.Listbox(list_frame, selectmode=tk.EXTENDED, exportselection=False)
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        for name in self._machine_names:
            lb.insert(tk.END, name)
        current = set(self._selected_machines())
        if not current:
            # empty selection means "all" in the query — show all highlighted
            lb.selection_set(0, tk.END)
        else:
            for i, name in enumerate(self._machine_names):
                if name in current:
                    lb.selection_set(i)
        btns = ttk.Frame(frame)
        btns.pack(fill=tk.X)
        ttk.Button(
            btns,
            text=self._("all"),
            command=lambda: lb.selection_set(0, tk.END),
        ).pack(side=tk.LEFT)
        ttk.Button(
            btns,
            text=self._("none"),
            command=lambda: lb.selection_clear(0, tk.END),
        ).pack(side=tk.LEFT, padx=4)
        ttk.Label(btns, text=self._("multi_hint"), style="Muted.TLabel").pack(
            side=tk.LEFT, padx=8
        )

        def _apply() -> None:
            sel = lb.curselection()
            names = [lb.get(i) for i in sel]
            if not names or (
                self._machine_names and len(names) == len(self._machine_names)
            ):
                self._machine_sel = set()
            else:
                self._machine_sel = set(names)
            self._update_machines_button()
            self._on_filter_changed()
            dlg.destroy()

        bottom = ttk.Frame(frame)
        bottom.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(bottom, text=self._("ok"), command=_apply).pack(side=tk.RIGHT)
        ttk.Button(bottom, text=self._("cancel"), command=dlg.destroy).pack(
            side=tk.RIGHT, padx=6
        )
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        dlg.wait_window()

    def _toggle_more_filters(self) -> None:
        self._more_filters_open = not self._more_filters_open
        self._apply_more_filters_visibility()
        self._schedule_filter_ini_save()

    def _apply_more_filters_visibility(self) -> None:
        if not hasattr(self, "_more_filters_frame"):
            return
        if self._more_filters_open:
            self._more_filters_frame.pack(fill=tk.X, pady=(6, 0))
            if hasattr(self, "_more_filters_btn"):
                self._more_filters_btn.configure(text=self._("fewer_filters"))
        else:
            self._more_filters_frame.pack_forget()
            if hasattr(self, "_more_filters_btn"):
                self._more_filters_btn.configure(text=self._("more_filters"))

    def _show_progress(self, visible: bool) -> None:
        if not hasattr(self, "prog_frame"):
            return
        if visible:
            if not self.prog_frame.winfo_ismapped():
                # Prefer Index tab chrome; fall back to packing in parent.
                after = getattr(self, "_actions_frame", None)
                pack_opts: dict = {"fill": tk.X, "padx": 8, "pady": 4}
                if after is not None and after.winfo_exists():
                    pack_opts["after"] = after
                self.prog_frame.pack(**pack_opts)
                # If scanning from Praca, jump to Indeks so progress is visible.
                self._goto_indeks_tab()
        else:
            self.prog_frame.pack_forget()

    def _goto_indeks_tab(self) -> None:
        self._show_pelny_view("indeks")

    def _goto_praca_tab(self) -> None:
        self._show_pelny_view("praca")

    def _show_pelny_view(self, which: str) -> None:
        """Switch indexer primary nav between Praca and Indeks."""
        if self._is_simple():
            return
        praca = getattr(self, "_praca_frame", None)
        indeks = getattr(self, "_indeks_frame", None)
        if praca is None or indeks is None:
            return
        view = "indeks" if which == "indeks" else "praca"
        self._pelny_view = view
        try:
            if view == "praca":
                indeks.pack_forget()
                if not praca.winfo_ismapped():
                    praca.pack(fill=tk.BOTH, expand=True)
            else:
                praca.pack_forget()
                if not indeks.winfo_ismapped():
                    indeks.pack(fill=tk.BOTH, expand=True)
        except tk.TclError:
            return
        self._refresh_pelny_nav_styles()
        self._schedule_filter_ini_save()

    def _refresh_pelny_nav_styles(self) -> None:
        """Bold / accent selected segment; muted idle segment."""
        view = getattr(self, "_pelny_view", "praca")
        pairs = (
            (getattr(self, "_nav_praca_btn", None), view == "praca"),
            (getattr(self, "_nav_indeks_btn", None), view == "indeks"),
        )
        for btn, selected in pairs:
            if btn is None:
                continue
            try:
                if not btn.winfo_exists():
                    continue
            except tk.TclError:
                continue
            if selected:
                btn.configure(
                    bg=UI_ACCENT,
                    fg=UI_ACCENT_TEXT,
                    activebackground=UI_ACCENT_HOVER,
                    activeforeground=UI_ACCENT_TEXT,
                    relief=tk.SUNKEN,
                    font=self._ui_font(size=13, bold=True),
                )
            else:
                btn.configure(
                    bg=UI_NAV_IDLE_BG,
                    fg=UI_NAV_IDLE_FG,
                    activebackground=UI_NAV_IDLE_HOVER,
                    activeforeground=UI_NAV_IDLE_FG,
                    relief=tk.RAISED,
                    font=self._ui_font(size=13, bold=False),
                )

    def _build_pelny_nav(self, parent, pad: dict) -> None:
        """Large segmented Praca | Indeks control — primary indexer navigation."""
        wrap = ttk.Frame(parent)
        wrap.pack(fill=tk.X, **pad)
        strip = tk.Frame(wrap, bg=UI_NAV_BORDER, padx=2, pady=2)
        strip.pack(fill=tk.X)
        inner = tk.Frame(strip, bg=UI_NAV_BORDER)
        inner.pack(fill=tk.X)
        btn_opts = dict(
            relief=tk.RAISED,
            borderwidth=1,
            padx=28,
            pady=12,
            cursor="hand2",
            highlightthickness=0,
            font=self._ui_font(size=13, bold=False),
        )
        self._nav_praca_btn = tk.Button(
            inner,
            text=self._("tab_praca"),
            command=lambda: self._show_pelny_view("praca"),
            **btn_opts,
        )
        self._nav_praca_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 1))
        self._nav_indeks_btn = tk.Button(
            inner,
            text=self._("tab_indeks"),
            command=lambda: self._show_pelny_view("indeks"),
            **btn_opts,
        )
        self._nav_indeks_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(1, 0))
        self._pelny_view = "praca"
        self._refresh_pelny_nav_styles()

    def _open_indeks_folders(self) -> None:
        """From Praca path line: switch to Indeks and expand folder editors."""
        self._goto_indeks_tab()
        self._set_folders_expanded(True)

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        simple = self._is_simple()
        self.title(window_title(self._("app_title")))
        self._update_machines_button()
        self._build_menubar()
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)
        self._root_frame = root
        self._main_notebook = None  # legacy name; indexer uses segmented nav
        self._praca_frame = None
        self._indeks_frame = None
        self._nav_praca_btn = None
        self._nav_indeks_btn = None
        self._pelny_view = "praca"

        # Ensure filter "all" token matches current language
        if self._is_all_token(self.source_type_var.get()):
            self.source_type_var.set(self._all_token())
        if self._is_all_token(self.control_var.get()):
            self.control_var.set(self._all_token())
        if self._is_all_token(self.programmer_var.get()):
            self.programmer_var.set(self._all_token())
        if self._is_all_token(self.provenance_var.get()) or not self.provenance_var.get():
            self.provenance_var.set(self._all_token())
        if not self.status_var.get():
            self.status_var.set(
                self._("status_pick_simple") if simple else self._("status_pick")
            )
        if not self.preview_header_var.get():
            self.preview_header_var.set(self._("preview_idle"))

        # --- Top chrome: language / help (capability comes from gcode-index.ini) ---
        top = ttk.Frame(root)
        top.pack(fill=tk.X, **pad)
        settings = ttk.Frame(top)
        settings.pack(side=tk.RIGHT)
        ttk.Label(settings, text=self._("language"), style="Muted.TLabel").pack(
            side=tk.LEFT, padx=(0, 2)
        )
        lang_combo = ttk.Combobox(
            settings,
            textvariable=self.lang_var,
            values=["pl", "en"],
            state="readonly",
            width=6,
        )
        lang_combo.pack(side=tk.LEFT)
        lang_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._set_language(self.lang_var.get())
        )
        ttk.Button(
            settings,
            text=self._("menu_help"),
            command=lambda: self._open_manual("simple" if simple else "full"),
        ).pack(side=tk.LEFT, padx=(12, 0))

        if simple:
            # Floor client (can_index=no): retrieve-only — no Praca/Indeks tabs.
            self._build_folders_section(root, pad, simple=True)
            self._build_simple_actions(root, pad)
            self._build_progress_bar(root)
            self._build_find_section(root, pad, simple=True)
            self._build_results_preview(root, pad, simple=True)
        else:
            # Indexer (can_index=yes): Praca | Indeks segmented primary nav.
            self._build_pelny_nav(root, pad)
            content = ttk.Frame(root)
            content.pack(fill=tk.BOTH, expand=True, **pad)
            self._pelny_content = content
            praca = ttk.Frame(content, padding=4)
            indeks = ttk.Frame(content, padding=4)
            self._praca_frame = praca
            self._indeks_frame = indeks

            # Praca: one-line path + find + results|full-height preview
            self._build_praca_path_line(praca, pad)
            self._build_find_section(praca, pad, simple=False)
            self._build_results_preview(praca, pad, simple=False)

            # Indeks: folders, remap, scan/watch/schedule/tray, progress
            self._build_folders_section(indeks, pad, simple=False)
            self._build_full_index_actions(indeks, pad)
            self._build_progress_bar(indeks)

            # Default to Praca when folders already configured
            if self._folders_ready():
                self._show_pelny_view("praca")
            else:
                self._show_pelny_view("indeks")
                self._set_folders_expanded(True, persist=False)

        status = ttk.Label(root, textvariable=self.status_var, anchor=tk.W)
        status.pack(fill=tk.X, **pad)


    def _build_folders_section(self, parent, pad: dict, *, simple: bool) -> None:
        """Folder summary + expanded editors (floor client root or indexer Indeks)."""
        self._folders_summary_frame = ttk.Frame(parent)
        self._update_folders_summary()
        ttk.Label(
            self._folders_summary_frame,
            textvariable=self._folders_summary_var,
            style="Key.TLabel",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            self._folders_summary_frame,
            text=self._("change_folders"),
            command=self._expand_folders,
        ).pack(side=tk.RIGHT)

        self._folders_expanded_frame = ttk.LabelFrame(
            parent,
            text=(
                self._("folders_step_simple") if simple else self._("folders")
            ),
            padding=8,
            style="Primary.TLabelframe",
        )
        paths = self._folders_expanded_frame
        if simple:
            # Floor client: no backup/DB path pickers — open DB via the primary button.
            # Optional extract folder only.
            ttk.Label(
                paths,
                text=self._("extract_folder"),
                style="Key.TLabel",
            ).grid(row=0, column=0, sticky=tk.W)
            ttk.Entry(paths, textvariable=self.extract_var, style="Key.TEntry").grid(
                row=0, column=1, sticky=tk.EW, padx=4, ipady=2
            )
            ttk.Button(paths, text=self._("browse"), command=self._pick_extract).grid(
                row=0, column=2
            )
            ttk.Label(
                paths,
                text=self._("extract_folder_hint_simple"),
                style="Muted.TLabel",
            ).grid(row=1, column=1, sticky=tk.W, padx=4, pady=(0, 2))
            done_row_idx = self._add_path_remap_fields(paths, 2)
        else:
            ttk.Label(
                paths,
                text=self._("backup_folder"),
                style="Key.TLabel",
            ).grid(row=0, column=0, sticky=tk.W)
            ttk.Entry(paths, textvariable=self.backup_var, style="Key.TEntry").grid(
                row=0, column=1, sticky=tk.EW, padx=4, ipady=2
            )
            ttk.Button(paths, text=self._("browse"), command=self._pick_backup).grid(
                row=0, column=2
            )

            ttk.Label(
                paths,
                text=self._("target_folder"),
                style="Key.TLabel",
            ).grid(row=1, column=0, sticky=tk.W)
            ttk.Entry(paths, textvariable=self.target_var, style="Key.TEntry").grid(
                row=1, column=1, sticky=tk.EW, padx=4, ipady=2
            )
            ttk.Button(paths, text=self._("browse"), command=self._pick_target).grid(
                row=1, column=2
            )

            ttk.Label(
                paths,
                text=self._("extract_folder"),
                style="Key.TLabel",
            ).grid(row=2, column=0, sticky=tk.W)
            ttk.Entry(paths, textvariable=self.extract_var, style="Key.TEntry").grid(
                row=2, column=1, sticky=tk.EW, padx=4, ipady=2
            )
            ttk.Button(paths, text=self._("browse"), command=self._pick_extract).grid(
                row=2, column=2
            )
            ttk.Label(
                paths,
                text=self._("extract_folder_hint"),
                style="Muted.TLabel",
            ).grid(row=3, column=1, sticky=tk.W, padx=4, pady=(0, 2))

            # Additional folders (green catch + yellow extras) — indexer only
            extra = ttk.LabelFrame(
                paths,
                text=self._("extra_folders"),
                padding=6,
            )
            extra.grid(row=4, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
            extra_row = ttk.Frame(extra)
            extra_row.pack(fill=tk.X)
            self.extra_list = tk.Listbox(extra_row, height=3, selectmode=tk.EXTENDED)
            extra_sb = ttk.Scrollbar(
                extra_row, orient=tk.VERTICAL, command=self.extra_list.yview
            )
            self.extra_list.configure(yscrollcommand=extra_sb.set)
            self.extra_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            extra_sb.pack(side=tk.RIGHT, fill=tk.Y)
            extra_btns = ttk.Frame(extra)
            extra_btns.pack(fill=tk.X, pady=(4, 0))
            ttk.Button(
                extra_btns,
                text=self._("add_green_folder"),
                command=lambda: self._add_scan_root(PROVENANCE_BACKUP),
            ).pack(side=tk.LEFT)
            ttk.Button(
                extra_btns,
                text=self._("add_yellow_folder"),
                command=lambda: self._add_scan_root(PROVENANCE_EXTRA),
            ).pack(side=tk.LEFT, padx=4)
            ttk.Button(
                extra_btns,
                text=self._("remove_selected"),
                command=self._remove_extra_roots,
            ).pack(side=tk.LEFT, padx=4)
            ttk.Label(extra_btns, text=self._("extra_hint"), style="Muted.TLabel").pack(
                side=tk.LEFT, padx=8
            )
            self._fill_extra_list(self._hidden_root_specs)
            done_row_idx = self._add_path_remap_fields(paths, 5)

        if simple and hasattr(self, "extra_list"):
            delattr(self, "extra_list")

        paths.columnconfigure(1, weight=1)

        done_row = ttk.Frame(paths)
        done_row.grid(
            row=done_row_idx,
            column=0,
            columnspan=3,
            sticky=tk.E,
            pady=(8, 0),
        )
        ttk.Button(
            done_row, text=self._("folders_done"), command=self._collapse_folders
        ).pack(side=tk.RIGHT)

        # Initial folders visibility
        if self._folders_expanded or not self._folders_ready():
            self._folders_expanded = True
            self._folders_expanded_frame.pack(fill=tk.X, **pad)
        else:
            self._folders_summary_frame.pack(fill=tk.X, **pad)


    def _build_simple_actions(self, parent, pad: dict) -> None:
        """Floor client (can_index=no): Open DB + clear filters."""
        actions = ttk.Frame(parent)
        self._actions_frame = actions
        actions.pack(fill=tk.X, **pad)
        row1 = ttk.Frame(actions)
        row1.pack(fill=tk.X)
        self.scan_btn = None
        self.open_db_btn = self._make_primary_button(
            row1, self._("open_db"), self._pick_existing_db
        )
        self.open_db_btn.pack(side=tk.LEFT)
        ttk.Button(
            row1, text=self._("clear_filters"), command=self._clear_filters
        ).pack(side=tk.LEFT, padx=8)


    def _build_full_index_actions(self, parent, pad: dict) -> None:
        """Indexer Indeks tab: scan, map, schedule, watch, tray, report tools."""
        actions = ttk.Frame(parent)
        self._actions_frame = actions
        actions.pack(fill=tk.X, **pad)

        row1 = ttk.Frame(actions)
        row1.pack(fill=tk.X)
        # Row 1 — primary: index + folder tools (always visible)
        self.scan_btn = self._make_primary_button(
            row1, self._("run_scan"), self._start_scan
        )
        self.scan_btn.pack(side=tk.LEFT)
        ttk.Button(
            row1, text=self._("map_folders"), command=self._open_folder_map
        ).pack(side=tk.LEFT, padx=8)
        ttk.Button(
            row1, text=self._("map_tree"), command=self._open_folder_tree_map
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            row1, text=self._("aliases"), command=self._open_alias_editor
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            row1, text=self._("folder_colours"), command=self._open_folder_colour_editor
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            row1, text=self._("open_db"), command=self._pick_existing_db
        ).pack(side=tk.LEFT, padx=8)

        # Row 2 — secondary tools + scan options (incl. watch) + schedule
        row2 = ttk.Frame(actions)
        row2.pack(fill=tk.X, pady=(4, 0))
        sched = ttk.Frame(row2)
        sched.pack(side=tk.RIGHT)
        ttk.Label(sched, text=self._("schedule"), style="Muted.TLabel").pack(
            side=tk.LEFT, padx=(0, 2)
        )
        self._sync_schedule_widgets()
        amount_entry = ttk.Entry(
            sched, textvariable=self.schedule_amount_var, width=5
        )
        amount_entry.pack(side=tk.LEFT)
        amount_entry.bind("<FocusOut>", self._on_schedule_widgets_changed)
        amount_entry.bind("<Return>", self._on_schedule_widgets_changed)
        amount_entry.bind("<KeyRelease>", self._on_schedule_amount_typed)
        unit_combo = ttk.Combobox(
            sched,
            textvariable=self.schedule_unit_var,
            values=self._schedule_unit_labels(),
            state="readonly",
            width=10,
        )
        unit_combo.pack(side=tk.LEFT, padx=(4, 0))
        unit_combo.bind("<<ComboboxSelected>>", self._on_schedule_widgets_changed)
        ttk.Label(
            sched, textvariable=self.schedule_status_var, style="Muted.TLabel"
        ).pack(side=tk.LEFT, padx=(8, 0))
        self._update_schedule_status()

        ttk.Button(
            row2, text=self._("scan_report"), command=self._open_scan_report
        ).pack(side=tk.LEFT)
        ttk.Button(
            row2, text=self._("scan_history"), command=self._open_scan_history
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            row2, text=self._("duplicates"), command=self._open_duplicates
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            row2, text=self._("clear_filters"), command=self._clear_filters
        ).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(
            row2, text=self._("also_excel"), variable=self.excel_var
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Checkbutton(
            row2, text=self._("incremental"), variable=self.incremental_var
        ).pack(side=tk.LEFT, padx=8)
        ttk.Checkbutton(
            row2,
            text=self._("watch_folders"),
            variable=self.watch_var,
            command=self._on_watch_toggled,
        ).pack(side=tk.LEFT, padx=4)
        self._build_watch_mode_segment(row2)
        ttk.Label(
            row2, textvariable=self.watch_status_var, style="Muted.TLabel"
        ).pack(side=tk.LEFT, padx=(4, 0))
        self._update_watch_status()

        # Row 3 — autostart / tray prefs (indexer, Windows-oriented)
        row3 = ttk.Frame(actions)
        row3.pack(fill=tk.X, pady=(4, 0))
        if tray_available():
            ttk.Checkbutton(
                row3,
                text=self._("close_to_tray"),
                variable=self.close_to_tray_var,
                command=self._on_desktop_pref_changed,
            ).pack(side=tk.LEFT)
            ttk.Checkbutton(
                row3,
                text=self._("minimize_to_tray"),
                variable=self.minimize_to_tray_var,
                command=self._on_desktop_pref_changed,
            ).pack(side=tk.LEFT, padx=(8, 0))
        if autostart_is_windows():
            ttk.Checkbutton(
                row3,
                text=self._("autostart"),
                variable=self.autostart_var,
                command=self._on_autostart_toggled,
            ).pack(side=tk.LEFT, padx=(12, 0))
            self.autostart_via_var.set(
                self._autostart_via_label(self._autostart_via_code())
            )
            via = ttk.Combobox(
                row3,
                textvariable=self.autostart_via_var,
                values=[
                    self._("autostart_via_startup"),
                    self._("autostart_via_task"),
                ],
                state="readonly",
                width=18,
            )
            via.pack(side=tk.LEFT, padx=(4, 0))
            via.bind("<<ComboboxSelected>>", self._on_autostart_via_selected)

        # Compact watch health strip
        strip = ttk.Frame(actions)
        strip.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(strip, text=self._("watch_strip") + ":", style="Muted.TLabel").pack(
            side=tk.LEFT
        )
        ttk.Label(
            strip, textvariable=self.watch_strip_var, style="Muted.TLabel"
        ).pack(side=tk.LEFT, padx=(4, 0))
        self._refresh_watch_strip()


    def _build_progress_bar(self, parent) -> None:
        """Progress bar host (packed only while scanning)."""
        self.prog_frame = ttk.Frame(parent)
        self.progress = ttk.Progressbar(
            self.prog_frame,
            mode="determinate",
            maximum=100.0,
            variable=self.progress_var,
        )
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            self.prog_frame, textvariable=self.progress_label_var, width=42
        ).pack(side=tk.LEFT, padx=(8, 0))


    def _build_praca_path_line(self, parent, pad: dict) -> None:
        """One-line path summary on Praca (no fat folder/remap chrome)."""
        self._praca_path_var = tk.StringVar(value="")
        line = ttk.Frame(parent)
        line.pack(fill=tk.X, **pad)
        ttk.Label(
            line, textvariable=self._praca_path_var, style="Muted.TLabel"
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            line,
            text=self._("goto_indeks"),
            command=self._open_indeks_folders,
        ).pack(side=tk.RIGHT)
        self._update_folders_summary()


    def _build_find_section(self, parent, pad: dict, *, simple: bool) -> None:
        """Search / filter bar with primary Wydobądź CTA."""
        find_title = self._("find_programs_step") if simple else self._("find_programs")
        self.filt_frame = ttk.LabelFrame(
            parent, text=find_title, padding=8, style="Primary.TLabelframe"
        )
        self.filt_frame.pack(fill=tk.X, **pad)
        filt = self.filt_frame

        ttk.Label(filt, text=self._("text"), style="Key.TLabel").grid(
            row=0, column=0, sticky=tk.W
        )
        self.search_entry = ttk.Entry(
            filt, textvariable=self.search_var, style="Key.TEntry"
        )
        self.search_entry.grid(
            row=0, column=1, sticky=tk.EW, padx=4, ipady=3
        )
        ttk.Button(
            filt,
            textvariable=self._machines_btn_var,
            command=self._open_machine_picker,
            width=18,
        ).grid(row=0, column=2, padx=4)
        ttk.Label(filt, text=self._("date_from"), style="Key.TLabel").grid(
            row=0, column=3, sticky=tk.W, padx=(8, 2)
        )
        self._date_entry(filt, self.date_from_var).grid(row=0, column=4, sticky=tk.W)
        ttk.Label(filt, text=self._("date_to_sep")).grid(row=0, column=5, sticky=tk.W)
        self._date_entry(filt, self.date_to_var).grid(row=0, column=6, sticky=tk.W)
        ttk.Checkbutton(
            filt,
            text=self._("newest_only"),
            variable=self.newest_only_var,
        ).grid(row=0, column=7, sticky=tk.E, padx=4)
        self.extract_btn = self._make_primary_button(
            filt, self._("extract_selected"), self._extract_selected
        )
        self.extract_btn.grid(row=0, column=8, padx=4)
        filt.columnconfigure(1, weight=1)

        row2 = ttk.Frame(filt)
        row2.grid(row=1, column=0, columnspan=9, sticky=tk.EW, pady=(6, 0))
        ttk.Button(
            row2, text=self._("open_folder"), command=self._open_selected_folder
        ).pack(side=tk.LEFT)
        ttk.Button(
            row2, text=self._("copy_path"), command=self._copy_selected_path
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            row2, text=self._("clear_filters"), command=self._clear_filters
        ).pack(side=tk.LEFT, padx=4)
        self._include_unknown_cb = ttk.Checkbutton(
            row2,
            text=self._("include_unknown"),
            variable=self.include_unknown_var,
            command=self._on_include_unknown_toggled,
        )
        self._include_unknown_cb.pack(side=tk.LEFT, padx=(12, 0))
        self._sync_include_unknown_widget()
        ttk.Checkbutton(
            row2,
            text=self._("search_auto_refresh"),
            variable=self.search_auto_refresh_var,
            command=self._on_search_auto_refresh_toggled,
        ).pack(side=tk.LEFT, padx=(12, 0))
        if not simple:
            ttk.Button(
                row2, text=self._("compare"), command=self._compare_selected
            ).pack(side=tk.LEFT, padx=4)
            self._more_filters_btn = ttk.Button(
                row2,
                text=self._("more_filters"),
                command=self._toggle_more_filters,
            )
            self._more_filters_btn.pack(side=tk.LEFT, padx=8)

            self._more_filters_frame = ttk.Frame(filt)
            adv = self._more_filters_frame
            ttk.Label(adv, text=self._("source_type")).grid(
                row=0, column=0, sticky=tk.W, pady=2
            )
            self.type_combo = ttk.Combobox(
                adv,
                textvariable=self.source_type_var,
                values=[self._all_token()],
                state="readonly",
                width=22,
            )
            self.type_combo.grid(row=0, column=1, sticky=tk.W, padx=4, pady=2)

            ttk.Label(adv, text=self._("control")).grid(
                row=0, column=2, sticky=tk.W, padx=(12, 0), pady=2
            )
            self.control_combo = ttk.Combobox(
                adv,
                textvariable=self.control_var,
                values=[self._all_token()],
                state="readonly",
                width=14,
            )
            self.control_combo.grid(row=0, column=3, sticky=tk.W, padx=4, pady=2)

            ttk.Label(adv, text=self._("filter_status")).grid(
                row=0, column=4, sticky=tk.W, padx=(12, 0), pady=2
            )
            self.provenance_combo = ttk.Combobox(
                adv,
                textvariable=self.provenance_var,
                values=self._status_filter_labels(),
                state="readonly",
                width=18,
            )
            self.provenance_combo.grid(row=0, column=5, sticky=tk.W, padx=4, pady=2)

            ttk.Label(adv, text=self._("filter_role")).grid(
                row=0, column=6, sticky=tk.W, padx=(12, 0), pady=2
            )
            self.role_combo = ttk.Combobox(
                adv,
                textvariable=self.role_var,
                values=self._role_filter_labels(),
                state="readonly",
                width=18,
            )
            self.role_combo.grid(row=0, column=7, sticky=tk.W, padx=4, pady=2)

            ttk.Label(adv, text=self._("programmer")).grid(
                row=1, column=0, sticky=tk.W, pady=2
            )
            self.programmer_combo = ttk.Combobox(
                adv,
                textvariable=self.programmer_var,
                values=[self._all_token()],
                state="readonly",
                width=14,
            )
            self.programmer_combo.grid(row=1, column=1, sticky=tk.W, padx=4, pady=2)

            ttk.Label(adv, text=self._("preset")).grid(
                row=1, column=2, sticky=tk.W, padx=(12, 0), pady=2
            )
            preset_row = ttk.Frame(adv)
            preset_row.grid(row=1, column=3, columnspan=5, sticky=tk.W, padx=4, pady=2)
            self.preset_combo = ttk.Combobox(
                preset_row,
                textvariable=self.preset_var,
                values=[],
                state="readonly",
                width=22,
            )
            self.preset_combo.pack(side=tk.LEFT)
            ttk.Button(
                preset_row, text=self._("load"), command=self._load_selected_preset
            ).pack(side=tk.LEFT, padx=4)
            ttk.Button(
                preset_row,
                text=self._("save_current"),
                command=self._save_current_preset,
            ).pack(side=tk.LEFT, padx=2)
            ttk.Button(
                preset_row,
                text=self._("delete"),
                command=self._delete_selected_preset,
            ).pack(side=tk.LEFT, padx=2)

            # Size / file-date ranges (#10) — Full more-filters only
            ttk.Label(adv, text=self._("size_from")).grid(
                row=2, column=0, sticky=tk.W, pady=2
            )
            size_row = ttk.Frame(adv)
            size_row.grid(row=2, column=1, sticky=tk.W, padx=4, pady=2)
            ttk.Entry(size_row, textvariable=self.size_min_var, width=10).pack(
                side=tk.LEFT
            )
            ttk.Label(size_row, text=self._("size_to_sep")).pack(side=tk.LEFT)
            ttk.Entry(size_row, textvariable=self.size_max_var, width=10).pack(
                side=tk.LEFT
            )
            ttk.Label(adv, text=self._("size_hint"), style="Muted.TLabel").grid(
                row=2, column=2, columnspan=2, sticky=tk.W, padx=(12, 0), pady=2
            )

            ttk.Label(adv, text=self._("mtime_from")).grid(
                row=3, column=0, sticky=tk.W, pady=2
            )
            mtime_row = ttk.Frame(adv)
            mtime_row.grid(row=3, column=1, sticky=tk.W, padx=4, pady=2)
            self._date_entry(mtime_row, self.mtime_from_var).pack(side=tk.LEFT)
            ttk.Label(mtime_row, text=self._("mtime_to_sep")).pack(side=tk.LEFT)
            self._date_entry(mtime_row, self.mtime_to_var).pack(side=tk.LEFT)
            ttk.Label(adv, text=self._("mtime_hint"), style="Muted.TLabel").grid(
                row=3, column=2, columnspan=2, sticky=tk.W, padx=(12, 0), pady=2
            )

            self._apply_more_filters_visibility()
        else:
            for attr in (
                "type_combo",
                "control_combo",
                "provenance_combo",
                "role_combo",
                "programmer_combo",
                "preset_combo",
                "_more_filters_frame",
                "_more_filters_btn",
            ):
                if hasattr(self, attr):
                    delattr(self, attr)


    def _build_results_preview(self, parent, pad: dict, *, simple: bool) -> None:
        """Results table with full-height preview dock on the right."""
        cols = (
            "flag",
            "src",
            "program",
            "part",
            "programmer",
            "machine",
            "date",
            "size",
            "type",
            "control",
            "path",
            "location",
        )
        results_pane = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        results_pane.pack(fill=tk.BOTH, expand=True, **pad)
        self._results_pane = results_pane

        tree_frame = ttk.Frame(results_pane)
        results_pane.add(tree_frame, weight=3)
        self.tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings", selectmode="extended"
        )
        headings = {
            "flag": (self._("col_flag"), 72),
            "src": (self._("col_src"), 64),
            "program": (self._("col_program"), 90),
            "part": (self._("col_part"), 130),
            "programmer": (self._("col_programmer"), 56),
            "machine": (self._("col_machine"), 110),
            "date": (self._("col_date"), 100),
            "size": (self._("col_size"), 70),
            "type": (self._("col_type"), 100),
            "control": (self._("col_control"), 70),
            "path": (self._("col_path"), 240),
            "location": (self._("col_location"), 120),
        }
        self._heading_labels = {k: label for k, (label, _w) in headings.items()}
        for key, (label, width) in headings.items():
            self.tree.heading(
                key, text=label, command=lambda c=key: self._on_sort_column(c)
            )
            stretch = key in ("path", "part")
            self.tree.column(key, width=width, stretch=stretch, minwidth=40)
        self._refresh_heading_labels()
        self.tree.tag_configure("flag_backup", foreground=STATUS_SWATCH[PROVENANCE_BACKUP])
        self.tree.tag_configure("flag_extra", foreground=STATUS_SWATCH[PROVENANCE_EXTRA])
        self.tree.tag_configure("flag_wip", foreground="#c0392b")
        self._configure_colour_tags()
        # Missing source: dim grey + distinct from provenance colours
        self.tree.tag_configure("source_missing", foreground="#8a1f1f")
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _e: self._extract_selected())
        self.tree.bind("<Button-3>", self._on_tree_context)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        if sys.platform == "darwin":
            self.tree.bind("<Button-2>", self._on_tree_context)
            self.tree.bind("<Control-Button-1>", self._on_tree_context)

        preview_frame = ttk.LabelFrame(
            results_pane,
            text=self._("preview"),
            padding=4,
            style="Primary.TLabelframe",
        )
        results_pane.add(preview_frame, weight=2)
        ttk.Label(preview_frame, textvariable=self.preview_header_var).pack(
            fill=tk.X, padx=2, pady=(0, 2)
        )
        find_row = ttk.Frame(preview_frame)
        find_row.pack(fill=tk.X, padx=2, pady=(0, 4))
        ttk.Label(find_row, text=self._("preview_find"), style="Muted.TLabel").pack(
            side=tk.LEFT
        )
        self.preview_find_entry = ttk.Entry(
            find_row, textvariable=self.preview_find_var, width=18
        )
        self.preview_find_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.preview_find_entry.bind("<Return>", self._preview_find_next)
        self.preview_find_entry.bind("<Shift-Return>", self._preview_find_prev)
        self.preview_find_entry.bind("<KeyRelease>", self._on_preview_find_typed)
        ttk.Button(
            find_row, text=self._("preview_find_prev"), width=3, command=self._preview_find_prev
        ).pack(side=tk.LEFT)
        ttk.Button(
            find_row, text=self._("preview_find_next"), width=3, command=self._preview_find_next
        ).pack(side=tk.LEFT, padx=(2, 0))
        ttk.Label(
            find_row, textvariable=self.preview_find_status_var, style="Muted.TLabel"
        ).pack(side=tk.LEFT, padx=(6, 0))
        prev_inner = ttk.Frame(preview_frame)
        prev_inner.pack(fill=tk.BOTH, expand=True)
        self.preview_text = tk.Text(
            prev_inner,
            wrap=tk.NONE,
            height=1,
            font=("Consolas", 10),
            state=tk.DISABLED,
        )
        prev_vsb = ttk.Scrollbar(
            prev_inner, orient=tk.VERTICAL, command=self.preview_text.yview
        )
        prev_hsb = ttk.Scrollbar(
            prev_inner, orient=tk.HORIZONTAL, command=self.preview_text.xview
        )
        self.preview_text.configure(
            yscrollcommand=prev_vsb.set, xscrollcommand=prev_hsb.set
        )
        self.preview_text.tag_configure(
            "preview_find_hit", background="#ffe58a", foreground="#222222"
        )
        self.preview_text.tag_configure(
            "preview_find_current", background="#f0a202", foreground="#111111"
        )
        self.preview_text.grid(row=0, column=0, sticky="nsew")
        prev_vsb.grid(row=0, column=1, sticky="ns")
        prev_hsb.grid(row=1, column=0, sticky="ew")
        prev_inner.rowconfigure(0, weight=1)
        prev_inner.columnconfigure(0, weight=1)

        self._ctx_menu = tk.Menu(self, tearoff=0)
        self._ctx_menu.add_command(
            label=self._("ctx_extract"), command=self._extract_selected
        )
        if not simple:
            self._ctx_menu.add_command(
                label=self._("ctx_compare"), command=self._compare_selected
            )
        self._ctx_menu.add_command(
            label=self._("ctx_open"), command=self._open_selected_folder
        )
        self._ctx_menu.add_command(
            label=self._("ctx_copy"), command=self._copy_selected_path
        )


    def _build_menubar(self) -> None:
        menubar = tk.Menu(self)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(
            label=self._("help_manual_simple"),
            command=lambda: self._open_manual("simple"),
        )
        help_menu.add_command(
            label=self._("help_manual_full"),
            command=lambda: self._open_manual("full"),
        )
        help_menu.add_separator()
        help_menu.add_command(
            label=self._("help_open_folder"),
            command=self._open_docs_folder,
        )
        help_menu.add_command(
            label=self._("help_about"),
            command=self._show_about,
        )
        menubar.add_cascade(label=self._("menu_help"), menu=help_menu)
        self.config(menu=menubar)

    def _open_manual(self, kind: str) -> None:
        title_key = "help_manual_simple" if kind == "simple" else "help_manual_full"
        ManualViewerDialog(
            self,
            title=self._(title_key).rstrip("…").rstrip("."),
            body=read_manual(self._lang, "simple" if kind == "simple" else "full"),
            close_label=self._("close"),
        )

    def _open_docs_folder(self) -> None:
        path = resolve_manual(self._lang, "simple")
        folder: Optional[Path] = None
        if path is not None:
            folder = path.parent.parent
        else:
            for root in docs_roots():
                if root.is_dir():
                    folder = root
                    break
        if folder is None or not folder.is_dir():
            messagebox.showinfo(self._("menu_help"), self._("help_open_folder"))
            return
        try:
            open_path_in_file_manager(folder)
        except OSError as exc:
            messagebox.showerror(self._("menu_help"), str(exc))

    def _show_about(self) -> None:
        messagebox.showinfo(
            self._("about_title"),
            self._("about_body", version=format_version_build()),
        )

    def _date_entry(self, parent: tk.Misc, var: tk.StringVar) -> ttk.Frame:
        """Typed DD.MM.YYYY entry + compact calendar button."""
        from gcode_index.date_picker import open_date_picker

        frame = ttk.Frame(parent)
        ttk.Entry(frame, textvariable=var, width=11).pack(side=tk.LEFT)
        ttk.Button(
            frame,
            text="▾",
            width=2,
            command=lambda: open_date_picker(
                frame,
                var,
                lang=self._lang,
                title=self._("date_picker_title"),
            ),
        ).pack(side=tk.LEFT, padx=(2, 0))
        return frame

    # --- paths ------------------------------------------------------------------

    def _pick_backup(self) -> None:
        path = filedialog.askdirectory(title=self._("pick_backup_title"))
        if path:
            self.backup_var.set(path)
            self._update_folders_summary()
            # Keep folder section open so extract / extras can still be set.
            self._save_instance_ini()
            self._sync_folder_watch()

    def _pick_target(self) -> None:
        path = filedialog.askdirectory(title=self._("target_folder"))
        if path:
            self.target_var.set(path)
            # Prefer keeping current green/yellow list when already set (INI primary);
            # otherwise load sidecar from the new database folder.
            if not self._scan_root_specs():
                self._load_extra_roots_into_list()
            else:
                self._persist_extra_roots()
            self._refresh_preset_combo()
            self._update_folders_summary()
            # INI is primary for language/schedule; YAML only fills blank last-run.
            settings = load_ui_settings(ui_settings_path_for_target(path))
            if not self._schedule_last_run and settings.get("schedule_last_run"):
                self._schedule_last_run = settings.get("schedule_last_run") or None
            self._load_colour_catalog()
            self._save_instance_ini()
            self._persist_ui_settings(path)
            self._sync_folder_watch()

    def _pick_extract(self) -> None:
        path = filedialog.askdirectory(title=self._("extract_folder"))
        if path:
            self.extract_var.set(path)
            self._update_folders_summary()
            self._save_instance_ini()

    def _pick_existing_db(self) -> None:
        path = filedialog.askopenfilename(
            title=self._("open_db"),
            filetypes=[
                (self._("filetype_sqlite"), "*.sqlite *.db"),
                (self._("filetype_all"), "*.*"),
            ],
        )
        if not path:
            return
        db = Path(path)
        self.target_var.set(str(db.parent))
        self._load_extra_roots_into_list()
        self._load_colour_catalog()
        self.status_var.set(self._("status_using_db", path=db))
        self._refresh_filter_choices()
        self._clear_filters()
        self._update_folders_summary()
        # Stay expanded on indexer so extract/backup remain editable; floor
        # clients collapse via Gotowe when ready.
        if not self._is_simple():
            self._set_folders_expanded(True, persist=False)
        self._save_instance_ini()

    def _scan_root_specs(self) -> list[ScanRootSpec]:
        if hasattr(self, "extra_list"):
            specs: list[ScanRootSpec] = []
            for i in range(self.extra_list.size()):
                parsed = parse_root_label(self.extra_list.get(i))
                if parsed is not None:
                    specs.append(parsed)
            self._hidden_root_specs = list(specs)
            return specs
        return list(self._hidden_root_specs)

    def _fill_extra_list(self, specs: list[ScanRootSpec]) -> None:
        self._hidden_root_specs = list(specs)
        if not hasattr(self, "extra_list"):
            return
        self.extra_list.delete(0, tk.END)
        for spec in specs:
            self.extra_list.insert(
                tk.END,
                format_root_label(
                    spec,
                    green_tag=self._("tag_green"),
                    yellow_tag=self._("tag_yellow"),
                ),
            )

    def _load_extra_roots_into_list(self) -> None:
        target = self.target_var.get().strip()
        specs: list[ScanRootSpec] = []
        if target:
            specs = list(load_scan_roots(extra_roots_path_for_target(target)))
        self._fill_extra_list(specs)

    def _persist_extra_roots(self) -> None:
        target = self.target_var.get().strip()
        specs = self._scan_root_specs()
        self._hidden_root_specs = list(specs)
        if target:
            Path(target).mkdir(parents=True, exist_ok=True)
            save_scan_roots(extra_roots_path_for_target(target), specs)
        self._save_instance_ini()

    def _add_scan_root(self, provenance: str) -> None:
        if not hasattr(self, "extra_list"):
            self._expand_folders()
        if not hasattr(self, "extra_list"):
            return
        title = (
            self._("add_green_folder")
            if provenance == PROVENANCE_BACKUP
            else self._("add_yellow_folder")
        )
        path = filedialog.askdirectory(title=title)
        if not path:
            return
        existing = {s.path.casefold() for s in self._scan_root_specs()}
        backup = self.backup_var.get().strip()
        try:
            resolved = str(Path(path).resolve())
        except OSError:
            resolved = path
        if backup:
            try:
                if str(Path(backup).resolve()) == resolved:
                    messagebox.showinfo(
                        self._("extra_folders"),
                        self._("extra_already_backup"),
                    )
                    return
            except OSError:
                pass
        if resolved.casefold() in existing or path.casefold() in existing:
            messagebox.showinfo(
                self._("extra_folders"), self._("extra_already_listed")
            )
            return
        nest_against: list[str] = []
        if backup:
            nest_against.append(backup)
        nest_against.extend(s.path for s in self._scan_root_specs())
        if any(roots_nest(resolved, other) for other in nest_against):
            messagebox.showinfo(
                self._("extra_folders"),
                self._("nested_root_overrides"),
            )
        specs = self._scan_root_specs()
        specs.append(ScanRootSpec(path=resolved, provenance=provenance))
        self._fill_extra_list(specs)
        self._persist_extra_roots()
        self._sync_folder_watch()

    def _add_extra_root(self) -> None:
        self._add_scan_root(PROVENANCE_EXTRA)

    def _remove_extra_roots(self) -> None:
        if not hasattr(self, "extra_list"):
            return
        sel = list(self.extra_list.curselection())
        if not sel:
            return
        for i in reversed(sel):
            self.extra_list.delete(i)
        self._persist_extra_roots()
        self._sync_folder_watch()

    def _schedule_unit_labels(self) -> list[str]:
        return [
            self._("schedule_off"),
            self._("schedule_unit_seconds"),
            self._("schedule_unit_minutes"),
            self._("schedule_unit_hours"),
            self._("schedule_unit_days"),
        ]

    def _unit_code_from_label(self, label: str) -> Optional[str]:
        raw = (label or "").strip()
        mapping = {
            self._("schedule_off"): None,
            self._("schedule_unit_seconds"): UNIT_SECONDS,
            self._("schedule_unit_minutes"): UNIT_MINUTES,
            self._("schedule_unit_hours"): UNIT_HOURS,
            self._("schedule_unit_days"): UNIT_DAYS,
        }
        if raw in mapping:
            return mapping[raw]
        # English/raw fallbacks
        low = raw.casefold()
        if low in ("off", "wyłączony", "wylaczony"):
            return None
        if low.startswith("sec") or low.startswith("sek"):
            return UNIT_SECONDS
        if low.startswith("min"):
            return UNIT_MINUTES
        if low.startswith("hour") or low.startswith("godz"):
            return UNIT_HOURS
        if low.startswith("day") or low.startswith("dni") or low.startswith("dzie"):
            return UNIT_DAYS
        return UNIT_MINUTES

    def _unit_label_from_code(self, unit: Optional[str]) -> str:
        if unit is None or unit == SCHEDULE_OFF:
            return self._("schedule_off")
        return {
            UNIT_SECONDS: self._("schedule_unit_seconds"),
            UNIT_MINUTES: self._("schedule_unit_minutes"),
            UNIT_HOURS: self._("schedule_unit_hours"),
            UNIT_DAYS: self._("schedule_unit_days"),
        }.get(unit, self._("schedule_off"))

    def _sync_schedule_widgets(self) -> None:
        parsed = parse_schedule(self._schedule)
        if parsed is None:
            self.schedule_amount_var.set("1")
            self.schedule_unit_var.set(self._("schedule_off"))
            self.schedule_var.set(SCHEDULE_OFF)
            return
        amount, unit = parsed
        self.schedule_amount_var.set(str(amount))
        self.schedule_unit_var.set(self._unit_label_from_code(unit))
        self.schedule_var.set(self._schedule)

    def _collect_schedule_from_widgets(self) -> str:
        unit = self._unit_code_from_label(self.schedule_unit_var.get())
        if unit is None:
            return SCHEDULE_OFF
        raw_amount = self.schedule_amount_var.get().strip()
        try:
            amount = int(float(raw_amount.replace(",", ".")))
        except ValueError:
            amount = 1
        return format_schedule(amount, unit)

    def _on_schedule_amount_typed(self, *_args) -> None:
        """Debounce amount edits so the countdown recalculates while typing."""
        if self._schedule_amount_debounce_id is not None:
            try:
                self.after_cancel(self._schedule_amount_debounce_id)
            except tk.TclError:
                pass
        self._schedule_amount_debounce_id = self.after(
            400, self._on_schedule_widgets_changed
        )

    def _on_schedule_widgets_changed(self, *_args) -> None:
        if self._schedule_amount_debounce_id is not None:
            try:
                self.after_cancel(self._schedule_amount_debounce_id)
            except tk.TclError:
                pass
            self._schedule_amount_debounce_id = None
        new_code = self._collect_schedule_from_widgets()
        old_code = self._schedule
        # Amount/unit change: restart the interval from *now* so next-run
        # updates immediately instead of staying anchored to an old last_run.
        if new_code != old_code and new_code != SCHEDULE_OFF:
            from datetime import datetime, timezone

            self._schedule_last_run = format_iso_datetime(
                datetime.now(timezone.utc)
            )
        self._set_schedule(new_code)

    def _set_schedule(self, schedule: str, *, persist: bool = True) -> None:
        code = normalize_schedule(schedule)
        self._schedule = code
        self._sync_schedule_widgets()
        if persist:
            self._persist_ui_settings()
            self._save_instance_ini()
        self._update_schedule_status()
        self._arm_schedule_timer()

    def _update_schedule_status(self) -> None:
        if not hasattr(self, "schedule_status_var"):
            return
        if self._schedule == SCHEDULE_OFF:
            self.schedule_status_var.set(self._("schedule_idle"))
            return
        if self._scan_busy:
            self.schedule_status_var.set(self._("schedule_running"))
            return
        rem = seconds_until_next(self._schedule, self._schedule_last_run)
        if rem is None:
            self.schedule_status_var.set(self._("schedule_idle"))
            return
        if rem <= 0.5:
            self.schedule_status_var.set(self._("schedule_due_now"))
            return
        self.schedule_status_var.set(
            self._("schedule_countdown", countdown=format_countdown(rem))
        )

    def _arm_schedule_timer(self) -> None:
        if self._schedule_after_id is not None:
            try:
                self.after_cancel(self._schedule_after_id)
            except tk.TclError:
                pass
            self._schedule_after_id = None
        # Floor client (can_index=no) — no auto-index timer.
        if self._is_simple():
            return
        if self._schedule != SCHEDULE_OFF:
            self._schedule_after_id = self.after(
                schedule_poll_ms(self._schedule), self._schedule_tick
            )

    def _schedule_tick(self) -> None:
        self._schedule_after_id = None
        try:
            self._update_schedule_status()
            self._maybe_run_scheduled_scan()
        finally:
            self._arm_schedule_timer()
            # Refresh again after possible scan start so "indexing now" shows.
            self._update_schedule_status()

    def _maybe_run_scheduled_scan(self) -> None:
        if self._is_simple():
            return
        if self._schedule == SCHEDULE_OFF or self._scan_busy:
            return
        if not self._folders_ready():
            return
        if not is_schedule_due(self._schedule, self._schedule_last_run):
            return
        self.status_var.set(self._("schedule_running"))
        self.schedule_status_var.set(self._("schedule_running"))
        self._start_scan(auto=True)

    def _mark_schedule_ran(self) -> None:
        from datetime import datetime, timezone

        self._schedule_last_run = format_iso_datetime(datetime.now(timezone.utc))
        self._persist_ui_settings()
        self._save_instance_ini()
        self._update_schedule_status()

    def _watch_mode_label(self, mode: str) -> str:
        code = normalize_watch_mode(mode)
        if code == WATCH_MODE_POLL:
            return self._("watch_mode_poll")
        return self._("watch_mode_hybrid")

    def _watch_mode_from_label(self, label: str) -> str:
        raw = (label or "").strip()
        if raw == self._("watch_mode_poll"):
            return WATCH_MODE_POLL
        if raw == self._("watch_mode_hybrid"):
            return WATCH_MODE_HYBRID
        return normalize_watch_mode(raw)

    def _build_watch_mode_segment(self, parent) -> None:
        """Small Auto | Poll segmented control (indexer watch method)."""
        wrap = ttk.Frame(parent)
        wrap.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(wrap, text=self._("watch_mode"), style="Muted.TLabel").pack(
            side=tk.LEFT, padx=(0, 4)
        )
        self.watch_mode_var.set(self._watch_mode_label(self._watch_mode))
        strip = tk.Frame(wrap, bg="#c5d0cb", padx=1, pady=1)
        strip.pack(side=tk.LEFT)
        self._watch_mode_hybrid_btn = tk.Button(
            strip,
            text=self._("watch_mode_hybrid"),
            command=lambda: self._set_watch_mode(WATCH_MODE_HYBRID),
            relief=tk.RAISED,
            borderwidth=1,
            padx=8,
            pady=1,
            cursor="hand2",
            font=self._ui_font(size=9, bold=False),
        )
        self._watch_mode_hybrid_btn.pack(side=tk.LEFT)
        self._watch_mode_poll_btn = tk.Button(
            strip,
            text=self._("watch_mode_poll"),
            command=lambda: self._set_watch_mode(WATCH_MODE_POLL),
            relief=tk.RAISED,
            borderwidth=1,
            padx=8,
            pady=1,
            cursor="hand2",
            font=self._ui_font(size=9, bold=False),
        )
        self._watch_mode_poll_btn.pack(side=tk.LEFT)
        self._refresh_watch_mode_styles()

    def _refresh_watch_mode_styles(self) -> None:
        mode = normalize_watch_mode(self._watch_mode)
        pairs = (
            (getattr(self, "_watch_mode_hybrid_btn", None), mode == WATCH_MODE_HYBRID),
            (getattr(self, "_watch_mode_poll_btn", None), mode == WATCH_MODE_POLL),
        )
        for btn, selected in pairs:
            if btn is None:
                continue
            try:
                if not btn.winfo_exists():
                    continue
            except tk.TclError:
                continue
            if selected:
                btn.configure(
                    bg=UI_ACCENT,
                    fg=UI_ACCENT_TEXT,
                    activebackground=UI_ACCENT_HOVER,
                    activeforeground=UI_ACCENT_TEXT,
                    relief=tk.SUNKEN,
                    font=self._ui_font(size=9, bold=True),
                )
            else:
                btn.configure(
                    bg="#eef2f0",
                    fg=UI_KEY_FG,
                    activebackground="#dde5e1",
                    activeforeground=UI_KEY_FG,
                    relief=tk.RAISED,
                    font=self._ui_font(size=9, bold=False),
                )

    def _set_watch_mode(self, mode: str, *, persist: bool = True) -> None:
        code = normalize_watch_mode(mode)
        if code == self._watch_mode:
            self._refresh_watch_mode_styles()
            return
        self._watch_mode = code
        self.watch_mode_var.set(self._watch_mode_label(code))
        self._refresh_watch_mode_styles()
        if persist:
            self._save_instance_ini()
        # Restart watcher so event vs poll roots rebind
        if self._watch_enabled and not self._is_simple():
            self._stop_folder_watch(release=False)
            self._sync_folder_watch()
        else:
            self._refresh_watch_strip()

    def _watch_roots(self) -> list[Path]:
        roots: list[Path] = []
        backup = self.backup_var.get().strip()
        if backup:
            roots.append(Path(backup))
        for spec in self._scan_root_specs():
            if spec.path:
                roots.append(Path(spec.path))
        return roots

    def _update_watch_status(self, locked_by: Optional[str] = None) -> None:
        if not hasattr(self, "watch_status_var"):
            return
        if locked_by:
            self.watch_status_var.set(self._("watch_locked", holder=locked_by))
        elif self._folder_watcher is not None and self._folder_watcher.running:
            self.watch_status_var.set(self._("watch_on"))
        else:
            self.watch_status_var.set(self._("watch_idle"))
        self._refresh_watch_strip(locked_by=locked_by)

    def _on_watch_poll_thread(self) -> None:
        try:
            self.after(0, self._refresh_watch_strip)
        except tk.TclError:
            pass

    def _format_watch_when(self, dt) -> str:
        if dt is None:
            return self._("watch_strip_never")
        try:
            return dt.astimezone().strftime("%H:%M:%S")
        except Exception:  # noqa: BLE001
            return self._("watch_strip_never")

    def _refresh_watch_strip(self, locked_by: Optional[str] = None) -> None:
        if not hasattr(self, "watch_strip_var"):
            return
        if self._is_simple():
            self.watch_strip_var.set("")
            return
        fw = self._folder_watcher
        if fw is None or not fw.running:
            self.watch_strip_var.set(self._("watch_strip_idle"))
            return
        bits = [
            self._("watch_strip_poll", when=self._format_watch_when(fw.last_poll_at)),
            self._("watch_strip_files", n=fw.stamp_count),
            self._(
                "watch_strip_scan",
                when=self._format_watch_when(self._last_watch_scan_at),
            ),
        ]
        # Per-root method (local=events, Z:/UNC=poll) when hybrid is active
        methods = fw.root_methods()
        if methods:
            parts: list[str] = []
            for label, method in methods:
                if method == METHOD_EVENTS:
                    parts.append(
                        self._("watch_strip_root_events", root=label)
                    )
                else:
                    parts.append(self._("watch_strip_root_poll", root=label))
            if parts:
                bits.append(" · ".join(parts))
        target = self.target_var.get().strip()
        if locked_by:
            bits.append(self._("watch_strip_lock", holder=locked_by))
        elif target:
            if we_hold_lock(target):
                bits.append(self._("watch_strip_lock_us"))
            else:
                info = read_lock(target)
                if info is None:
                    bits.append(self._("watch_strip_lock_none"))
                else:
                    bits.append(self._("watch_strip_lock", holder=info.summary()))
        self.watch_strip_var.set(" · ".join(bits))

    def _autostart_via_code(self) -> str:
        raw = (self.autostart_via_var.get() or "").strip()
        if raw == self._("autostart_via_task"):
            return VIA_TASK
        if raw.casefold() in ("task", "scheduler", "harmonogram zadań", "harmonogram zadan"):
            return VIA_TASK
        return VIA_STARTUP

    def _autostart_via_label(self, code: str) -> str:
        if normalize_autostart_via(code) == VIA_TASK:
            return self._("autostart_via_task")
        return self._("autostart_via_startup")

    def _on_desktop_pref_changed(self, *_args) -> None:
        self._save_instance_ini()

    def _on_autostart_via_selected(self, *_args) -> None:
        self._save_instance_ini()
        if self.autostart_var.get():
            self._apply_autostart(enabled=True)

    def _on_autostart_toggled(self) -> None:
        enabled = bool(self.autostart_var.get())
        self._apply_autostart(enabled=enabled)
        self._save_instance_ini()

    def _apply_autostart(self, *, enabled: bool) -> None:
        ok, detail = sync_autostart(
            enabled=enabled, via=self._autostart_via_code()
        )
        if ok:
            self.status_var.set(
                self._("autostart_ok") if enabled else self._("autostart_removed")
            )
        else:
            self.autostart_var.set(False)
            messagebox.showerror(
                self._("autostart"),
                self._("autostart_fail", error=detail),
            )

    def _on_watch_toggled(self) -> None:
        self._watch_enabled = bool(self.watch_var.get()) and not self._is_simple()
        self._save_instance_ini()
        self._sync_folder_watch()

    def _stop_folder_watch(self, *, release: bool = False) -> None:
        if self._folder_watcher is not None:
            try:
                self._folder_watcher.stop()
            except Exception:  # noqa: BLE001
                log.exception("stop folder watcher failed")
            self._folder_watcher = None
        if release:
            target = self.target_var.get().strip()
            if target and we_hold_lock(target):
                release_lock(target)
        self._update_watch_status()

    def _sync_folder_watch(self, *, initial: bool = False) -> None:
        """Start/stop watcher for indexer (can_index=yes) based on checkbox + folders + lock."""
        if self._is_simple():
            self._watch_enabled = False
            self._stop_folder_watch(release=True)
            return
        self._watch_enabled = bool(self.watch_var.get())
        if not self._watch_enabled:
            self._stop_folder_watch(release=True)
            return
        backup = self.backup_var.get().strip()
        target = self.target_var.get().strip()
        if not backup or not target or not Path(backup).is_dir():
            if not initial and self.watch_var.get():
                self.watch_var.set(False)
                self._watch_enabled = False
                messagebox.showinfo(self._("watch_folders"), self._("watch_need_folders"))
            self._stop_folder_watch(release=True)
            return
        Path(target).mkdir(parents=True, exist_ok=True)
        ok, holder = try_acquire_lock(target, purpose="watch")
        if not ok:
            self.watch_var.set(False)
            self._watch_enabled = False
            self._stop_folder_watch(release=False)
            who = holder.summary() if holder is not None else "?"
            self._update_watch_status(locked_by=who)
            if not initial:
                messagebox.showwarning(
                    self._("watch_folders"),
                    self._("watch_locked", holder=who),
                )
            return
        roots = self._watch_roots()
        mode = normalize_watch_mode(self._watch_mode)
        if self._folder_watcher is None:
            self._folder_watcher = FolderWatcher(
                on_change=self._on_watch_change_thread,
                poll_s=5.0,
                debounce_s=3.0,
                on_poll=self._on_watch_poll_thread,
                mode=mode,
            )
            self._folder_watcher.set_roots(roots)
            n = self._folder_watcher.seed()
            self._folder_watcher.start()
            log.info(
                "folder watch started mode=%s (%s files baseline)", mode, n
            )
        else:
            prev_mode = self._folder_watcher.mode
            prev_methods = self._folder_watcher.root_methods()
            self._folder_watcher.set_mode(mode)
            self._folder_watcher.set_roots(roots)
            new_methods = self._folder_watcher.root_methods()
            rebind = prev_mode != mode or prev_methods != new_methods
            if self._folder_watcher.running and rebind:
                self._folder_watcher.stop()
                n = self._folder_watcher.seed()
                self._folder_watcher.start()
                log.info(
                    "folder watch rebound mode=%s (%s files)", mode, n
                )
            elif not self._folder_watcher.running:
                n = self._folder_watcher.seed()
                self._folder_watcher.start()
                log.info(
                    "folder watch started mode=%s (%s files baseline)", mode, n
                )
            else:
                self._folder_watcher.seed()
        self._update_watch_status()
        self._save_instance_ini()

    def _on_watch_change_thread(self) -> None:
        """Called from watcher thread — marshal onto Tk."""
        try:
            self.after(0, self._on_watch_change)
        except tk.TclError:
            pass

    def _on_watch_change(self) -> None:
        if self._is_simple() or not self._watch_enabled:
            return
        if self._scan_busy:
            self._watch_rescan_pending = True
            return
        from datetime import datetime, timezone

        self._last_watch_scan_at = datetime.now(timezone.utc)
        self._refresh_watch_strip()
        self.status_var.set(self._("watch_trigger"))
        self._start_scan(auto=True)

    def _db_path(self) -> Optional[Path]:
        target = self.target_var.get().strip()
        if not target:
            return None
        return Path(target) / DEFAULT_DB_NAME

    # --- folder map -------------------------------------------------------------

    def _folder_map_path(self) -> Optional[Path]:
        target = self.target_var.get().strip()
        if not target:
            return None
        return map_path_for_target(target)

    def _local_aliases_path(self) -> Optional[Path]:
        target = self.target_var.get().strip()
        if not target:
            return None
        return local_aliases_path_for_target(target)

    def _load_alias_map(self) -> AliasMap:
        local = self._local_aliases_path()
        return AliasMap.load_merged(default_aliases_path(), local)

    def _load_folder_map(self) -> FolderMachineMap:
        path = self._folder_map_path()
        if path is None or not path.is_file():
            return FolderMachineMap()
        try:
            return FolderMachineMap.load(path)
        except Exception:  # noqa: BLE001
            log.exception("failed to load folder map %s", path)
            return FolderMachineMap()

    def _open_folder_map(self) -> None:
        backup = self.backup_var.get().strip()
        target = self.target_var.get().strip()
        if not backup or not Path(backup).is_dir():
            messagebox.showerror(self._("backup_folder"), self._("err_backup_required"))
            return
        if not target:
            messagebox.showerror(
                self._("target_folder"),
                self._("err_target_for_map"),
            )
            return
        Path(target).mkdir(parents=True, exist_ok=True)
        try:
            aliases = self._load_alias_map()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(self._("aliases_dialog_title"), str(exc))
            return
        folders = discover_machine_folders(backup)
        if not folders:
            messagebox.showinfo(
                self._("map_folders"),
                self._("map_no_folders", path=backup),
            )
            return
        existing = self._load_folder_map()
        part = partition_folders(folders, aliases, existing)
        if not part.needs_manual:
            auto_n = part.auto_count
            prev_n = len(part.previously_mapped)
            messagebox.showinfo(
                self._("map_folders"),
                self._("map_all_matched")
                + f"\n\n{self._('map_summary', auto=auto_n, prev=prev_n, manual=0)}",
            )
            return
        suggested = suggest_assignments(folders, aliases, existing)
        suggested.backup_root = str(Path(backup).resolve())
        dlg = FolderMapDialog(
            self,
            partition=part,
            suggested=suggested,
            existing_map=existing,
            aliases=aliases,
            machine_choices=[
                display_for_machine(UNKNOWN_ID, UNKNOWN_LABEL),
                *aliases.known_machine_displays(),
            ],
            save_path=map_path_for_target(target),
            local_aliases_path=local_aliases_path_for_target(target),
        )
        self.wait_window(dlg)
        if dlg.saved:
            bits = [self._("status_aliases_saved", filename=map_path_for_target(target).name)]
            if dlg.aliases_saved:
                bits.append(
                    self._("status_aliases_saved", filename=LOCAL_ALIASES_FILENAME)
                )
            self.status_var.set("; ".join(bits))

    def _open_folder_tree_map(self) -> None:
        """Open lazy path-tree mapper (indexer). Show errors instead of failing silently."""
        try:
            self._open_folder_tree_map_impl()
        except Exception as exc:  # noqa: BLE001
            log.exception("open folder tree map failed")
            messagebox.showerror(self._("map_tree"), str(exc))

    def _open_folder_tree_map_impl(self) -> None:
        backup = self.backup_var.get().strip()
        target = self.target_var.get().strip()
        if not target:
            messagebox.showerror(
                self._("target_folder"),
                self._("err_target_for_tree_map", filename=TREE_MAP_FILENAME),
            )
            return
        roots, skipped = collect_tree_map_roots(backup, self._scan_root_specs())
        if not roots:
            detail = self._("err_tree_map_need_roots")
            if skipped:
                detail = (
                    detail
                    + "\n\n"
                    + self._("err_tree_map_roots_missing", paths="\n".join(skipped))
                )
            messagebox.showerror(self._("map_tree"), detail)
            return
        Path(target).mkdir(parents=True, exist_ok=True)
        save_path = tree_map_path_for_target(target)
        tree_map = load_folder_tree_map(save_path)
        try:
            aliases = self._load_alias_map()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(self._("aliases_dialog_title"), str(exc))
            return
        catalog = load_colour_catalog(
            folder_colour_aliases_path_for_target(target)
        )
        machine_choices = [
            display_for_machine(UNKNOWN_ID, UNKNOWN_LABEL),
            *aliases.known_machine_displays(),
            "",  # leave machine unchanged
        ]
        dlg = FolderTreeMapDialog(
            self,
            roots=roots,
            tree_map=tree_map,
            catalog=catalog,
            machine_choices=machine_choices,
            save_path=save_path,
            aliases=aliases,
            local_aliases_path=local_aliases_path_for_target(target),
            colour_save_path=folder_colour_aliases_path_for_target(target),
        )
        self.wait_window(dlg)
        if dlg.saved:
            self.status_var.set(
                self._("status_tree_map_saved", filename=TREE_MAP_FILENAME)
            )
        if getattr(dlg, "aliases_changed", False):
            note = self._("tree_alias_reindex_note")
            self.status_var.set(
                (self.status_var.get() + " — " if self.status_var.get() else "") + note
            )

    def _open_alias_editor(self) -> None:
        target = self.target_var.get().strip()
        if not target:
            messagebox.showerror(
                self._("target_folder"),
                self._("err_target_for_aliases", filename=LOCAL_ALIASES_FILENAME),
            )
            return
        Path(target).mkdir(parents=True, exist_ok=True)
        try:
            aliases = self._load_alias_map()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(self._("aliases_dialog_title"), str(exc))
            return
        dlg = AliasEditorDialog(
            self,
            aliases=aliases,
            save_path=local_aliases_path_for_target(target),
        )
        self.wait_window(dlg)
        if dlg.saved:
            self.status_var.set(
                self._("status_aliases_saved", filename=LOCAL_ALIASES_FILENAME)
            )
            self._refresh_filter_choices()

    def _open_folder_colour_editor(self) -> None:
        target = self.target_var.get().strip()
        if not target:
            messagebox.showerror(
                self._("folder_colours"),
                self._(
                    "err_target_for_folder_colours",
                    filename=FOLDER_COLOUR_ALIASES_FILENAME,
                ),
            )
            return
        Path(target).mkdir(parents=True, exist_ok=True)
        path = folder_colour_aliases_path_for_target(target)
        dlg = FolderColourAliasDialog(self, save_path=path)
        self.wait_window(dlg)
        if dlg.saved:
            self._load_colour_catalog()
            self.status_var.set(
                self._(
                    "status_folder_colours_saved",
                    filename=FOLDER_COLOUR_ALIASES_FILENAME,
                )
            )

    # --- scan -------------------------------------------------------------------

    def _start_scan(self, auto: bool = False) -> None:
        if self._scan_busy:
            return
        # Floor client (can_index=no) — indexing lives on the indexer PC.
        if self._is_simple():
            if not auto:
                messagebox.showinfo(
                    self._("run_scan"),
                    self._("hint_simple"),
                )
            return
        backup = self.backup_var.get().strip()
        target = self.target_var.get().strip()
        if not backup or not Path(backup).is_dir():
            if not auto:
                messagebox.showerror(self._("backup_folder"), self._("err_backup_invalid"))
            return
        if not target:
            if not auto:
                messagebox.showerror(self._("target_folder"), self._("err_target_for_db"))
            return
        Path(target).mkdir(parents=True, exist_ok=True)
        self._persist_ui_settings(target)
        # Offer mapper only on indexer (manual) when unmatched folders remain
        if not auto and not self._is_simple():
            try:
                aliases = self._load_alias_map()
                folders = discover_machine_folders(backup)
                part = partition_folders(folders, aliases, self._load_folder_map())
            except Exception:  # noqa: BLE001
                log.exception("folder partition before scan failed")
                part = None
            if part is not None and part.needs_manual:
                prompt = self._(
                    "map_needs_manual_prompt", n=part.manual_count
                )
                if messagebox.askyesno(self._("map_folders"), prompt):
                    self._open_folder_map()
        self._scan_busy = True
        self._set_primary_button_enabled(self.scan_btn, False)
        self.progress_var.set(0.0)
        self.progress_label_var.set(self._("scan_starting"))
        self.status_var.set(
            self._("schedule_running") if auto else self._("scan_scanning")
        )
        self._update_schedule_status()
        self._show_progress(True)
        self._maybe_auto_collapse_folders()
        if self._is_simple() or auto:
            write_excel = False
            incremental = True
        else:
            write_excel = bool(self.excel_var.get())
            incremental = bool(self.incremental_var.get())
        self._persist_extra_roots()
        root_specs = normalize_scan_roots(
            self._scan_root_specs(),
            backup_root=backup,
        )
        threading.Thread(
            target=self._scan_worker,
            args=(
                Path(backup),
                Path(target),
                write_excel,
                root_specs,
                incremental,
                auto,
            ),
            daemon=True,
        ).start()

    def _on_scan_progress(self, info: dict) -> None:
        """Marshal scanner progress onto the Tk thread."""
        self.after(0, lambda: self._apply_scan_progress(info))

    def _apply_scan_progress(self, info: dict) -> None:
        phase = info.get("phase") or ""
        key = info.get("message_key")
        if key:
            kwargs = dict(info.get("message_kwargs") or {})
            message = self._(str(key), **kwargs)
        else:
            message = info.get("message") or ""
        current = int(info.get("current") or 0)
        total = int(info.get("total") or 0)
        eta = format_eta(info.get("eta_s"))

        if phase == "counting" or total <= 0:
            self.progress.configure(mode="indeterminate")
            try:
                self.progress.start(12)
            except tk.TclError:
                pass
            self.progress_label_var.set(message or self._("scan_counting_short"))
            self.status_var.set(message or self._("scan_counting"))
            return

        try:
            self.progress.stop()
        except tk.TclError:
            pass
        self.progress.configure(mode="determinate", maximum=100.0)
        pct = min(100.0, 100.0 * current / max(total, 1))
        self.progress_var.set(pct)
        label = f"{current} / {total}"
        if eta:
            label = f"{label}  {eta}"
        self.progress_label_var.set(label)
        self.status_var.set(message or label)

    def _scan_worker(
        self,
        backup: Path,
        target: Path,
        write_excel: bool,
        root_specs: list[tuple[Path, str]],
        incremental: bool,
        auto: bool = False,
    ) -> None:
        try:
            from datetime import datetime, timezone

            scan_started = datetime.now(timezone.utc)
            aliases_path = default_aliases_path()
            local_path = local_aliases_path_for_target(target)
            alias_map = AliasMap.load_merged(aliases_path, local_path)
            folder_map = FolderMachineMap.load(map_path_for_target(target))
            fmap = folder_map if folder_map.assignments else None
            colour_map = FolderColourAliasMap.load(
                folder_colour_aliases_path_for_target(target)
            )
            tree_map = load_folder_tree_map(tree_map_path_for_target(target))
            self._colour_catalog = load_colour_catalog(
                folder_colour_aliases_path_for_target(target)
            )
            self._configure_colour_tags()
            db_path = target / DEFAULT_DB_NAME
            cache = None
            n_cached = 0
            prior_paths: set[str] = set()
            if incremental and db_path.is_file():
                try:
                    prior = open_db(db_path)
                    try:
                        cache = load_scan_cache(prior)
                        prior_paths = prior_paths_from_cache(cache)
                    finally:
                        prior.close()
                except Exception:  # noqa: BLE001
                    log.exception("load scan cache failed; falling back to full scan")
                    cache = None
                    prior_paths = set()
            if root_specs:
                result = scan_with_extra_roots(
                    backup,
                    alias_map,
                    root_specs=root_specs,
                    progress=self._on_scan_progress,
                    folder_map=fmap,
                    cache=cache,
                    colour_map=colour_map,
                    tree_map=tree_map,
                )
            else:
                result = scan_backup_tree(
                    backup,
                    alias_map,
                    progress=self._on_scan_progress,
                    folder_map=fmap,
                    provenance=PROVENANCE_BACKUP,
                    cache=cache,
                    colour_map=colour_map,
                    tree_map=tree_map,
                )
            n_cached = sum(1 for fs in result.files_seen if fs.status == "cached")
            if db_path.is_file():
                db_path.unlink()
            conn = open_db(db_path)
            run_id = write_scan_result(
                conn,
                backup_root=str(backup.resolve()),
                aliases_path=str(aliases_path),
                result=result,
            )
            type_counts = Counter(i.source_type for i in result.instances)
            type_note = ", ".join(f"{k}={v}" for k, v in sorted(type_counts.items()))
            unknown_prog = sum(1 for i in result.instances if i.machine_id == "unknown")
            n_green = sum(1 for i in result.instances if i.provenance == PROVENANCE_BACKUP)
            n_yellow = sum(1 for i in result.instances if i.provenance == PROVENANCE_EXTRA)
            n_red = sum(
                1 for i in result.instances if ROLE_WIP in roles_from_db(i.role)
            )
            other_flags = Counter(
                tag
                for i in result.instances
                for tag in roles_from_db(i.role)
                if tag != ROLE_WIP
            )
            conn.close()
            scan_finished = datetime.now(timezone.utc)
            try:
                entry = build_history_entry(
                    run_id=run_id,
                    backup_root=str(backup.resolve()),
                    result=result,
                    started_at=scan_started,
                    finished_at=scan_finished,
                    prior_paths=prior_paths,
                    incremental=cache is not None,
                    auto=auto,
                )
                append_scan_history(target, entry)
            except Exception:  # noqa: BLE001
                log.exception("append scan history failed")
            excel_note = ""
            if write_excel:
                xlsx = target / "gcode_index.xlsx"
                export_excel(xlsx, result.instances)
                excel_note = self._("scan_note_excel", name=xlsx.name)
            unk_note = (
                self._("scan_note_unknown_prog", n=unknown_prog)
                if unknown_prog
                else self._("scan_note_unknown_prog_zero")
            )
            local_note = (
                self._("scan_note_local_aliases", n=alias_map.local_alias_count)
                if alias_map.local_alias_count
                else ""
            )
            flag_note = self._(
                "scan_note_flags", green=n_green, yellow=n_yellow, red=n_red
            )
            if other_flags:
                flag_note += "; " + ", ".join(
                    f"{k}={v}" for k, v in sorted(other_flags.items())
                )
            cache_note = (
                self._("scan_note_cached", n=n_cached) if n_cached else ""
            )
            mode_note = (
                self._("scan_note_incremental")
                if cache is not None
                else self._("scan_note_full")
            )
            auto_note = self._("scan_note_auto") if auto else ""
            extra = (
                f"{unk_note}{local_note}{flag_note}"
                f"{cache_note}{mode_note}{auto_note}"
            )
            msg = self._(
                "scan_done_status",
                n=len(result.instances),
                types=type_note,
                unknowns=len(result.unknowns),
                extra=extra,
                db=db_path.name,
                run=run_id[:8],
                excel=excel_note,
            )
            report = scan_report_from_result(result, run_id=run_id)
            self.after(
                0, lambda: self._scan_done(True, msg, report=report, auto=auto)
            )
        except Exception as exc:  # noqa: BLE001 — show in UI
            log.exception("scan failed")
            self.after(0, lambda: self._scan_done(False, str(exc), auto=auto))

    def _scan_done(
        self,
        ok: bool,
        message: str,
        *,
        report: Optional[ScanReport] = None,
        auto: bool = False,
    ) -> None:
        self._scan_busy = False
        self._set_primary_button_enabled(self.scan_btn, True)
        try:
            self.progress.stop()
        except tk.TclError:
            pass
        self.progress.configure(mode="determinate")
        if ok:
            self.progress_var.set(100.0)
            self.progress_label_var.set(self._("scan_done"))
            self._mark_schedule_ran()
            if auto:
                from datetime import datetime, timezone

                self._last_watch_scan_at = datetime.now(timezone.utc)
                self._refresh_watch_strip()
            # Re-seed watcher baseline after a successful index so we don't
            # immediately re-trigger on the same tree.
            if self._folder_watcher is not None and self._folder_watcher.running:
                try:
                    self._folder_watcher.seed()
                except Exception:  # noqa: BLE001
                    log.exception("re-seed folder watcher failed")
                self._refresh_watch_strip()
        else:
            self.progress_var.set(0.0)
            self.progress_label_var.set("")
        self._update_schedule_status()
        self.status_var.set(message)
        # Hide progress bar shortly after finish to free vertical space
        self.after(1200, lambda: self._show_progress(False) if not self._scan_busy else None)
        if not ok:
            if not auto:
                messagebox.showerror(self._("scan_failed_title"), message)
            if self._watch_rescan_pending and self._watch_enabled:
                self._watch_rescan_pending = False
                self.after(1500, self._on_watch_change)
            return
        if report is not None:
            self._last_scan_report = report
        self._refresh_filter_choices()
        self._clear_filters(status_prefix=message)
        # Note DB mtime so auto-refresh doesn't immediately re-fire
        self._note_db_mtime()
        if report is not None and not self._is_simple() and not auto:
            self._show_scan_report(report)
        if self._watch_rescan_pending and self._watch_enabled:
            self._watch_rescan_pending = False
            self.after(800, self._on_watch_change)

    def _open_scan_history(self) -> None:
        if self._is_simple():
            messagebox.showinfo(
                self._("scan_history"),
                self._("scan_history_indexer_only"),
            )
            return
        target = self.target_var.get().strip()
        if not target:
            messagebox.showinfo(
                self._("scan_history"),
                self._("scan_history_empty"),
            )
            return
        entries = load_scan_history(
            history_path_for_target(target), limit=DEFAULT_HISTORY_LIMIT
        )
        ScanHistoryDialog(
            self,
            entries=entries,
            title=self._("scan_history"),
            empty_label=self._("scan_history_empty"),
            close_label=self._("close"),
            columns=(
                self._("scan_history_when"),
                self._("scan_history_duration"),
                self._("scan_history_instances"),
                self._("scan_history_added"),
                self._("scan_history_updated"),
                self._("scan_history_removed"),
                self._("scan_history_cached"),
                self._("scan_history_mode"),
            ),
        )

    def _open_scan_report(self) -> None:
        report = self._last_scan_report
        if report is None:
            db_path = self._db_path()
            if db_path is None or not db_path.is_file():
                messagebox.showinfo(
                    self._("scan_report_title"),
                    self._("scan_report_need_db"),
                )
                return
            try:
                conn = open_db(db_path)
                try:
                    report = load_scan_report(conn)
                finally:
                    conn.close()
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror(self._("scan_report_title"), str(exc))
                return
        if report is None:
            messagebox.showinfo(self._("scan_report_title"), self._("scan_report_none"))
            return
        self._last_scan_report = report
        self._show_scan_report(report)

    def _show_scan_report(self, report: ScanReport) -> None:
        ScanReportDialog(self, report=report)

    def _open_duplicates(self) -> None:
        db_path = self._db_path()
        if db_path is None or not db_path.is_file():
            messagebox.showinfo(
                self._("duplicates_title"),
                self._("duplicates_need_db"),
            )
            return
        try:
            conn = open_db(db_path)
            try:
                groups = find_duplicate_groups(conn)
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(self._("duplicates_title"), str(exc))
            return
        if not groups:
            messagebox.showinfo(
                self._("duplicates_title"),
                self._("duplicates_none"),
            )
            return
        dlg = DuplicatesDialog(self, groups=groups)
        self.wait_window(dlg)
        if dlg.selected_members:
            self.tree.delete(*self.tree.get_children())
            self._fill_tree(dlg.selected_members)
            self.status_var.set(self._("duplicates_showing", n=len(dlg.selected_members)))

    # --- filters / search -------------------------------------------------------

    def _selected_machines(self) -> list[str]:
        if not self._machine_sel:
            return []
        names = [n for n in self._machine_names if n in self._machine_sel]
        if self._machine_names and len(names) == len(self._machine_names):
            return []
        return names

    def _select_all_machines(self) -> None:
        self._machine_sel = set()
        self._update_machines_button()
        self._on_filter_changed()

    def _clear_machine_selection(self) -> None:
        self._machine_sel = set()
        self._update_machines_button()
        self._on_filter_changed()

    def _refresh_filter_choices(self) -> None:
        db_path = self._db_path()
        seed: list[str] = []
        try:
            seed = self._load_alias_map().known_machine_displays()
        except Exception:  # noqa: BLE001
            seed = []
        # Always offer unassigned bucket even when the last scan found none
        if UNKNOWN_MACHINE_DISPLAY not in seed:
            seed = [UNKNOWN_MACHINE_DISPLAY, *seed]

        vals: dict[str, list[str]] = {
            "machines": list(seed),
            "source_types": [],
            "control_families": [],
            "programmers": [],
        }
        if db_path is not None and db_path.is_file():
            try:
                conn = open_db(db_path)
                try:
                    vals = list_filter_values(conn, seed_machines=seed)
                finally:
                    conn.close()
            except Exception:  # noqa: BLE001
                pass

        prev = set(self._selected_machines())
        self._machine_names = list(vals["machines"])
        if prev:
            self._machine_sel = {n for n in prev if n in set(self._machine_names)}
        else:
            self._machine_sel = set()
        self._update_machines_button()
        if hasattr(self, "type_combo"):
            self.type_combo["values"] = [self._all_token(), *vals["source_types"]]
        if hasattr(self, "control_combo"):
            self.control_combo["values"] = [self._all_token(), *vals["control_families"]]
        if hasattr(self, "programmer_combo"):
            self.programmer_combo["values"] = [
                self._all_token(),
                *vals.get("programmers", []),
            ]
        if hasattr(self, "provenance_combo"):
            self.provenance_combo["values"] = self._status_filter_labels()
        if hasattr(self, "role_combo"):
            self.role_combo["values"] = self._role_filter_labels()
        self._refresh_preset_combo()

    def _presets_path(self) -> Optional[Path]:
        target = self.target_var.get().strip()
        if not target:
            return None
        return presets_path_for_target(target)

    def _refresh_preset_combo(self) -> None:
        if not hasattr(self, "preset_combo"):
            return
        path = self._presets_path()
        names: list[str] = []
        if path is not None:
            try:
                names = [p.name for p in load_presets(path)]
            except Exception:  # noqa: BLE001
                log.exception("load presets failed")
                names = []
        prev = self.preset_var.get().strip()
        self.preset_combo["values"] = names
        if prev and prev in names:
            self.preset_var.set(prev)
        elif names:
            # Keep empty selection until user picks / loads
            if prev not in names:
                self.preset_var.set("")
        else:
            self.preset_var.set("")

    def _current_filter_preset(self, name: str) -> FilterPreset:
        return FilterPreset(
            name=name.strip(),
            text=self.search_var.get().strip(),
            machines=self._selected_machines(),
            date_from=self.date_from_var.get().strip(),
            date_to=self.date_to_var.get().strip(),
            size_min=self.size_min_var.get().strip(),
            size_max=self.size_max_var.get().strip(),
            mtime_from=self.mtime_from_var.get().strip(),
            mtime_to=self.mtime_to_var.get().strip(),
            source_type=self.source_type_var.get().strip() or ALL,
            control=self.control_var.get().strip() or ALL,
            provenance=self.provenance_var.get().strip() or ALL,
            programmer=self.programmer_var.get().strip() or ALL,
            role=self.role_var.get().strip() or ALL,
            newest_only=bool(self.newest_only_var.get()),
        )

    def _apply_filter_preset(self, preset: FilterPreset) -> None:
        self._filter_trace_lock = True
        try:
            self.search_var.set(preset.text or "")
            self.date_from_var.set(preset.date_from or "")
            self.date_to_var.set(preset.date_to or "")
            self.size_min_var.set(getattr(preset, "size_min", "") or "")
            self.size_max_var.set(getattr(preset, "size_max", "") or "")
            self.mtime_from_var.set(getattr(preset, "mtime_from", "") or "")
            self.mtime_to_var.set(getattr(preset, "mtime_to", "") or "")
            self.source_type_var.set(preset.source_type or ALL)
            self.control_var.set(preset.control or ALL)
            self.provenance_var.set(preset.provenance or ALL)
            self.programmer_var.set(preset.programmer or ALL)
            role_raw = getattr(preset, "role", "") or ALL
            self.role_var.set(role_raw if role_raw else ALL)
            self.newest_only_var.set(bool(preset.newest_only))
            wanted = {m.strip() for m in (preset.machines or []) if m.strip()}
            self._machine_sel = {
                n for n in self._machine_names if n in wanted
            } if wanted else set()
            self._update_machines_button()
            self.preset_var.set(preset.name)
        finally:
            self._filter_trace_lock = False
        self._run_query_now(status_prefix=self._("preset_loaded", name=preset.name))

    def _save_current_preset(self) -> None:
        path = self._presets_path()
        if path is None:
            messagebox.showerror(
                self._("presets_title"),
                self._("preset_need_target"),
            )
            return
        Path(path.parent).mkdir(parents=True, exist_ok=True)
        initial = self.preset_var.get().strip()
        name = simpledialog.askstring(
            self._("preset_save_title"),
            self._("preset_save_prompt"),
            initialvalue=initial,
            parent=self,
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showerror(self._("presets_title"), self._("preset_name_empty"))
            return
        existing = get_preset(path, name)
        if existing is not None:
            if not messagebox.askyesno(
                self._("presets_title"),
                self._("preset_replace", name=name),
                parent=self,
            ):
                return
        preset = self._current_filter_preset(name)
        try:
            upsert_preset(path, preset)
        except OSError as exc:
            messagebox.showerror(self._("presets_title"), str(exc))
            return
        self._refresh_preset_combo()
        self.preset_var.set(name)
        self.status_var.set(
            self._("preset_saved", name=name, filename=PRESETS_FILENAME)
        )

    def _load_selected_preset(self) -> None:
        path = self._presets_path()
        name = self.preset_var.get().strip()
        if path is None:
            messagebox.showerror(self._("presets_title"), self._("preset_need_target_short"))
            return
        if not name:
            messagebox.showinfo(self._("presets_title"), self._("preset_select_load"))
            return
        preset = get_preset(path, name)
        if preset is None:
            messagebox.showinfo(self._("presets_title"), self._("preset_not_found", name=name))
            self._refresh_preset_combo()
            return
        self._apply_filter_preset(preset)

    def _delete_selected_preset(self) -> None:
        path = self._presets_path()
        name = self.preset_var.get().strip()
        if path is None:
            messagebox.showerror(self._("presets_title"), self._("preset_need_target_short"))
            return
        if not name:
            messagebox.showinfo(self._("presets_title"), self._("preset_select_delete"))
            return
        if not messagebox.askyesno(
            self._("presets_title"),
            self._("preset_delete_confirm", name=name),
            parent=self,
        ):
            return
        try:
            delete_preset(path, name)
        except OSError as exc:
            messagebox.showerror(self._("presets_title"), str(exc))
            return
        self.preset_var.set("")
        self._refresh_preset_combo()
        self.status_var.set(self._("preset_deleted", name=name))

    def _clear_filters(self, status_prefix: Optional[str] = None) -> None:
        self._filter_trace_lock = True
        try:
            self.search_var.set("")
            self._machine_sel = set()
            self._update_machines_button()
            self.date_from_var.set("")
            self.date_to_var.set("")
            self.size_min_var.set("")
            self.size_max_var.set("")
            self.mtime_from_var.set("")
            self.mtime_to_var.set("")
            self.source_type_var.set(self._all_token())
            self.control_var.set(self._all_token())
            self.provenance_var.set(self._all_token())
            if hasattr(self, "role_var"):
                self.role_var.set(self._all_token())
            self.programmer_var.set(self._all_token())
            self.newest_only_var.set(False)
            self._sort_col = None
            self._sort_reverse = False
            self._refresh_heading_labels()
        finally:
            self._filter_trace_lock = False
        self._run_query_now(status_prefix=status_prefix)

    def _on_filter_changed(self, *_args) -> None:
        if self._filter_trace_lock:
            return
        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
        self._search_after_id = self.after(SEARCH_DEBOUNCE_MS, self._run_query_now)
        self._schedule_filter_ini_save()

    def _on_search_auto_refresh_toggled(self) -> None:
        self._save_instance_ini()
        self._arm_search_auto_refresh()

    def _include_unknown_locked(self) -> bool:
        """Floor client / operator lock: include-UNKNOWN cannot be turned off."""
        return self._is_simple() or bool(self._settings_locked)

    def _effective_include_unknown(self) -> bool:
        if self._include_unknown_locked():
            return True
        return bool(self.include_unknown_var.get())

    def _sync_include_unknown_widget(self) -> None:
        """Force ON + disable when floor/locked; otherwise leave editable."""
        locked = self._include_unknown_locked()
        if locked:
            self.include_unknown_var.set(True)
        cb = getattr(self, "_include_unknown_cb", None)
        if cb is None:
            return
        try:
            cb.configure(state=tk.DISABLED if locked else tk.NORMAL)
        except tk.TclError:
            pass

    def _on_include_unknown_toggled(self) -> None:
        if self._include_unknown_locked():
            self.include_unknown_var.set(True)
            self._sync_include_unknown_widget()
            messagebox.showinfo(
                self._("include_unknown"),
                self._("include_unknown_locked"),
            )
            return
        if not bool(self.include_unknown_var.get()):
            if not messagebox.askyesno(
                self._("include_unknown"),
                self._("include_unknown_off_warn"),
                parent=self,
            ):
                self.include_unknown_var.set(True)
                return
        self._save_instance_ini()
        self._on_filter_changed()

    def _note_db_mtime(self) -> None:
        db_path = self._db_path()
        if db_path is None or not db_path.is_file():
            self._db_mtime_seen = None
            return
        try:
            self._db_mtime_seen = db_path.stat().st_mtime
        except OSError:
            self._db_mtime_seen = None

    def _arm_search_auto_refresh(self) -> None:
        if self._auto_refresh_after_id is not None:
            try:
                self.after_cancel(self._auto_refresh_after_id)
            except tk.TclError:
                pass
            self._auto_refresh_after_id = None
        if not bool(self.search_auto_refresh_var.get()):
            return
        self._note_db_mtime()
        ms = max(5, int(self._search_auto_refresh_s)) * 1000
        self._auto_refresh_after_id = self.after(ms, self._search_auto_refresh_tick)

    def _search_auto_refresh_tick(self) -> None:
        self._auto_refresh_after_id = None
        try:
            if not bool(self.search_auto_refresh_var.get()):
                return
            if self._scan_busy:
                return
            db_path = self._db_path()
            if db_path is None or not db_path.is_file():
                return
            try:
                mtime = db_path.stat().st_mtime
            except OSError:
                return
            prev = self._db_mtime_seen
            if prev is None:
                self._db_mtime_seen = mtime
            elif mtime > prev + 0.01:
                self._db_mtime_seen = mtime
                # Soft refresh — keep filters, don't flash errors
                self._run_query_now(status_prefix=self._("search_auto_refresh_done"))
        finally:
            if bool(self.search_auto_refresh_var.get()):
                ms = max(5, int(self._search_auto_refresh_s)) * 1000
                try:
                    self._auto_refresh_after_id = self.after(
                        ms, self._search_auto_refresh_tick
                    )
                except tk.TclError:
                    self._auto_refresh_after_id = None

    def _run_query_now(self, status_prefix: Optional[str] = None) -> None:
        self._search_after_id = None
        self.tree.delete(*self.tree.get_children())
        self._result_rows = []
        self._clear_preview()

        db_path = self._db_path()
        if db_path is None or not db_path.is_file():
            self.status_var.set(self._("status_no_db"))
            return

        text = self.search_var.get().strip() or None
        machines = self._selected_machines()
        date_from = self.date_from_var.get().strip() or None
        date_to = self.date_to_var.get().strip() or None
        size_min = self.size_min_var.get().strip() or None
        size_max = self.size_max_var.get().strip() or None
        mtime_from = self.mtime_from_var.get().strip() or None
        mtime_to = self.mtime_to_var.get().strip() or None
        source_type = self.source_type_var.get().strip()
        control = self.control_var.get().strip()
        provenance = self._status_filter_value()
        role = self._role_filter_value()
        programmer = self.programmer_var.get().strip()
        if self._is_all_token(programmer):
            programmer_filter = None
        else:
            programmer_filter = programmer

        try:
            conn = open_db(db_path)
            try:
                rows = query_instances(
                    conn,
                    text=text,
                    machines=machines or None,
                    date_from=date_from,
                    date_to=date_to,
                    size_min=size_min,
                    size_max=size_max,
                    mtime_from=mtime_from,
                    mtime_to=mtime_to,
                    source_type=None if self._is_all_token(source_type) else source_type,
                    control_family=None if self._is_all_token(control) else control,
                    provenance=provenance,
                    role=role,
                    programmer=programmer_filter,
                    newest_only=bool(self.newest_only_var.get()),
                    include_unknown=self._effective_include_unknown(),
                    limit=BROWSE_LIMIT,
                )
                total = conn.execute("SELECT COUNT(*) FROM program_instances").fetchone()[0]
            finally:
                conn.close()
        except ValueError as exc:
            self.status_var.set(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(self._("search_error", error=exc))
            return

        self._fill_tree(rows)
        missing_n = int(getattr(self, "_missing_source_count", 0) or 0)
        bits = [self._("status_shown", n=len(rows))]
        if total > len(rows):
            bits.append(self._("status_of_db", total=total))
        if missing_n:
            bits.append(self._("status_missing_sources", n=missing_n))
        if text:
            bits.append(f"text={text!r}")
        if machines:
            bits.append(f"machines={len(machines)}")
            if self._effective_include_unknown():
                bits.append(self._("status_include_unknown"))
        if date_from or date_to:
            bits.append(f"dates={date_from or '…'}→{date_to or '…'}")
        if size_min or size_max:
            bits.append(f"size={size_min or '…'}→{size_max or '…'}")
        if mtime_from or mtime_to:
            bits.append(f"file={mtime_from or '…'}→{mtime_to or '…'}")
        if source_type and not self._is_all_token(source_type):
            bits.append(f"type={source_type}")
        if control and not self._is_all_token(control):
            bits.append(f"control={control}")
        if provenance:
            bits.append(f"status={provenance}")
        if role:
            bits.append(f"role={role}")
        if programmer_filter:
            bits.append(f"programmer={programmer_filter}")
        if self.newest_only_var.get():
            bits.append(self._("status_newest_only"))
        if self._sort_col:
            arrow = "↓" if self._sort_reverse else "↑"
            bits.append(f"sort={self._sort_col}{arrow}")
        summary = " · ".join(bits)
        if status_prefix:
            self.status_var.set(f"{status_prefix} — {summary}")
        else:
            self.status_var.set(summary)

    def _load_colour_catalog(self) -> None:
        target = self.target_var.get().strip()
        if target:
            self._colour_catalog = load_colour_catalog(
                folder_colour_aliases_path_for_target(target)
            )
        else:
            self._colour_catalog = ColourCatalog()
        self._configure_colour_tags()
        if hasattr(self, "provenance_combo"):
            cur = self.provenance_var.get()
            labels = self._status_filter_labels()
            self.provenance_combo["values"] = labels
            if cur not in labels:
                self.provenance_var.set(self._all_token())
        if hasattr(self, "role_combo"):
            cur = self.role_var.get()
            labels = self._role_filter_labels()
            self.role_combo["values"] = labels
            if cur not in labels:
                self.role_var.set(self._all_token())
        if hasattr(self, "tree") and getattr(self, "_result_rows", None) is not None:
            self._redraw_tree()

    def _configure_colour_tags(self) -> None:
        if not hasattr(self, "tree"):
            return
        self.tree.tag_configure(
            "flag_backup", foreground=STATUS_SWATCH[PROVENANCE_BACKUP]
        )
        self.tree.tag_configure(
            "flag_extra", foreground=STATUS_SWATCH[PROVENANCE_EXTRA]
        )
        for c in self._colour_catalog.colours:
            tag = f"flag_{c.id}"
            try:
                self.tree.tag_configure(tag, foreground=c.swatch)
            except tk.TclError:
                self.tree.tag_configure(tag, foreground="#888888")

    def _status_filter_labels(self) -> list[str]:
        return [
            self._all_token(),
            self._("status_on_machine"),
            self._("status_unknown"),
        ]

    def _role_filter_labels(self) -> list[str]:
        labels = [self._all_token()]
        for c in getattr(self, "_colour_catalog", ColourCatalog()).colours:
            labels.append(c.label(self._lang))
        return labels

    def _provenance_filter_labels(self) -> list[str]:
        # Back-compat alias used by presets / older code paths
        return self._status_filter_labels()

    def _colour_id_from_filter_label(self, raw: str) -> Optional[str]:
        if not raw or self._is_all_token(raw):
            return None
        catalog = getattr(self, "_colour_catalog", ColourCatalog())
        for c in catalog.colours:
            if raw == c.label(self._lang) or raw == c.label_pl or raw == c.label_en:
                return c.id
            if raw.casefold() == c.id:
                return c.id
        low = raw.casefold()
        if raw in (
            self._("status_not_run"),
            self._("status_unknown"),
        ) or any(
            x in low
            for x in (
                "yellow",
                "żółt",
                "extra",
                "not_run",
                "nie uruch",
                "nieznan",
                "unknown",
            )
        ):
            return PROVENANCE_EXTRA
        if raw in (self._("status_on_machine"),) or any(
            x in low for x in ("green", "zielon", "backup", "on_machine", "maszyn")
        ):
            return PROVENANCE_BACKUP
        # Never treat status spellings as role ids (yellow ≠ fixture)
        if is_status_colour_id(raw):
            return PROVENANCE_EXTRA if "yellow" in low or "extra" in low or "nieznan" in low or "unknown" in low else PROVENANCE_BACKUP
        cid = normalize_colour_id(raw, known_ids=catalog.colour_ids)
        return cid if cid in catalog.colour_ids else None

    def _status_badge(self, prov: str) -> str:
        """Status disc (colour via Treeview tag foreground — Windows-safe)."""
        return status_dot(prov)

    def _flag_badge_and_tag(self, prov: str, role: Optional[str] = None) -> tuple[str, str]:
        """Return Flag-column text + tree tag (swatch colour, not emoji)."""
        status = prov or PROVENANCE_BACKUP
        tags = roles_from_db(role)
        return flag_text(status, tags), flag_tag(status, tags)

    def _provenance_filter_value(self) -> Optional[str]:
        return self._status_filter_value()

    def _status_filter_value(self) -> Optional[str]:
        raw = self.provenance_var.get().strip()
        if not raw or self._is_all_token(raw):
            return None
        if raw == self._("status_on_machine"):
            return PROVENANCE_BACKUP
        if raw in (self._("status_not_run"), self._("status_unknown")):
            return PROVENANCE_EXTRA
        return self._colour_id_from_filter_label(raw)

    def _role_filter_value(self) -> Optional[str]:
        raw = self.role_var.get().strip()
        if not raw or self._is_all_token(raw):
            return None
        catalog = getattr(self, "_colour_catalog", ColourCatalog())
        for c in catalog.colours:
            if raw == c.label(self._lang) or raw == c.label_pl or raw == c.label_en:
                return c.id
            if raw.casefold() == c.id:
                return c.id
        return None

    def _fill_tree(self, rows: list) -> None:
        if self._sort_col:
            rows = sort_instances(
                rows, self._sort_col, reverse=self._sort_reverse
            )
        self._result_rows = list(rows)
        self._redraw_tree()

    def _redraw_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        badge_missing = self._("badge_missing")
        backup = self.backup_var.get().strip() or (self._backup_root_from_db() or "")
        remaps = self._active_path_remaps()
        missing_n = 0
        for i, r in enumerate(self._result_rows):
            date = format_display_date(r["backup_date"])
            machine = r["machine_label"] or r["machine_id"] or ""
            keys = r.keys() if hasattr(r, "keys") else ()
            control = r["control_family"] if "control_family" in keys else ""
            size_val = ""
            if "source_size" in keys:
                size_val = format_display_size(r["source_size"])
            prog_flag = ""
            if "programmer" in keys and r["programmer"]:
                prog_flag = str(r["programmer"])
            prov = ""
            if "provenance" in keys:
                prov = str(r["provenance"] or PROVENANCE_BACKUP)
            role = None
            if "role" in keys and r["role"]:
                role = str(r["role"]).strip() or None
            flag, tag = self._flag_badge_and_tag(prov, role)
            missing = self._row_source_missing(
                r, backup_root=backup or None, path_remaps=remaps
            )
            if missing:
                missing_n += 1
            src_badge = badge_missing if missing else ""
            tags = ("source_missing",) if missing else (tag,)
            self.tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(
                    flag,
                    src_badge,
                    r["program_number"] or "",
                    r["part_number"] or "",
                    prog_flag,
                    machine,
                    date,
                    size_val,
                    r["source_type"] or "",
                    control or "",
                    r["source_path"] or "",
                    format_location(r),
                ),
                tags=tags,
            )
        self._missing_source_count = missing_n
        self._refresh_heading_labels()
        self._refresh_preview()

    def _row_source_missing(
        self,
        row,
        *,
        backup_root: Optional[str] = None,
        path_remaps=None,
    ) -> bool:
        """True when the indexed source file is not present on disk."""
        try:
            sp = str(row["source_path"] or "").strip()
        except (KeyError, IndexError, TypeError):
            return True
        if not sp:
            return True
        if backup_root is None:
            backup_root = self.backup_var.get().strip() or (
                self._backup_root_from_db() or ""
            )
        keys = row.keys() if hasattr(row, "keys") else ()
        scan_root = None
        if "scan_root" in keys and row["scan_root"]:
            scan_root = str(row["scan_root"])
        remaps = (
            path_remaps
            if path_remaps is not None
            else self._active_path_remaps()
        )
        return not source_exists_on_disk(
            sp,
            backup_root or None,
            scan_root,
            path_remaps=remaps,
        )

    def _refresh_heading_labels(self) -> None:
        if not hasattr(self, "tree") or not self._heading_labels:
            return
        for key, base in self._heading_labels.items():
            if self._sort_col == key:
                mark = " ▼" if self._sort_reverse else " ▲"
                self.tree.heading(key, text=base + mark)
            else:
                self.tree.heading(key, text=base)

    def _on_sort_column(self, column: str) -> None:
        """Toggle asc/desc sort when a results-table heading is clicked (#3)."""
        if self._sort_col == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = column
            # Dates/sizes: newest/largest first on first click feels natural
            # Source badge: missing (BRAK) first on first click (reverse=False)
            self._sort_reverse = column in {"date", "size", "mtime"}
        if not self._result_rows:
            self._refresh_heading_labels()
            self._schedule_filter_ini_save()
            return
        if column == "src":
            # key 0 = missing; reverse=False → missing first
            self._result_rows = sorted(
                self._result_rows,
                key=lambda r: (0 if self._row_source_missing(r) else 1),
                reverse=self._sort_reverse,
            )
        else:
            self._result_rows = sort_instances(
                self._result_rows, column, reverse=self._sort_reverse
            )
        self._redraw_tree()
        self._schedule_filter_ini_save()

    def _set_preview_body(self, header: str, body: str, *, is_error: bool = False) -> None:
        self.preview_header_var.set(header)
        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", body)
        self.preview_text.configure(
            state=tk.DISABLED,
            foreground="#a40000" if is_error else "#222222",
        )
        self._preview_find_reapply()

    def _clear_preview(self) -> None:
        self._set_preview_body(self._("preview_idle"), "")

    def _on_tree_select(self, *_args) -> None:
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        rows = self._selected_rows()
        if not rows:
            self._clear_preview()
            return
        row = rows[0]
        label = instance_label(row)
        if len(rows) > 1:
            header = self._(
                "preview_header_multi", label=label, n=len(rows)
            )
        else:
            header = self._("preview_header", label=label)
        backup = self.backup_var.get().strip() or (self._backup_root_from_db() or "")
        body, err = preview_text(
            row,
            backup_root=backup or None,
            path_remaps=self._active_path_remaps(),
            lang=self._lang,
        )
        if err:
            self._set_preview_body(
                header, self._("preview_error", error=err), is_error=True
            )
            return
        self._set_preview_body(header, body)

    def _on_preview_find_typed(self, *_args) -> None:
        self._preview_find_reapply(keep_index=False)

    def _preview_find_clear_tags(self) -> None:
        if not hasattr(self, "preview_text"):
            return
        try:
            self.preview_text.tag_remove("preview_find_hit", "1.0", tk.END)
            self.preview_text.tag_remove("preview_find_current", "1.0", tk.END)
        except tk.TclError:
            pass

    def _preview_find_reapply(self, *, keep_index: bool = True) -> None:
        """Recompute match list from current needle + preview body; update highlights."""
        if not hasattr(self, "preview_text"):
            return
        needle = (self.preview_find_var.get() or "").strip()
        self._preview_find_clear_tags()
        self._preview_find_matches = []
        if not needle:
            self._preview_find_index = -1
            self.preview_find_status_var.set("")
            return
        # Text.search needs NORMAL briefly for some platforms; we keep DISABLED after.
        was = str(self.preview_text.cget("state"))
        try:
            self.preview_text.configure(state=tk.NORMAL)
            start = "1.0"
            while True:
                pos = self.preview_text.search(
                    needle, start, stopindex=tk.END, nocase=True
                )
                if not pos:
                    break
                end = f"{pos}+{len(needle)}c"
                self._preview_find_matches.append(pos)
                self.preview_text.tag_add("preview_find_hit", pos, end)
                start = end
        except tk.TclError:
            self._preview_find_matches = []
        finally:
            try:
                self.preview_text.configure(state=was)
            except tk.TclError:
                pass
        if not self._preview_find_matches:
            self._preview_find_index = -1
            self.preview_find_status_var.set(self._("preview_find_none"))
            return
        if keep_index and 0 <= self._preview_find_index < len(self._preview_find_matches):
            idx = self._preview_find_index
        else:
            idx = 0
        self._preview_find_goto(idx)

    def _preview_find_goto(self, index: int) -> None:
        matches = self._preview_find_matches
        if not matches or not hasattr(self, "preview_text"):
            return
        n = len(matches)
        idx = index % n
        self._preview_find_index = idx
        needle = (self.preview_find_var.get() or "").strip()
        pos = matches[idx]
        end = f"{pos}+{len(needle)}c"
        try:
            was = str(self.preview_text.cget("state"))
            self.preview_text.configure(state=tk.NORMAL)
            self.preview_text.tag_remove("preview_find_current", "1.0", tk.END)
            self.preview_text.tag_add("preview_find_current", pos, end)
            self.preview_text.see(pos)
            self.preview_text.configure(state=was)
        except tk.TclError:
            pass
        self.preview_find_status_var.set(
            self._("preview_find_status", current=idx + 1, total=n)
        )

    def _preview_find_next(self, *_args) -> None:
        if not self._preview_find_matches:
            self._preview_find_reapply(keep_index=False)
            return
        self._preview_find_goto(self._preview_find_index + 1)

    def _preview_find_prev(self, *_args) -> None:
        if not self._preview_find_matches:
            self._preview_find_reapply(keep_index=False)
            return
        self._preview_find_goto(self._preview_find_index - 1)

    def _compare_selected(self) -> None:
        rows = self._selected_rows()
        if len(rows) != 2:
            messagebox.showinfo(
                self._("compare_title"),
                self._("compare_need_two"),
            )
            return
        backup = self.backup_var.get().strip() or (self._backup_root_from_db() or "")
        diff_text, err = unified_diff_programs(
            rows[0],
            rows[1],
            backup_root=backup or None,
            path_remaps=self._active_path_remaps(),
            lang=self._lang,
        )
        if err:
            messagebox.showerror(self._("compare_title"), err)
            return
        CompareDiffDialog(
            self,
            label_a=instance_label(rows[0]),
            label_b=instance_label(rows[1]),
            diff_text=diff_text,
        )

    # --- row actions ------------------------------------------------------------

    def _selected_rows(self) -> list:
        rows: list = []
        for iid in self.tree.selection():
            try:
                idx = int(iid)
            except ValueError:
                continue
            if 0 <= idx < len(self._result_rows):
                rows.append(self._result_rows[idx])
        return rows

    def _selected_row(self):
        rows = self._selected_rows()
        return rows[0] if rows else None

    def _on_tree_context(self, event) -> None:
        row_id = self.tree.identify_row(event.y)
        if row_id:
            # Keep multi-selection when right-clicking an already-selected row
            if row_id not in self.tree.selection():
                self.tree.selection_set(row_id)
            self.tree.focus(row_id)
        try:
            self._ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._ctx_menu.grab_release()

    def _row_source_path(self) -> Optional[Path]:
        row = self._selected_row()
        if row is None:
            messagebox.showinfo(self._("selection"), self._("err_select_row"))
            return None
        backup = self.backup_var.get().strip() or (self._backup_root_from_db() or "")
        sp = str(row["source_path"] or "")
        if not sp:
            messagebox.showerror(self._("path"), self._("err_no_source_path"))
            return None
        keys = row.keys() if hasattr(row, "keys") else ()
        scan_root = None
        if "scan_root" in keys and row["scan_root"]:
            scan_root = str(row["scan_root"])
        return resolve_source_abspath(
            sp,
            backup or None,
            scan_root,
            path_remaps=self._active_path_remaps(),
        )

    def _open_selected_folder(self) -> None:
        path = self._row_source_path()
        if path is None:
            return
        if not path.exists():
            messagebox.showerror(
                self._("ctx_open"),
                self._("open_source_missing", path=str(path)),
            )
            return
        try:
            open_path_in_file_manager(path)
            self.status_var.set(self._("status_opened_folder", name=path.name))
        except OSError as exc:
            messagebox.showerror(self._("open_folder"), str(exc))

    def _copy_selected_path(self) -> None:
        path = self._row_source_path()
        if path is None:
            return
        text = str(path)
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
        except tk.TclError as exc:
            messagebox.showerror(self._("copy_path"), str(exc))
            return
        self.status_var.set(self._("status_copied_path", path=text))

    def _extract_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            messagebox.showinfo(self._("extract_title"), self._("extract_need_selection"))
            return
        backup = self.backup_var.get().strip()
        extract_dir = self._extract_dir()
        if not backup:
            backup = self._backup_root_from_db() or ""
        if not extract_dir:
            messagebox.showerror(
                self._("extract_folder"),
                self._("extract_folder")
                + "\n\n"
                + self._("extract_folder_hint"),
            )
            return

        # Resolve roots: any selected row may use scan_root
        needs_backup = False
        for row in rows:
            keys = row.keys() if hasattr(row, "keys") else ()
            scan_root = str(row["scan_root"]) if "scan_root" in keys and row["scan_root"] else ""
            if not scan_root:
                needs_backup = True
                break
        if needs_backup and (not backup or not Path(backup).is_dir()):
            messagebox.showerror(
                self._("backup_folder"),
                self._("extract_need_backup"),
            )
            return

        Path(extract_dir).mkdir(parents=True, exist_ok=True)

        if len(rows) == 1:
            row = rows[0]
            missing_path = self._missing_source_path(row)
            if missing_path is not None:
                messagebox.showerror(
                    self._("extract_failed"),
                    self._("extract_source_missing", path=str(missing_path)),
                )
                return
            suggested = default_extract_filename(row)
            out = filedialog.asksaveasfilename(
                title=self._("extract_save_title"),
                initialdir=extract_dir,
                initialfile=suggested,
                defaultextension=".nc",
                filetypes=[(self._("filetype_nc"), "*.nc *.txt *.mpf *.pgm"), (self._("filetype_all"), "*.*")],
            )
            if not out:
                return
            try:
                path = extract_to_path(
                    row,
                    out,
                    backup_root=backup or None,
                    path_remaps=self._active_path_remaps(),
                )
            except ExtractError as exc:
                messagebox.showerror(
                    self._("extract_failed"),
                    self._format_extract_error(exc, row),
                )
                return
            self.status_var.set(self._("status_extracted", path=path))
            messagebox.showinfo(self._("extract_wrote_title"), self._("extract_wrote", path=path))
            return

        # Batch: pick output folder, write unique filenames
        out_dir = filedialog.askdirectory(
            title=self._("extract_batch_title", n=len(rows)),
            initialdir=extract_dir,
        )
        if not out_dir:
            return
        used: set[str] = set()
        ok = 0
        errors: list[str] = []
        remaps = self._active_path_remaps()
        for row in rows:
            name = batch_extract_filename(row, used=used)
            dest = Path(out_dir) / name
            missing_path = self._missing_source_path(row)
            if missing_path is not None:
                prog = row["program_number"] if "program_number" in row.keys() else "?"
                errors.append(
                    f"{prog}: {self._('badge_missing')} — {missing_path}"
                )
                continue
            try:
                extract_to_path(
                    row, dest, backup_root=backup or None, path_remaps=remaps
                )
                ok += 1
            except ExtractError as exc:
                prog = row["program_number"] if "program_number" in row.keys() else "?"
                errors.append(f"{prog}: {self._format_extract_error(exc, row)}")
        msg = self._(
            "extract_batch_ok", ok=ok, total=len(rows), folder=out_dir
        )
        if errors:
            msg = self._(
                "extract_batch_partial",
                ok=ok,
                total=len(rows),
                failed=len(errors),
                folder=out_dir,
            )
            detail = "\n".join(errors[:8])
            if len(errors) > 8:
                detail += "\n" + self._("map_more", n=len(errors) - 8)
            msg = f"{msg}\n\n{detail}"
            messagebox.showwarning(self._("extract_batch_dialog_title"), msg)
        else:
            messagebox.showinfo(self._("extract_batch_dialog_title"), msg)
        self.status_var.set(
            self._("extract_batch_ok", ok=ok, total=len(rows), folder=out_dir).split("\n")[0]
        )

    def _missing_source_path(self, row) -> Optional[Path]:
        """Return resolved path when source is missing; else None."""
        if not self._row_source_missing(row):
            return None
        try:
            sp = str(row["source_path"] or "").strip()
        except (KeyError, IndexError, TypeError):
            return Path("(no source_path)")
        backup = self.backup_var.get().strip() or (self._backup_root_from_db() or "")
        keys = row.keys() if hasattr(row, "keys") else ()
        scan_root = None
        if "scan_root" in keys and row["scan_root"]:
            scan_root = str(row["scan_root"])
        return resolve_source_abspath(
            sp or "(empty)",
            backup or None,
            scan_root,
            path_remaps=self._active_path_remaps(),
        )

    def _format_extract_error(self, exc: ExtractError, row=None) -> str:
        msg = str(exc)
        if "missing" in msg.casefold():
            path = self._missing_source_path(row) if row is not None else None
            if path is None and row is not None:
                # Error says missing but our check disagreed — still localize
                try:
                    path = resolve_source_abspath(
                        str(row["source_path"] or ""),
                        self.backup_var.get().strip() or None,
                        path_remaps=self._active_path_remaps(),
                    )
                except Exception:  # noqa: BLE001
                    path = Path("?")
            return self._(
                "extract_source_missing",
                path=str(path) if path is not None else msg,
            )
        return msg

    def _backup_root_from_db(self) -> Optional[str]:
        db_path = self._db_path()
        if db_path is None or not db_path.is_file():
            return None
        try:
            conn = open_db(db_path)
            try:
                cur = conn.execute(
                    "SELECT backup_root FROM index_runs ORDER BY started_at DESC LIMIT 1"
                )
                hit = cur.fetchone()
                return hit[0] if hit else None
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            return None


class ManualViewerDialog(tk.Toplevel):
    """Scrollable window for bundled markdown manuals."""

    def __init__(
        self,
        master: tk.Tk,
        *,
        title: str,
        body: str,
        close_label: str = "Close"  # callers pass i18n,
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.geometry("780x620")
        self.minsize(480, 360)
        frame = ttk.Frame(self, padding=8)
        frame.pack(fill=tk.BOTH, expand=True)
        text = tk.Text(
            frame,
            wrap=tk.WORD,
            font=("Segoe UI", 10) if sys.platform == "win32" else ("TkDefaultFont", 10),
        )
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=sb.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        text.insert("1.0", body)
        text.configure(state=tk.DISABLED)
        ttk.Button(self, text=close_label, command=self.destroy).pack(
            pady=(0, 8)
        )
        self.bind("<Escape>", lambda _e: self.destroy())


class CompareDiffDialog(tk.Toplevel):
    """Unified diff of two selected program instances (#12)."""

    def __init__(
        self,
        master: tk.Tk,
        *,
        label_a: str,
        label_b: str,
        diff_text: str,
    ) -> None:
        super().__init__(master)
        self.title(_tr(master, "compare_title"))
        self.minsize(640, 420)
        self.geometry("860x560")
        self.transient(master)
        self.grab_set()

        ttk.Label(
            self,
            text=_tr(master, "compare_labels", a=label_a, b=label_b),
            wraplength=820,
        ).pack(fill=tk.X, padx=12, pady=(12, 6))

        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        text = tk.Text(frame, wrap=tk.NONE, font=("Consolas", 10), height=24)
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=text.xview)
        text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        text.tag_configure("add", foreground="#1a7f37")
        text.tag_configure("del", foreground="#a40000")
        text.tag_configure("meta", foreground="#555555")
        text.tag_configure("hunk", foreground="#0057b8")

        for line in diff_text.splitlines(keepends=True):
            if line.startswith("+++") or line.startswith("---"):
                tag = "meta"
            elif line.startswith("@@"):
                tag = "hunk"
            elif line.startswith("+"):
                tag = "add"
            elif line.startswith("-"):
                tag = "del"
            else:
                tag = None
            if tag:
                text.insert(tk.END, line, tag)
            else:
                text.insert(tk.END, line)
        text.configure(state=tk.DISABLED)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btns, text=_tr(master, "close"), command=self.destroy).pack(side=tk.RIGHT)


class ScanHistoryDialog(tk.Toplevel):
    """Last N index runs — when, duration, added/updated/removed/cached."""

    def __init__(
        self,
        master: tk.Tk,
        *,
        entries: list,
        title: str,
        empty_label: str,
        close_label: str,
        columns: tuple[str, ...],
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.minsize(720, 360)
        self.geometry("900x420")
        self.transient(master)
        self.grab_set()

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        cols = ("when", "dur", "inst", "add", "upd", "rem", "cached", "mode")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=14)
        labels = {
            "when": columns[0],
            "dur": columns[1],
            "inst": columns[2],
            "add": columns[3],
            "upd": columns[4],
            "rem": columns[5],
            "cached": columns[6],
            "mode": columns[7],
        }
        widths = {
            "when": 160,
            "dur": 70,
            "inst": 70,
            "add": 70,
            "upd": 70,
            "rem": 70,
            "cached": 70,
            "mode": 110,
        }
        for key in cols:
            tree.heading(key, text=labels[key])
            tree.column(key, width=widths[key], stretch=key in ("when", "mode"))
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        if not entries:
            tree.insert("", tk.END, values=(empty_label, "", "", "", "", "", "", ""))
        else:
            for entry in entries:
                when = (entry.finished_at or entry.started_at or "")[:19].replace(
                    "T", " "
                )
                mode = []
                if entry.incremental:
                    mode.append(_tr(master, "history_mode_incr"))
                else:
                    mode.append(_tr(master, "history_mode_full"))
                if entry.auto:
                    mode.append(_tr(master, "history_mode_auto"))
                tree.insert(
                    "",
                    tk.END,
                    values=(
                        when,
                        entry.duration_label(),
                        entry.instance_count,
                        entry.files_added,
                        entry.files_updated,
                        entry.files_removed,
                        entry.files_cached,
                        "+".join(mode),
                    ),
                )

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btns, text=close_label, command=self.destroy).pack(side=tk.RIGHT)


class ScanReportDialog(tk.Toplevel):
    """Post-scan quality summary (#14): counts, copies, UNKNOWN, skipped."""

    def __init__(self, master: tk.Tk, *, report: ScanReport) -> None:
        super().__init__(master)
        self.title(_tr(master, "scan_report_title"))
        self.minsize(560, 420)
        self.geometry("720x560")
        self.transient(master)
        self.grab_set()
        lang = getattr(master, "_lang", "pl")

        ttk.Label(
            self,
            text=_tr(master, "scan_report_intro"),
            wraplength=680,
        ).pack(fill=tk.X, padx=12, pady=(12, 6))

        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        text = tk.Text(frame, wrap=tk.WORD, font=("Consolas", 10), height=24)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=sb.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        body = format_scan_report(report, lang=lang)
        text.insert("1.0", body)
        text.configure(state=tk.DISABLED)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btns, text=_tr(master, "close"), command=self.destroy).pack(side=tk.RIGHT)


class DuplicatesDialog(tk.Toplevel):
    """Exact body SHA and near-duplicate finder; colour-conflict hygiene (#13)."""

    def __init__(self, master: tk.Tk, *, groups: list[DuplicateGroup]) -> None:
        super().__init__(master)
        self.title(_tr(master, "duplicates_title"))
        self.minsize(720, 480)
        self.geometry("900x580")
        self.transient(master)
        self.grab_set()
        self.selected_members: list = []
        self._all_groups = list(groups)
        self._groups: list[DuplicateGroup] = []
        self._master = master
        self._catalog = getattr(master, "_colour_catalog", None) or ColourCatalog()
        self._conflicts_only = tk.BooleanVar(value=False)

        n_exact = sum(1 for g in groups if g.kind == "exact")
        n_near = sum(1 for g in groups if g.kind == "near")
        n_conflict = sum(1 for g in groups if g.colour_conflict)
        self._summary = ttk.Label(
            self,
            text=_tr(
                master,
                "duplicates_summary",
                exact=n_exact,
                near=n_near,
                conflicts=n_conflict,
            ),
            wraplength=860,
        )
        self._summary.pack(fill=tk.X, padx=12, pady=(12, 4))

        filter_row = ttk.Frame(self)
        filter_row.pack(fill=tk.X, padx=12, pady=(0, 4))
        ttk.Checkbutton(
            filter_row,
            text=_tr(master, "dup_colour_conflicts_only"),
            variable=self._conflicts_only,
            command=self._rebuild_group_list,
        ).pack(side=tk.LEFT)
        ttk.Label(
            filter_row,
            text=_tr(master, "dup_colour_conflicts_hint", n=n_conflict),
            wraplength=520,
        ).pack(side=tk.LEFT, padx=(12, 0))

        self._banner = tk.Label(
            self,
            text="",
            anchor=tk.W,
            justify=tk.LEFT,
            padx=10,
            pady=6,
            wraplength=860,
            background="#fff3cd",
            foreground="#664d03",
            font=("Segoe UI", 10, "bold"),
        )
        # Packed on demand when a conflict group is selected

        paned = ttk.Panedwindow(self, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        top = ttk.Frame(paned)
        bottom = ttk.Frame(paned)
        paned.add(top, weight=1)
        paned.add(bottom, weight=2)

        self.group_list = tk.Listbox(top, exportselection=False, height=8)
        gsb = ttk.Scrollbar(top, orient=tk.VERTICAL, command=self.group_list.yview)
        self.group_list.configure(yscrollcommand=gsb.set)
        self.group_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        gsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.group_list.bind("<<ListboxSelect>>", self._on_group_select)

        cols = ("flag", "program", "machine", "date", "size", "sha", "path")
        self.member_tree = ttk.Treeview(
            bottom, columns=cols, show="headings", selectmode="browse", height=10
        )
        headings = {
            "flag": (_tr(master, "col_flag"), 72),
            "program": (_tr(master, "col_program"), 90),
            "machine": (_tr(master, "col_machine"), 120),
            "date": (_tr(master, "col_date"), 100),
            "size": (_tr(master, "col_size"), 70),
            "sha": (_tr(master, "col_sha"), 120),
            "path": (_tr(master, "col_path"), 280),
        }
        for key, (label, width) in headings.items():
            self.member_tree.heading(key, text=label)
            self.member_tree.column(
                key, width=width, stretch=(key == "path"), minwidth=40
            )
        self.member_tree.tag_configure(
            "flag_backup", foreground=STATUS_SWATCH[PROVENANCE_BACKUP]
        )
        self.member_tree.tag_configure(
            "flag_extra", foreground=STATUS_SWATCH[PROVENANCE_EXTRA]
        )
        for c in self._catalog.colours:
            self.member_tree.tag_configure(f"flag_{c.id}", foreground=c.swatch)
        msb = ttk.Scrollbar(bottom, orient=tk.VERTICAL, command=self.member_tree.yview)
        self.member_tree.configure(yscrollcommand=msb.set)
        self.member_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        msb.pack(side=tk.RIGHT, fill=tk.Y)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btns, text=_tr(master, "cancel"), command=self.destroy).pack(
            side=tk.RIGHT
        )
        ttk.Button(
            btns, text=_tr(master, "show_in_results"), command=self._show_in_results
        ).pack(side=tk.RIGHT, padx=8)

        self._rebuild_group_list()

    def _colour_badges(self, colour_ids: frozenset[str] | set[str]) -> str:
        """Colourable discs (not emoji) for conflict banners / lists."""
        bits: list[str] = []
        for cid in sorted(colour_ids):
            bits.append(role_dot())
        return "".join(bits) if bits else role_dot()

    def _flag_for(self, prov: str, role: str | None = None) -> tuple[str, str]:
        status = prov or PROVENANCE_BACKUP
        tags = roles_from_db(role)
        return flag_text(status, tags), flag_tag(status, tags)

    def _rebuild_group_list(self) -> None:
        only = bool(self._conflicts_only.get())
        if only:
            self._groups = [g for g in self._all_groups if g.colour_conflict]
        else:
            self._groups = list(self._all_groups)
        self.group_list.delete(0, tk.END)
        for g in self._groups:
            prefix = (
                _tr(self._master, "dup_kind_exact")
                if g.kind == "exact"
                else _tr(self._master, "dup_kind_near")
            )
            conflict = ""
            if g.colour_conflict:
                badges = self._colour_badges(g.colour_ids)
                conflict = (
                    f" ⚠ {_tr(self._master, 'dup_colour_conflict')} {badges} · "
                )
            self.group_list.insert(tk.END, f"[{prefix}]{conflict}{g.label}")
        self._hide_banner()
        self.member_tree.delete(*self.member_tree.get_children())
        if self._groups:
            self.group_list.selection_set(0)
            self._on_group_select()
        elif only:
            self._show_banner(
                _tr(self._master, "dup_colour_conflicts_none"),
                conflict=False,
            )

    def _show_banner(self, text: str, *, conflict: bool = True) -> None:
        if conflict:
            self._banner.configure(
                text=text,
                background="#f8d7da",
                foreground="#842029",
            )
        else:
            self._banner.configure(
                text=text,
                background="#e2e3e5",
                foreground="#41464b",
            )
        if self._banner.winfo_ismapped():
            return
        for child in self.winfo_children():
            if isinstance(child, ttk.Panedwindow):
                self._banner.pack(fill=tk.X, padx=12, pady=(0, 4), before=child)
                return
        self._banner.pack(fill=tk.X, padx=12, pady=(0, 4))

    def _hide_banner(self) -> None:
        if self._banner.winfo_ismapped():
            self._banner.pack_forget()

    def _on_group_select(self, *_args) -> None:
        self.member_tree.delete(*self.member_tree.get_children())
        sel = self.group_list.curselection()
        if not sel:
            self._hide_banner()
            return
        group = self._groups[sel[0]]
        if group.colour_conflict:
            badges = self._colour_badges(group.colour_ids)
            colours = ", ".join(
                self._catalog.label_for(cid, getattr(self._master, "_lang", "pl"))
                for cid in sorted(group.colour_ids)
            )
            banner = _tr(
                self._master,
                "dup_colour_conflict_banner",
                badges=badges,
                colours=colours,
                n=len(group.colour_ids),
            )
            if getattr(group, "status_conflict", False):
                status_badges = "".join(
                    status_dot(s)
                    for s in sorted(getattr(group, "status_ids", ()) or ())
                )
                banner = (
                    banner
                    + " "
                    + _tr(
                        self._master,
                        "dup_status_conflict_note",
                        badges=status_badges,
                    )
                )
            self._show_banner(banner, conflict=True)
        else:
            self._hide_banner()
        for i, m in enumerate(group.members):
            keys = m.keys()
            if "program_sha256" in keys and m["program_sha256"]:
                sha = str(m["program_sha256"])
            elif "content_sha256" in keys:
                sha = str(m["content_sha256"] or "")
            else:
                sha = ""
            sha_short = (sha[:12] + "…") if len(sha) > 12 else sha
            size = m["source_size"]
            size_s = str(size) if size is not None else ""
            machine = m["machine_label"] or m["machine_id"] or ""
            prov = "backup"
            if "provenance" in keys and m["provenance"]:
                prov = str(m["provenance"]).strip() or "backup"
            role = None
            if "role" in keys and m["role"]:
                role = str(m["role"]).strip() or None
            badge, tag = self._flag_for(prov, role)
            self.member_tree.insert(
                "",
                tk.END,
                iid=str(i),
                tags=(tag,),
                values=(
                    badge,
                    m["program_number"] or "",
                    machine,
                    format_display_date(m["backup_date"]),
                    size_s,
                    sha_short,
                    m["source_path"] or "",
                ),
            )

    def _show_in_results(self) -> None:
        sel = self.group_list.curselection()
        if not sel:
            messagebox.showinfo(
                _tr(self.master, "duplicates_title"),
                _tr(self.master, "duplicates_select_group"),
                parent=self,
            )
            return
        self.selected_members = list(self._groups[sel[0]].members)
        self.destroy()


class FolderTreeMapDialog(tk.Toplevel):
    """Lazy folder tree: assign machine + multi-role tags + exclude per path.

    Persists to ``folder_tree_map.yaml`` next to the database. Longest path
    prefix wins on reindex; name-wide role aliases accumulate (union) and path
    tags replace that union for the matched prefix.

    Right-click a folder → alias that **name** everywhere as machine or role
    (exact normalized spelling for roles).
    """

    _PLACEHOLDER = "__lazy__"

    def __init__(
        self,
        master: tk.Tk,
        *,
        roots: list[Path],
        tree_map: FolderTreeMap,
        catalog: ColourCatalog,
        machine_choices: list[str],
        save_path: Path,
        aliases: Optional[AliasMap] = None,
        local_aliases_path: Optional[Path] = None,
        colour_save_path: Optional[Path] = None,
    ) -> None:
        super().__init__(master)
        self.title(_tr(master, "map_tree_dialog_title"))
        self.minsize(720, 480)
        self.geometry("900x580")
        self.transient(master)
        self.grab_set()
        self.saved = False
        self.aliases_changed = False
        self._save_path = Path(save_path)
        self._map = FolderTreeMap(rules=list(tree_map.rules))
        self._catalog = catalog
        self._colour_map = FolderColourAliasMap(
            catalog.rules, known_ids=catalog.colour_ids
        )
        self._colour_save_path = (
            Path(colour_save_path) if colour_save_path else None
        )
        self._aliases = aliases
        self._local_aliases_path = (
            Path(local_aliases_path) if local_aliases_path else None
        )
        self._roots = [Path(r) for r in roots]
        self._choices = list(machine_choices)
        self._leave_machine = _tr(master, "map_tree_machine_leave")
        if self._leave_machine not in self._choices:
            self._choices.insert(0, self._leave_machine)
        # Normalize empty choice to leave marker
        self._choices = [
            self._leave_machine if not (c or "").strip() else c for c in self._choices
        ]
        # de-dupe preserving order
        seen: set[str] = set()
        cleaned: list[str] = []
        for c in self._choices:
            if c in seen:
                continue
            seen.add(c)
            cleaned.append(c)
        self._choices = cleaned

        self._path_by_iid: dict[str, Path] = {}
        self._tag_vars: dict[str, tk.BooleanVar] = {}
        self._selected_path: Optional[Path] = None

        ttk.Label(
            self,
            text=_tr(master, "map_tree_intro"),
            wraplength=860,
        ).pack(fill=tk.X, padx=12, pady=(12, 6))

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 8))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self._tree = ttk.Treeview(left, show="tree", selectmode="browse")
        sb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.grid(row=0, column=0, sticky=tk.NSEW)
        sb.grid(row=0, column=1, sticky=tk.NS)
        self._tree.bind("<<TreeviewOpen>>", self._on_open)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Button-3>", self._on_tree_context)
        if sys.platform == "darwin":
            self._tree.bind("<Button-2>", self._on_tree_context)
            self._tree.bind("<Control-Button-1>", self._on_tree_context)

        right = ttk.LabelFrame(body, text=_tr(master, "map_tree_assign"), padding=8)
        right.grid(row=0, column=1, sticky=tk.NSEW)
        self._path_var = tk.StringVar(value="")
        self._inherit_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self._path_var, wraplength=300).pack(
            anchor=tk.W, pady=(0, 4)
        )
        ttk.Label(
            right, textvariable=self._inherit_var, wraplength=300, style="Muted.TLabel"
        ).pack(anchor=tk.W, pady=(0, 8))

        ttk.Label(right, text=_tr(master, "map_tree_machine")).pack(anchor=tk.W)
        self._machine_var = tk.StringVar(value=self._leave_machine)
        ttk.Combobox(
            right,
            textvariable=self._machine_var,
            values=self._choices,
            state="readonly",
            width=36,
        ).pack(fill=tk.X, pady=(2, 8))

        tags_frame = ttk.LabelFrame(right, text=_tr(master, "map_tree_tags"), padding=4)
        tags_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        for c in catalog.colours:
            var = tk.BooleanVar(value=False)
            self._tag_vars[c.id] = var
            row = ttk.Frame(tags_frame)
            row.pack(anchor=tk.W, fill=tk.X)
            make_swatch(row, c.swatch, width=2, padx=2, pady=0).pack(
                side=tk.LEFT, padx=(0, 4)
            )
            ttk.Checkbutton(
                row,
                text=c.label(_lang_of(master)),
                variable=var,
            ).pack(side=tk.LEFT)

        self._exclude_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            right,
            text=_tr(master, "map_tree_exclude"),
            variable=self._exclude_var,
        ).pack(anchor=tk.W, pady=(0, 8))

        abtns = ttk.Frame(right)
        abtns.pack(fill=tk.X)
        ttk.Button(
            abtns, text=_tr(master, "map_tree_apply_node"), command=self._apply_node
        ).pack(side=tk.LEFT)
        ttk.Button(
            abtns, text=_tr(master, "map_tree_clear_node"), command=self._clear_node
        ).pack(side=tk.LEFT, padx=6)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Label(
            btns,
            text=_tr(master, "tree_alias_hint"),
            style="Muted.TLabel",
            wraplength=520,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(btns, text=_tr(master, "cancel"), command=self.destroy).pack(
            side=tk.RIGHT
        )
        ttk.Button(btns, text=_tr(master, "map_tree_save"), command=self._save).pack(
            side=tk.RIGHT, padx=8
        )

        self._populate_roots()
        self._set_editor_enabled(False)

    def _populate_roots(self) -> None:
        for root in self._roots:
            iid = self._insert_dir("", root, is_root=True)
            self._ensure_placeholder(iid, root)

    def _folder_label(self, path: Path, *, is_root: bool = False) -> str:
        label = str(path) if is_root else path.name
        exact, inherited = self._map.inherited_from(path)
        if exact is not None:
            label = f"{label} ★"
        elif inherited is not None:
            label = f"{label} ·"
        # Name-wide role / machine badges (not path rules)
        if not is_root:
            bits: list[str] = []
            role_rule = self._colour_map.rule_for_name(path.name)
            if role_rule is not None and role_rule.colour != COLOUR_EXCLUDE:
                c = self._catalog.get(role_rule.colour)
                rlab = c.label(_lang_of(self.master)) if c else role_rule.colour
                bits.append(rlab)
            if self._aliases is not None:
                info = self._aliases.resolve(path.name)
                if info.mapped:
                    bits.append(info.label or info.machine_id)
            if bits:
                label = f"{label}  [{' · '.join(bits)}]"
        return label

    def _insert_dir(self, parent: str, path: Path, *, is_root: bool = False) -> str:
        label = self._folder_label(path, is_root=is_root)
        iid = self._tree.insert(parent, tk.END, text=label, open=False)
        self._path_by_iid[iid] = path
        return iid

    def _ensure_placeholder(self, iid: str, path: Path) -> None:
        if self._tree.get_children(iid):
            return
        try:
            has_kids = any(True for _ in path.iterdir() if _.is_dir())
        except OSError:
            has_kids = False
        if has_kids:
            self._tree.insert(iid, tk.END, text="", tags=(self._PLACEHOLDER,))

    def _on_open(self, _event=None) -> None:
        sel = self._tree.focus()
        if not sel:
            return
        path = self._path_by_iid.get(sel)
        if path is None:
            return
        kids = self._tree.get_children(sel)
        if kids and self._PLACEHOLDER in self._tree.item(kids[0], "tags"):
            self._tree.delete(kids[0])
        if self._tree.get_children(sel):
            return
        for child in list_child_dirs(path):
            cid = self._insert_dir(sel, child)
            self._ensure_placeholder(cid, child)

    def _on_select(self, _event=None) -> None:
        sel = self._tree.focus()
        path = self._path_by_iid.get(sel) if sel else None
        self._selected_path = path
        if path is None:
            self._set_editor_enabled(False)
            self._path_var.set("")
            self._inherit_var.set("")
            return
        self._set_editor_enabled(True)
        self._path_var.set(str(path))
        exact, inherited = self._map.inherited_from(path)
        if exact is not None:
            self._inherit_var.set(_tr(self.master, "map_tree_explicit"))
            self._load_rule_into_editor(exact, inherited=False)
        elif inherited is not None:
            self._inherit_var.set(
                _tr(self.master, "map_tree_inherited", path=inherited.path)
            )
            self._load_rule_into_editor(inherited, inherited=True)
        else:
            self._inherit_var.set(_tr(self.master, "map_tree_no_rule"))
            self._reset_editor()

    def _load_rule_into_editor(self, rule, *, inherited: bool) -> None:
        if rule.machine_id:
            display = display_for_machine(rule.machine_id, rule.machine_id)
            for choice in self._choices:
                mid, _lab = parse_machine_display(choice)
                if mid == rule.machine_id:
                    display = choice
                    break
            self._machine_var.set(display)
        else:
            self._machine_var.set(self._leave_machine)
        selected = set(rule.tags)
        for cid, var in self._tag_vars.items():
            var.set(cid in selected)
        self._exclude_var.set(bool(rule.exclude))

    def _reset_editor(self) -> None:
        self._machine_var.set(self._leave_machine)
        for var in self._tag_vars.values():
            var.set(False)
        self._exclude_var.set(False)

    def _set_editor_enabled(self, enabled: bool) -> None:
        # Soft enable: Apply checks selection.
        return

    def _apply_node(self) -> None:
        path = self._selected_path
        if path is None:
            return
        tags = [cid for cid, var in self._tag_vars.items() if var.get()]
        exclude = bool(self._exclude_var.get())
        machine_raw = self._machine_var.get().strip()
        machine_id = None
        if machine_raw and machine_raw != self._leave_machine:
            mid, _lab = parse_machine_display(machine_raw)
            if mid and mid not in {UNKNOWN_ID, ""}:
                machine_id = mid
            elif mid == UNKNOWN_ID:
                machine_id = UNKNOWN_ID
        self._map.set_rule(
            path,
            machine_id=machine_id,
            tags=tags,
            exclude=exclude,
        )
        self._refresh_node_label(path)
        self._inherit_var.set(_tr(self.master, "map_tree_explicit"))

    def _clear_node(self) -> None:
        path = self._selected_path
        if path is None:
            return
        self._map.set_rule(path, clear=True)
        self._reset_editor()
        self._refresh_node_label(path)
        exact, inherited = self._map.inherited_from(path)
        if inherited is not None:
            self._inherit_var.set(
                _tr(self.master, "map_tree_inherited", path=inherited.path)
            )
            self._load_rule_into_editor(inherited, inherited=True)
        else:
            self._inherit_var.set(_tr(self.master, "map_tree_no_rule"))

    def _refresh_node_label(self, path: Path) -> None:
        for iid, p in self._path_by_iid.items():
            if p == path or str(p).casefold() == str(path).casefold():
                is_root = p in self._roots
                self._tree.item(iid, text=self._folder_label(p, is_root=is_root))
                break

    def _refresh_all_name_badges(self) -> None:
        for iid, p in list(self._path_by_iid.items()):
            is_root = p in self._roots
            self._tree.item(iid, text=self._folder_label(p, is_root=is_root))

    def _on_tree_context(self, event) -> None:
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        self._tree.selection_set(iid)
        self._tree.focus(iid)
        path = self._path_by_iid.get(iid)
        if path is None:
            return
        # Roots: no name-wide alias (would alias the whole backup root name)
        if path in self._roots:
            return
        name = path.name
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label=_tr(self.master, "tree_alias_machine_menu", name=name),
            command=lambda: self._alias_name_as_machine(path),
        )
        role_menu = tk.Menu(menu, tearoff=0)
        for c in self._catalog.colours:
            role_menu.add_command(
                label=c.label(_lang_of(self.master)),
                command=lambda cid=c.id, p=path: self._alias_name_as_role(p, cid),
            )
        menu.add_cascade(
            label=_tr(self.master, "tree_alias_role_menu", name=name),
            menu=role_menu,
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _alias_safety_ok(self, path: Path, name: str) -> bool:
        if path in self._roots:
            messagebox.showwarning(
                _tr(self.master, "tree_alias_title"),
                _tr(self.master, "tree_alias_block_root"),
                parent=self,
            )
            return False
        risky, reason = is_risky_alias_name(name)
        if not risky:
            return True
        if reason == "short":
            messagebox.showwarning(
                _tr(self.master, "tree_alias_title"),
                _tr(self.master, "tree_alias_block_short", name=name),
                parent=self,
            )
            return False
        key = {
            "date": "tree_alias_warn_date",
            "memory": "tree_alias_warn_memory",
        }.get(reason, "tree_alias_warn_date")
        return bool(
            messagebox.askyesno(
                _tr(self.master, "tree_alias_title"),
                _tr(self.master, key, name=name),
                parent=self,
            )
        )

    def _count_name_hits(self, name: str) -> int:
        return count_same_name_dirs(self._roots, name)

    def _preview_roles_on_path(self, path: Path, extra_role: Optional[str] = None) -> str:
        """Role union on path after applying optional new name→role for this folder."""
        parts = []
        try:
            # Relative parts under nearest root
            for root in self._roots:
                try:
                    rel = path.relative_to(root)
                    parts = list(rel.parts)
                    break
                except ValueError:
                    continue
        except Exception:
            parts = [path.name]
        if not parts:
            parts = [path.name]
        # Simulate: temporarily consider extra_role for this name
        roles: list[str] = []
        seen: set[str] = set()
        for part in parts:
            colour = None
            if extra_role and normalize_folder_name(part) == normalize_folder_name(
                path.name
            ):
                colour = extra_role
            else:
                colour = self._colour_map.match_segment(part)
            if colour and colour != COLOUR_EXCLUDE and colour not in seen:
                seen.add(colour)
                roles.append(colour)
        if not roles:
            return "—"
        labels = []
        for rid in roles:
            c = self._catalog.get(rid)
            labels.append(c.label(_lang_of(self.master)) if c else rid)
        return ", ".join(labels)

    def _alias_name_as_machine(self, path: Path) -> None:
        if self._aliases is None or self._local_aliases_path is None:
            messagebox.showinfo(
                _tr(self.master, "tree_alias_title"),
                _tr(self.master, "tree_alias_need_aliases"),
                parent=self,
            )
            return
        name = path.name
        if not self._alias_safety_ok(path, name):
            return
        # Pick machine from list (exclude leave / unknown empty)
        machines = []
        for choice in self._choices:
            if not choice or choice == self._leave_machine:
                continue
            mid, _lab = parse_machine_display(choice)
            if not mid or mid == UNKNOWN_ID:
                continue
            machines.append(choice)
        if not machines:
            messagebox.showinfo(
                _tr(self.master, "tree_alias_title"),
                _tr(self.master, "tree_alias_no_machines"),
                parent=self,
            )
            return
        pick = _pick_from_list(
            self,
            title=_tr(self.master, "tree_alias_machine_pick_title", name=name),
            prompt=_tr(self.master, "tree_alias_machine_pick_prompt", name=name),
            values=machines,
        )
        if not pick:
            return
        mid, _lab = parse_machine_display(pick)
        if not mid:
            return
        hits = self._count_name_hits(name)
        existing = self._aliases.resolve(name)
        if existing.mapped:
            cur = existing.label or existing.machine_id
            if existing.machine_id == mid:
                messagebox.showinfo(
                    _tr(self.master, "tree_alias_title"),
                    _tr(
                        self.master,
                        "tree_alias_machine_already",
                        name=name,
                        target=cur,
                    ),
                    parent=self,
                )
                return
            if not messagebox.askyesno(
                _tr(self.master, "tree_alias_replace_title"),
                _tr(
                    self.master,
                    "tree_alias_machine_replace",
                    name=name,
                    current=cur,
                    new=pick,
                    count=hits,
                ),
                parent=self,
            ):
                return
        else:
            if not messagebox.askyesno(
                _tr(self.master, "tree_alias_confirm_title"),
                _tr(
                    self.master,
                    "tree_alias_machine_confirm",
                    name=name,
                    target=pick,
                    count=hits,
                ),
                parent=self,
            ):
                return
        self._aliases.add_local_alias(name, mid)
        try:
            self._aliases.save_local(self._local_aliases_path)
        except OSError as exc:
            messagebox.showerror(_tr(self.master, "tree_alias_title"), str(exc), parent=self)
            return
        self.aliases_changed = True
        self._refresh_all_name_badges()
        messagebox.showinfo(
            _tr(self.master, "tree_alias_title"),
            _tr(self.master, "tree_alias_saved_reindex", name=name, target=pick),
            parent=self,
        )

    def _alias_name_as_role(self, path: Path, role_id: str) -> None:
        if self._colour_save_path is None:
            messagebox.showinfo(
                _tr(self.master, "tree_alias_title"),
                _tr(self.master, "tree_alias_need_roles"),
                parent=self,
            )
            return
        name = path.name
        if not self._alias_safety_ok(path, name):
            return
        role_def = self._catalog.get(role_id)
        role_label = (
            role_def.label(_lang_of(self.master)) if role_def else role_id
        )
        hits = self._count_name_hits(name)
        existing = self._colour_map.rule_for_name(name)
        if existing is not None:
            cur_def = self._catalog.get(existing.colour)
            cur_lab = (
                cur_def.label(_lang_of(self.master))
                if cur_def
                else existing.colour
            )
            if existing.colour == role_id:
                messagebox.showinfo(
                    _tr(self.master, "tree_alias_title"),
                    _tr(
                        self.master,
                        "tree_alias_role_already",
                        name=name,
                        target=cur_lab,
                    ),
                    parent=self,
                )
                return
            preview = self._preview_roles_on_path(path, extra_role=role_id)
            if not messagebox.askyesno(
                _tr(self.master, "tree_alias_replace_title"),
                _tr(
                    self.master,
                    "tree_alias_role_replace",
                    name=name,
                    current=cur_lab,
                    new=role_label,
                    count=hits,
                    path_roles=preview,
                ),
                parent=self,
            ):
                return
        else:
            preview = self._preview_roles_on_path(path, extra_role=role_id)
            if not messagebox.askyesno(
                _tr(self.master, "tree_alias_confirm_title"),
                _tr(
                    self.master,
                    "tree_alias_role_confirm",
                    name=name,
                    target=role_label,
                    count=hits,
                    path_roles=preview,
                ),
                parent=self,
            ):
                return
        self._colour_map.upsert_exact_role(name, role_id)
        # Persist full catalog with updated rules
        self._catalog = ColourCatalog(
            colours=list(self._catalog.colours),
            rules=list(self._colour_map.rules),
        )
        self._colour_map = FolderColourAliasMap(
            self._catalog.rules, known_ids=self._catalog.colour_ids
        )
        try:
            save_colour_catalog(self._colour_save_path, self._catalog)
        except OSError as exc:
            messagebox.showerror(_tr(self.master, "tree_alias_title"), str(exc), parent=self)
            return
        self.aliases_changed = True
        self._refresh_all_name_badges()
        messagebox.showinfo(
            _tr(self.master, "tree_alias_title"),
            _tr(
                self.master,
                "tree_alias_saved_reindex",
                name=name,
                target=role_label,
            ),
            parent=self,
        )

    def _save(self) -> None:
        try:
            save_folder_tree_map(self._save_path, self._map)
        except OSError as exc:
            messagebox.showerror(_tr(self.master, "map_tree_save"), str(exc), parent=self)
            return
        self.saved = True
        self.destroy()


def _pick_from_list(
    parent: tk.Misc,
    *,
    title: str,
    prompt: str,
    values: list[str],
) -> Optional[str]:
    """Simple modal list picker. Returns selected string or None."""
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.minsize(360, 280)
    result: dict[str, Optional[str]] = {"value": None}
    ttk.Label(dlg, text=prompt, wraplength=340).pack(fill=tk.X, padx=12, pady=(12, 6))
    lb = tk.Listbox(dlg, exportselection=False, height=12)
    lb.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
    for v in values:
        lb.insert(tk.END, v)
    if values:
        lb.selection_set(0)

    def _ok() -> None:
        sel = lb.curselection()
        if sel:
            result["value"] = lb.get(sel[0])
        dlg.destroy()

    def _cancel() -> None:
        dlg.destroy()

    btns = ttk.Frame(dlg)
    btns.pack(fill=tk.X, padx=12, pady=12)
    ttk.Button(btns, text=_tr(parent, "cancel"), command=_cancel).pack(side=tk.RIGHT)
    ttk.Button(btns, text=_tr(parent, "save"), command=_ok).pack(side=tk.RIGHT, padx=8)
    lb.bind("<Double-Button-1>", lambda _e: _ok())
    parent.wait_window(dlg)
    return result["value"]


def _lang_of(master) -> str:
    return getattr(master, "_lang", None) or DEFAULT_LANG


class FolderMapDialog(tk.Toplevel):
    """Assign unmatched machine folders; auto-matched ones stay out of the way.

    On save, writes ``machine_folders.yaml`` and optionally shop-local aliases
    (``aliases.local.yaml``) so the same folder names auto-match on later scans.
    """

    def __init__(
        self,
        master: tk.Tk,
        *,
        partition: FolderPartition,
        suggested: FolderMachineMap,
        existing_map: FolderMachineMap,
        aliases: AliasMap,
        machine_choices: list[str],
        save_path: Path,
        local_aliases_path: Path,
    ) -> None:
        super().__init__(master)
        self.title(_tr(master, "map_dialog_title"))
        self.minsize(560, 400)
        self.geometry("680x520")
        self.transient(master)
        self.grab_set()
        self.saved = False
        self.aliases_saved = False
        self._save_path = Path(save_path)
        self._local_aliases_path = Path(local_aliases_path)
        self._suggested = suggested
        self._existing = existing_map
        self._partition = partition
        self._aliases = aliases
        self._choices = list(machine_choices)
        self._vars: dict[str, tk.StringVar] = {}

        summary = _tr(
            master,
            "map_summary",
            auto=partition.auto_count,
            prev=len(partition.previously_mapped),
            manual=partition.manual_count,
        )
        ttk.Label(self, text=summary, wraplength=640).pack(
            fill=tk.X, padx=12, pady=(12, 4)
        )
        ttk.Label(
            self,
            text=_tr(master, "map_hint"),
            wraplength=640,
        ).pack(fill=tk.X, padx=12, pady=(0, 6))

        if partition.auto_matched:
            auto_frame = ttk.LabelFrame(self, text=_tr(master, "map_auto_frame"))
            auto_frame.pack(fill=tk.X, padx=12, pady=4)
            preview = ", ".join(
                f"{name}→{info.label or info.machine_id}"
                for name, info in partition.auto_matched[:12]
            )
            if len(partition.auto_matched) > 12:
                preview += ", " + _tr(
                    master, "map_more", n=len(partition.auto_matched) - 12
                )
            ttk.Label(auto_frame, text=preview, wraplength=620).pack(
                fill=tk.X, padx=8, pady=6
            )

        outer = ttk.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor=tk.NW)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(inner, text=_tr(master, "map_col_folder")).grid(
            row=0, column=0, sticky=tk.W, padx=4, pady=2
        )
        ttk.Label(inner, text=_tr(master, "map_col_machine")).grid(
            row=0, column=1, sticky=tk.W, padx=4, pady=2
        )

        for i, folder in enumerate(partition.needs_manual, start=1):
            a = suggested.get(folder)
            mid = a.machine_id if a else UNKNOWN_ID
            label = a.label if a else UNKNOWN_LABEL
            initial = display_for_machine(mid, label)
            if initial not in self._choices:
                self._choices.append(initial)
            var = tk.StringVar(value=initial)
            self._vars[folder] = var
            ttk.Label(inner, text=folder).grid(row=i, column=0, sticky=tk.W, padx=4, pady=3)
            ttk.Combobox(
                inner,
                textvariable=var,
                values=self._choices,
                state="readonly",
                width=42,
            ).grid(row=i, column=1, sticky=tk.EW, padx=4, pady=3)
        inner.columnconfigure(1, weight=1)

        self._save_aliases_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self,
            text=_tr(master, "map_save_aliases_cb"),
            variable=self._save_aliases_var,
        ).pack(anchor=tk.W, padx=12, pady=(4, 0))

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btns, text=_tr(master, "cancel"), command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text=_tr(master, "map_save"), command=self._save).pack(
            side=tk.RIGHT, padx=8
        )

    def _save(self) -> None:
        out = FolderMachineMap()
        out.backup_root = self._suggested.backup_root or self._existing.backup_root
        # Keep previous real mappings + auto-matched as explicit map entries
        for folder, prev in self._partition.previously_mapped:
            out.set(folder, prev.machine_id, prev.label)
        for folder, info in self._partition.auto_matched:
            out.set(folder, info.machine_id, info.label)
        for folder, var in self._vars.items():
            mid, label = parse_machine_display(var.get())
            out.set(folder, mid, label)
            if self._save_aliases_var.get() and mid not in {UNKNOWN_ID, ""}:
                if not mid.startswith("unmapped:"):
                    self._aliases.add_local_alias(folder, mid, label=label)
        try:
            out.save(self._save_path)
        except OSError as exc:
            messagebox.showerror(_tr(self.master, "map_save"), str(exc), parent=self)
            return
        if self._save_aliases_var.get() and self._aliases.local_alias_count:
            try:
                self._aliases.save_local(self._local_aliases_path)
                self.aliases_saved = True
            except OSError as exc:
                messagebox.showerror(
                    _tr(self.master, "aliases_save_local"), str(exc), parent=self
                )
                return
        self.saved = True
        self.destroy()




class FolderColourAliasDialog(tk.Toplevel):
    """Manage folder roles + folder-name → role/exclude aliases."""

    def __init__(self, master: tk.Tk, *, save_path: Path) -> None:
        super().__init__(master)
        self.title(_tr(master, "folder_colours_dialog_title"))
        self.minsize(740, 520)
        self.geometry("820x560")
        self.transient(master)
        self.grab_set()
        self.saved = False
        self._save_path = Path(save_path)
        self._catalog = load_colour_catalog(self._save_path)
        self._lang = getattr(master, "_lang", None) or "pl"

        ttk.Label(
            self,
            text=_tr(master, "folder_colours_intro"),
            wraplength=740,
        ).pack(fill=tk.X, padx=12, pady=(12, 6))

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        self._tab_colours = ttk.Frame(nb, padding=6)
        self._tab_aliases = ttk.Frame(nb, padding=6)
        nb.add(self._tab_colours, text=_tr(master, "folder_colours_tab_colours"))
        nb.add(self._tab_aliases, text=_tr(master, "folder_colours_tab_aliases"))
        self._build_colours_tab()
        self._build_aliases_tab()

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=12, pady=8)
        ttk.Button(btns, text=_tr(master, "save"), command=self._save).pack(side=tk.RIGHT)
        ttk.Button(btns, text=_tr(master, "cancel"), command=self.destroy).pack(
            side=tk.RIGHT, padx=6
        )
        self._refresh_colour_list()
        self._refresh_alias_list()
        self._sync_alias_colour_choices()

    # --- colours tab ---------------------------------------------------------

    def _build_colours_tab(self) -> None:
        body = self._tab_colours
        body.rowconfigure(1, weight=1)
        body.columnconfigure(1, weight=1)

        explain = ttk.LabelFrame(
            body, text=_tr(self.master, "filter_status"), padding=6
        )
        explain.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        pack_status_legend(
            explain,
            on_machine_text=_tr(self.master, "status_on_machine"),
            not_run_text=_tr(self.master, "status_unknown"),
            explain_text=_tr(self.master, "folder_colour_status_explain"),
            wraplength=720,
        ).pack(fill=tk.X)

        left = ttk.Frame(body)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(0, weight=1)
        self._colour_list = tk.Listbox(left, exportselection=False, width=28)
        sb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self._colour_list.yview)
        self._colour_list.configure(yscrollcommand=sb.set)
        self._colour_list.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self._colour_list.bind("<<ListboxSelect>>", self._on_colour_select)
        cbtns = ttk.Frame(left)
        cbtns.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(cbtns, text=_tr(self.master, "folder_colour_add"), command=self._add_colour).pack(
            side=tk.LEFT
        )
        ttk.Button(
            cbtns, text=_tr(self.master, "folder_colour_remove"), command=self._remove_colour
        ).pack(side=tk.LEFT, padx=6)

        right = ttk.LabelFrame(body, text=_tr(self.master, "folder_colour_edit"), padding=6)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)
        self._cid_var = tk.StringVar()
        self._label_pl_var = tk.StringVar()
        self._label_en_var = tk.StringVar()
        self._swatch_var = tk.StringVar(value="#888888")
        self._badge_var = tk.StringVar(value="●")
        self._meaning_pl_var = tk.StringVar()
        self._meaning_en_var = tk.StringVar()

        rows = [
            ("folder_colour_id", self._cid_var),
            ("folder_colour_label_pl", self._label_pl_var),
            ("folder_colour_label_en", self._label_en_var),
        ]
        for i, (key, var) in enumerate(rows):
            ttk.Label(right, text=_tr(self.master, key)).grid(row=i, column=0, sticky=tk.W)
            state = "readonly" if key == "folder_colour_id" else "normal"
            ttk.Entry(right, textvariable=var, state=state).grid(
                row=i, column=1, sticky=tk.EW, padx=4, pady=2
            )

        # Colour: primary = clickable swatch + presets; hex is optional readout
        colour_row = 3
        ttk.Label(right, text=_tr(self.master, "folder_colour_swatch")).grid(
            row=colour_row, column=0, sticky=tk.NW, pady=(6, 0)
        )
        colour_box = ttk.Frame(right)
        colour_box.grid(row=colour_row, column=1, sticky=tk.EW, padx=4, pady=(4, 2))
        colour_box.columnconfigure(1, weight=1)

        self._swatch_preview = tk.Label(
            colour_box,
            text="    ",
            background="#888888",
            width=6,
            relief=tk.RAISED,
            bd=2,
            cursor="hand2",
        )
        self._swatch_preview.grid(row=0, column=0, padx=(0, 8), pady=2)
        self._swatch_preview.bind("<Button-1>", lambda _e: self._pick_swatch_colour())
        ttk.Button(
            colour_box,
            text=_tr(self.master, "folder_colour_pick"),
            command=self._pick_swatch_colour,
        ).grid(row=0, column=1, sticky=tk.W)

        ttk.Label(colour_box, text=_tr(self.master, "folder_colour_presets")).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=(6, 2)
        )
        palette = ttk.Frame(colour_box)
        palette.grid(row=2, column=0, columnspan=2, sticky=tk.W)
        for hex_col in COLOUR_PRESET_SWATCHES:
            chip = tk.Label(
                palette,
                text="  ",
                background=hex_col,
                width=3,
                relief=tk.RAISED,
                bd=1,
                cursor="hand2",
            )
            chip.pack(side=tk.LEFT, padx=2, pady=2)
            chip.bind(
                "<Button-1>",
                lambda _e, h=hex_col: self._set_swatch_colour(h),
            )

        hex_row = ttk.Frame(colour_box)
        hex_row.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(6, 0))
        ttk.Label(hex_row, text=_tr(self.master, "folder_colour_hex")).pack(side=tk.LEFT)
        ttk.Entry(hex_row, textvariable=self._swatch_var, width=12).pack(
            side=tk.LEFT, padx=6
        )

        ttk.Label(right, text=_tr(self.master, "folder_colour_badge")).grid(
            row=4, column=0, sticky=tk.W
        )
        ttk.Entry(right, textvariable=self._badge_var).grid(
            row=4, column=1, sticky=tk.EW, padx=4, pady=2
        )

        ttk.Label(right, text=_tr(self.master, "folder_colour_meaning_pl")).grid(
            row=5, column=0, sticky=tk.NW
        )
        self._meaning_pl = tk.Text(right, height=3, width=40, wrap=tk.WORD)
        self._meaning_pl.grid(row=5, column=1, sticky=tk.EW, padx=4, pady=2)
        ttk.Label(right, text=_tr(self.master, "folder_colour_meaning_en")).grid(
            row=6, column=0, sticky=tk.NW
        )
        self._meaning_en = tk.Text(right, height=3, width=40, wrap=tk.WORD)
        self._meaning_en.grid(row=6, column=1, sticky=tk.EW, padx=4, pady=2)
        ttk.Button(
            right, text=_tr(self.master, "folder_colour_update"), command=self._apply_colour_fields
        ).grid(row=7, column=1, sticky=tk.E, pady=(8, 0))
        self._swatch_var.trace_add("write", self._update_swatch_preview)

    def _set_swatch_colour(self, hex_colour: str) -> None:
        self._swatch_var.set(normalize_hex_colour(hex_colour))

    def _pick_swatch_colour(self) -> None:
        initial = normalize_hex_colour(self._swatch_var.get())
        try:
            _rgb, chosen = colorchooser.askcolor(
                color=initial,
                title=_tr(self.master, "folder_colour_pick_title"),
                parent=self,
            )
        except tk.TclError:
            return
        if chosen:
            self._set_swatch_colour(str(chosen))

    def _update_swatch_preview(self, *_a) -> None:
        sw = normalize_hex_colour(self._swatch_var.get())
        try:
            self._swatch_preview.configure(background=sw)
        except tk.TclError:
            self._swatch_preview.configure(background="#888888")

    def _colour_row_label(self, c: ColourDef) -> str:
        # Disc takes Listbox item foreground (swatch); avoid emoji glyphs.
        return f"{DOT}  {c.label(self._lang)}  ({c.id})"

    def _refresh_colour_list(self) -> None:
        self._colour_list.delete(0, tk.END)
        for c in self._catalog.colours:
            self._colour_list.insert(tk.END, self._colour_row_label(c))
            idx = self._colour_list.size() - 1
            try:
                self._colour_list.itemconfig(idx, foreground=c.swatch)
            except tk.TclError:
                pass

    def _on_colour_select(self, _evt=None) -> None:
        sel = self._colour_list.curselection()
        if not sel:
            return
        c = self._catalog.colours[int(sel[0])]
        self._cid_var.set(c.id)
        self._label_pl_var.set(c.label_pl)
        self._label_en_var.set(c.label_en)
        self._swatch_var.set(c.swatch)
        self._badge_var.set(c.badge)
        self._meaning_pl.delete("1.0", tk.END)
        self._meaning_pl.insert("1.0", c.meaning_pl)
        self._meaning_en.delete("1.0", tk.END)
        self._meaning_en.insert("1.0", c.meaning_en)

    def _apply_colour_fields(self) -> None:
        sel = self._colour_list.curselection()
        if not sel:
            return
        idx = int(sel[0])
        old = self._catalog.colours[idx]
        updated = ColourDef(
            id=old.id,
            label_pl=self._label_pl_var.get(),
            label_en=self._label_en_var.get(),
            swatch=normalize_hex_colour(self._swatch_var.get()),
            meaning_pl=self._meaning_pl.get("1.0", tk.END).strip(),
            meaning_en=self._meaning_en.get("1.0", tk.END).strip(),
            badge=self._badge_var.get(),
            builtin=old.builtin,
        )
        colours = list(self._catalog.colours)
        colours[idx] = updated
        self._catalog = ColourCatalog(colours=colours, rules=list(self._catalog.rules))
        self._refresh_colour_list()
        self._colour_list.selection_set(idx)
        self._sync_alias_colour_choices()

    def _add_colour(self) -> None:
        base = "custom"
        n = 1
        ids = self._catalog.colour_ids
        while f"{base}{n}" in ids:
            n += 1
        cid = f"{base}{n}"
        new = ColourDef(
            id=cid,
            label_pl=_tr(self.master, "folder_colour_new_label"),
            label_en="New role",
            swatch="#e67e22",
            meaning_pl="",
            meaning_en="",
            badge="●",
            builtin=False,
        )
        colours = list(self._catalog.colours) + [new]
        self._catalog = ColourCatalog(colours=colours, rules=list(self._catalog.rules))
        self._refresh_colour_list()
        self._colour_list.selection_clear(0, tk.END)
        self._colour_list.selection_set(tk.END)
        self._on_colour_select()
        self._sync_alias_colour_choices()

    def _remove_colour(self) -> None:
        sel = self._colour_list.curselection()
        if not sel:
            return
        c = self._catalog.colours[int(sel[0])]
        if c.builtin:
            messagebox.showinfo(
                _tr(self.master, "folder_colours"),
                _tr(self.master, "folder_colour_builtin_locked"),
            )
            return
        colours = [x for x in self._catalog.colours if x.id != c.id]
        # Remap aliases pointing at removed role → fixture seed
        rules = []
        for r in self._catalog.rules:
            if r.colour == c.id:
                rules.append(FolderColourRule(alias=r.alias, colour=ROLE_FIXTURE))
            else:
                rules.append(r)
        self._catalog = ColourCatalog(colours=colours, rules=rules)
        self._refresh_colour_list()
        self._refresh_alias_list()
        self._sync_alias_colour_choices()

    # --- aliases tab ---------------------------------------------------------

    def _build_aliases_tab(self) -> None:
        body = self._tab_aliases
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        list_frame = ttk.Frame(body)
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self._alias_list = tk.Listbox(list_frame, exportselection=False)
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._alias_list.yview)
        self._alias_list.configure(yscrollcommand=sb.set)
        self._alias_list.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self._alias_list.bind("<<ListboxSelect>>", self._on_alias_select)

        edit = ttk.Frame(body)
        edit.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        edit.columnconfigure(1, weight=1)
        ttk.Label(edit, text=_tr(self.master, "folder_colour_alias")).grid(
            row=0, column=0, sticky=tk.W
        )
        self._alias_var = tk.StringVar()
        ttk.Entry(edit, textvariable=self._alias_var).grid(
            row=0, column=1, sticky=tk.EW, padx=4, pady=2
        )
        ttk.Label(edit, text=_tr(self.master, "folder_colour_value")).grid(
            row=1, column=0, sticky=tk.W
        )
        self._alias_colour_var = tk.StringVar()
        self._alias_colour_combo = ttk.Combobox(
            edit, textvariable=self._alias_colour_var, state="readonly", width=40
        )
        self._alias_colour_combo.grid(row=1, column=1, sticky=tk.W, padx=4, pady=2)
        abtns = ttk.Frame(body)
        abtns.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            abtns, text=_tr(self.master, "folder_colour_add"), command=self._add_alias
        ).pack(side=tk.LEFT)
        ttk.Button(
            abtns, text=_tr(self.master, "folder_colour_update"), command=self._update_alias
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            abtns, text=_tr(self.master, "folder_colour_remove"), command=self._remove_alias
        ).pack(side=tk.LEFT, padx=6)

    def _alias_colour_choices(self) -> list[tuple[str, str]]:
        """Return (label, colour_id_or_exclude) pairs."""
        out = [(c.label(self._lang) + f" ({c.id})", c.id) for c in self._catalog.colours]
        out.append((_tr(self.master, "flag_exclude"), COLOUR_EXCLUDE))
        return out

    def _sync_alias_colour_choices(self) -> None:
        pairs = self._alias_colour_choices()
        self._alias_colour_labels = [p[0] for p in pairs]
        self._alias_colour_ids = [p[1] for p in pairs]
        self._alias_colour_combo["values"] = self._alias_colour_labels
        if not self._alias_colour_var.get() and self._alias_colour_labels:
            # default to red/personal seed if present
            for lab, cid in pairs:
                if cid == ROLE_PERSONAL:
                    self._alias_colour_var.set(lab)
                    break
            else:
                self._alias_colour_var.set(self._alias_colour_labels[0])

    def _label_for_colour_id(self, colour: str) -> str:
        if colour == COLOUR_EXCLUDE:
            return _tr(self.master, "flag_exclude")
        for lab, cid in self._alias_colour_choices():
            if cid == colour:
                return lab
        return colour

    def _colour_id_from_alias_label(self, label: str) -> str:
        for lab, cid in self._alias_colour_choices():
            if lab == label:
                return cid
        low = (label or "").casefold()
        if any(x in low for x in ("exclude", "pomiń", "pomin", "skip", "nie indeks")):
            return COLOUR_EXCLUDE
        return normalize_colour_id(label, known_ids=self._catalog.colour_ids)

    def _format_alias_row(self, rule: FolderColourRule) -> str:
        return f"{rule.alias}  →  {self._label_for_colour_id(rule.colour)}"

    def _refresh_alias_list(self) -> None:
        self._alias_list.delete(0, tk.END)
        for rule in self._catalog.rules:
            self._alias_list.insert(tk.END, self._format_alias_row(rule))

    def _on_alias_select(self, _evt=None) -> None:
        sel = self._alias_list.curselection()
        if not sel:
            return
        rule = self._catalog.rules[int(sel[0])]
        self._alias_var.set(rule.alias)
        self._alias_colour_var.set(self._label_for_colour_id(rule.colour))

    def _add_alias(self) -> None:
        alias = self._alias_var.get().strip()
        if not alias:
            return
        colour = self._colour_id_from_alias_label(self._alias_colour_var.get())
        rule = FolderColourRule(alias=alias, colour=colour)
        rules = [r for r in self._catalog.rules if r.key != rule.key]
        rules.append(rule)
        self._catalog = ColourCatalog(colours=list(self._catalog.colours), rules=rules)
        self._refresh_alias_list()

    def _update_alias(self) -> None:
        sel = self._alias_list.curselection()
        alias = self._alias_var.get().strip()
        if not alias:
            return
        colour = self._colour_id_from_alias_label(self._alias_colour_var.get())
        rule = FolderColourRule(alias=alias, colour=colour)
        rules = list(self._catalog.rules)
        if sel:
            idx = int(sel[0])
            rules = [r for i, r in enumerate(rules) if i != idx and r.key != rule.key]
            rules.insert(min(idx, len(rules)), rule)
        else:
            rules = [r for r in rules if r.key != rule.key]
            rules.append(rule)
        self._catalog = ColourCatalog(colours=list(self._catalog.colours), rules=rules)
        self._refresh_alias_list()

    def _remove_alias(self) -> None:
        sel = self._alias_list.curselection()
        if not sel:
            return
        idx = int(sel[0])
        rules = list(self._catalog.rules)
        del rules[idx]
        self._catalog = ColourCatalog(colours=list(self._catalog.colours), rules=rules)
        self._refresh_alias_list()
        self._alias_var.set("")

    def _save(self) -> None:
        self._apply_colour_fields()
        try:
            save_colour_catalog(self._save_path, self._catalog)
        except OSError as exc:
            messagebox.showerror(_tr(self.master, "folder_colours"), str(exc))
            return
        self.saved = True
        self.catalog = self._catalog
        self.destroy()


class AliasEditorDialog(tk.Toplevel):
    """Edit machines and their folder aliases (saved to aliases.local.yaml)."""

    def __init__(
        self,
        master: tk.Tk,
        *,
        aliases: AliasMap,
        save_path: Path,
    ) -> None:
        super().__init__(master)
        self.title(_tr(master, "aliases_dialog_title"))
        self.minsize(780, 480)
        self.geometry("900x560")
        self.transient(master)
        self.grab_set()
        self.saved = False
        self._aliases = aliases
        self._save_path = Path(save_path)
        self._dirty = False
        self._selected_mid: Optional[str] = None
        self._machine_order: list[str] = []
        # Guard: programmatic selection_set must not re-enter <<ListboxSelect>>
        self._selecting_machine = False
        # Staging: machine_id → {label, control_family, layout, local_aliases, …}
        self._draft: dict[str, dict[str, Any]] = {}
        # Snapshot of catalog meta at open (detect label/control/layout edits)
        self._orig_meta: dict[str, tuple[str, str, str]] = {}
        self._load_draft_from_aliases()

        ttk.Label(
            self,
            text=_tr(master, "aliases_intro"),
            wraplength=860,
        ).pack(fill=tk.X, padx=12, pady=(12, 6))

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        # --- Left: machines ----------------------------------------------------
        left = ttk.LabelFrame(body, text=_tr(master, "machines"), padding=6)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        mach_pane = ttk.Frame(left)
        mach_pane.grid(row=0, column=0, sticky="nsew")
        mach_pane.rowconfigure(0, weight=1)
        mach_pane.columnconfigure(0, weight=1)
        self._machine_list = tk.Listbox(mach_pane, exportselection=False)
        mach_sb = ttk.Scrollbar(
            mach_pane, orient=tk.VERTICAL, command=self._machine_list.yview
        )
        self._machine_list.configure(yscrollcommand=mach_sb.set)
        self._machine_list.grid(row=0, column=0, sticky="nsew")
        mach_sb.grid(row=0, column=1, sticky="ns")
        self._machine_list.bind("<<ListboxSelect>>", self._on_machine_selected)
        mach_btns = ttk.Frame(left)
        mach_btns.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(mach_btns, text=_tr(master, "alias_add_machine"), command=self._add_machine).pack(
            side=tk.LEFT
        )
        ttk.Button(
            mach_btns, text=_tr(master, "alias_remove_machine"), command=self._remove_machine
        ).pack(side=tk.LEFT, padx=6)

        # --- Right: details + aliases ------------------------------------------
        right = ttk.LabelFrame(body, text=_tr(master, "alias_selected_machine"), padding=6)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)
        right.rowconfigure(4, weight=1)

        ttk.Label(right, text=_tr(master, "alias_field_id")).grid(row=0, column=0, sticky=tk.W)
        self._mid_var = tk.StringVar()
        self._mid_entry = ttk.Entry(
            right, textvariable=self._mid_var, state="readonly"
        )
        self._mid_entry.grid(row=0, column=1, sticky=tk.EW, padx=4, pady=2)

        ttk.Label(right, text=_tr(master, "alias_field_label")).grid(row=1, column=0, sticky=tk.W)
        self._label_var = tk.StringVar()
        ttk.Entry(right, textvariable=self._label_var).grid(
            row=1, column=1, sticky=tk.EW, padx=4, pady=2
        )

        ttk.Label(right, text=_tr(master, "alias_field_control")).grid(row=2, column=0, sticky=tk.W)
        self._control_var = tk.StringVar()
        ttk.Combobox(
            right,
            textvariable=self._control_var,
            values=["", "haas", "fanuc", "sinumerik"],
            width=28,
        ).grid(row=2, column=1, sticky=tk.EW, padx=4, pady=2)

        ttk.Label(right, text=_tr(master, "alias_field_layout")).grid(row=3, column=0, sticky=tk.W)
        self._layout_var = tk.StringVar()
        ttk.Combobox(
            right,
            textvariable=self._layout_var,
            values=[
                "",
                "haas_pgm",
                "haas_ngc",
                "fanuc_all_fldr",
                "fanuc_all_prog",
                "manual_nc_folder",
            ],
            width=28,
        ).grid(row=3, column=1, sticky=tk.EW, padx=4, pady=2)

        alias_frame = ttk.LabelFrame(right, text=_tr(master, "alias_folder_aliases"), padding=4)
        alias_frame.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        alias_frame.rowconfigure(0, weight=1)
        alias_frame.columnconfigure(0, weight=1)
        alias_pane = ttk.Frame(alias_frame)
        alias_pane.grid(row=0, column=0, sticky="nsew")
        alias_pane.rowconfigure(0, weight=1)
        alias_pane.columnconfigure(0, weight=1)
        self._alias_list = tk.Listbox(alias_pane, exportselection=False)
        alias_sb = ttk.Scrollbar(
            alias_pane, orient=tk.VERTICAL, command=self._alias_list.yview
        )
        self._alias_list.configure(yscrollcommand=alias_sb.set)
        self._alias_list.grid(row=0, column=0, sticky="nsew")
        alias_sb.grid(row=0, column=1, sticky="ns")
        alias_btns = ttk.Frame(alias_frame)
        alias_btns.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(alias_btns, text=_tr(master, "alias_add"), command=self._add_alias).pack(
            side=tk.LEFT
        )
        ttk.Button(
            alias_btns, text=_tr(master, "alias_remove"), command=self._remove_alias
        ).pack(side=tk.LEFT, padx=6)
        ttk.Label(
            alias_btns,
            text=_tr(master, "alias_bundled_hint"),
            style="Muted.TLabel",
        ).pack(side=tk.LEFT, padx=8)

        ttk.Button(
            right, text=_tr(master, "alias_apply_details"), command=self._apply_machine_details
        ).grid(row=5, column=0, columnspan=2, sticky=tk.E, pady=(8, 0))

        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=12, pady=12)
        ttk.Label(footer, text=_tr(master, "alias_saves_to", path=self._save_path.name)).pack(side=tk.LEFT)
        ttk.Button(footer, text=_tr(master, "cancel"), command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(footer, text=_tr(master, "save"), command=self._save).pack(side=tk.RIGHT, padx=8)

        # Select first machine (if any) and show its details — do not clear
        # the detail pane afterward (that left highlight vs fields out of sync).
        self._reload_machine_list()

    # --- draft model -----------------------------------------------------------

    def _load_draft_from_aliases(self) -> None:
        self._draft.clear()
        self._orig_meta.clear()
        for row in self._aliases.machines_overview():
            mid = row["machine_id"]
            label = str(row.get("label") or "")
            control = str(row.get("control_family") or "")
            layout = str(row.get("layout") or "")
            self._draft[mid] = {
                "label": label,
                "control_family": control,
                "layout": layout,
                "local_aliases": list(row.get("local_aliases") or []),
                "bundled_aliases": list(row.get("bundled_aliases") or []),
                "local_only": bool(row.get("local_only")),
            }
            self._orig_meta[mid] = (label, control, layout)

    def _meta_changed(self, mid: str, row: dict[str, Any]) -> bool:
        cur = (
            str(row.get("label") or ""),
            str(row.get("control_family") or ""),
            str(row.get("layout") or ""),
        )
        return cur != self._orig_meta.get(mid, ("", "", ""))

    def _machine_display(self, mid: str) -> str:
        row = self._draft.get(mid) or {}
        lab = str(row.get("label") or "").strip()
        return f"{lab} ({mid})" if lab and lab != mid else mid

    def _reload_machine_list(self, *, select_mid: Optional[str] = None) -> None:
        keep = select_mid or self._selected_mid
        self._machine_list.delete(0, tk.END)
        self._machine_order = sorted(
            self._draft.keys(),
            key=lambda m: self._machine_display(m).casefold(),
        )
        select_idx = 0
        for i, mid in enumerate(self._machine_order):
            self._machine_list.insert(tk.END, self._machine_display(mid))
            if keep and mid == keep:
                select_idx = i
        # selection_set fires <<ListboxSelect>>; suppress re-entrant flush/reload
        self._selecting_machine = True
        try:
            if self._machine_order:
                self._machine_list.selection_clear(0, tk.END)
                self._machine_list.selection_set(select_idx)
                self._machine_list.activate(select_idx)
                self._machine_list.see(select_idx)
                self._selected_mid = self._machine_order[select_idx]
                self._fill_detail(self._selected_mid)
            else:
                self._selected_mid = None
                self._clear_detail()
        finally:
            self._selecting_machine = False

    def _clear_detail(self) -> None:
        self._mid_var.set("")
        self._label_var.set("")
        self._control_var.set("")
        self._layout_var.set("")
        self._alias_list.delete(0, tk.END)

    def _fill_detail(self, mid: str) -> None:
        row = self._draft.get(mid) or {}
        self._mid_var.set(mid)
        self._label_var.set(str(row.get("label") or ""))
        self._control_var.set(str(row.get("control_family") or ""))
        self._layout_var.set(str(row.get("layout") or ""))
        self._alias_list.delete(0, tk.END)
        for name in row.get("local_aliases") or []:
            self._alias_list.insert(tk.END, name)
        for name in row.get("bundled_aliases") or []:
            self._alias_list.insert(tk.END, f"{name}  [bundled]")

    def _flush_machine_fields(self, mid: str) -> bool:
        """Write label/control/layout from the detail pane into draft.

        Returns True when the display label changed (left list may need refresh
        / re-sort). Does not touch Listbox selection.
        """
        if mid not in self._draft:
            return False
        row = self._draft[mid]
        new_label = self._label_var.get().strip()
        new_control = self._control_var.get().strip()
        new_layout = self._layout_var.get().strip()
        old_label = str(row.get("label") or "")
        changed_meta = (
            old_label != new_label
            or str(row.get("control_family") or "") != new_control
            or str(row.get("layout") or "") != new_layout
        )
        if not changed_meta:
            return False
        row["label"] = new_label
        row["control_family"] = new_control
        row["layout"] = new_layout
        self._dirty = True
        return old_label != new_label

    def _on_machine_selected(self, _event: object = None) -> None:
        if self._selecting_machine:
            return
        sel = self._machine_list.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._machine_order):
            return
        new_mid = self._machine_order[idx]
        if new_mid == self._selected_mid:
            return
        prev = self._selected_mid
        label_changed = False
        # Detail pane still shows *prev* — flush it before switching.
        # Critical: do NOT call _apply_machine_details here; that reloaded the
        # list and re-selected ``prev``, pinning the highlight on the old row
        # (often the 2nd machine after the first successful click).
        if prev and prev in self._draft:
            label_changed = self._flush_machine_fields(prev)
        if label_changed:
            # Sort order may have changed — rebuild but keep the clicked row.
            self._selected_mid = new_mid
            self._reload_machine_list(select_mid=new_mid)
            return
        self._selected_mid = new_mid
        self._fill_detail(new_mid)

    def _apply_machine_details(self, silent: bool = False) -> None:
        mid = self._selected_mid or self._mid_var.get().strip()
        if not mid or mid not in self._draft:
            if not silent:
                messagebox.showinfo(
                    _tr(self.master, "machines"),
                    _tr(self.master, "alias_select_machine"),
                    parent=self,
                )
            return
        label_changed = self._flush_machine_fields(mid)
        # Explicit Apply always refreshes the left list; silent flush only when
        # the display string (sort key) may have changed.
        if label_changed or not silent:
            self._reload_machine_list(select_mid=mid)

    def _add_machine(self) -> None:
        form = MachineForm(self, title=_tr(self.master, "alias_add_machine_title"))
        self.wait_window(form)
        if not form.result:
            return
        mid, label, control, layout, alias = form.result
        if mid in self._draft:
            messagebox.showerror(
                _tr(self.master, "alias_add_machine_title"),
                _tr(self.master, "alias_id_exists", id=mid),
                parent=self,
            )
            return
        locals_: list[str] = []
        if alias:
            locals_.append(alias)
        self._draft[mid] = {
            "label": label,
            "control_family": control,
            "layout": layout,
            "local_aliases": locals_,
            "bundled_aliases": [],
            "local_only": True,
        }
        self._orig_meta[mid] = ("", "", "")  # new → any meta is a change
        self._dirty = True
        self._reload_machine_list(select_mid=mid)

    def _remove_machine(self) -> None:
        mid = self._selected_mid
        if not mid:
            messagebox.showinfo(
                _tr(self.master, "alias_remove_title"),
                _tr(self.master, "alias_select_machine"),
                parent=self,
            )
            return
        row = self._draft.get(mid) or {}
        has_bundled = bool(row.get("bundled_aliases"))
        name = self._machine_display(mid)
        if has_bundled:
            msg = _tr(self.master, "alias_remove_bundled_confirm", name=name)
        else:
            msg = _tr(self.master, "alias_remove_local_confirm", name=name)
        if not messagebox.askyesno(
            _tr(self.master, "alias_remove_title"), msg, parent=self
        ):
            return
        if has_bundled:
            row["local_aliases"] = []
            row["local_only"] = False
        else:
            del self._draft[mid]
            self._selected_mid = None
        self._dirty = True
        self._reload_machine_list()

    def _add_alias(self) -> None:
        mid = self._selected_mid
        if not mid:
            messagebox.showinfo(
                _tr(self.master, "alias_add_title"),
                _tr(self.master, "alias_select_machine"),
                parent=self,
            )
            return
        self._apply_machine_details(silent=True)
        name = simpledialog.askstring(
            _tr(self.master, "alias_add_title"),
            _tr(self.master, "alias_add_prompt"),
            parent=self,
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            return
        row = self._draft[mid]
        # Avoid duplicates (casefold / normalize-ish)
        existing = {a.casefold() for a in row["local_aliases"]}
        bundled = {a.casefold() for a in row["bundled_aliases"]}
        if name.casefold() in existing:
            messagebox.showinfo(
                _tr(self.master, "alias_add_title"),
                _tr(self.master, "alias_already_listed"),
                parent=self,
            )
            return
        if name.casefold() in bundled:
            # Promoting: store as local override of same spelling
            row["bundled_aliases"] = [
                a for a in row["bundled_aliases"] if a.casefold() != name.casefold()
            ]
        row["local_aliases"].append(name)
        row["local_aliases"] = sorted(row["local_aliases"], key=str.casefold)
        self._dirty = True
        self._fill_detail(mid)

    def _remove_alias(self) -> None:
        mid = self._selected_mid
        if not mid:
            return
        sel = self._alias_list.curselection()
        if not sel:
            messagebox.showinfo(
                _tr(self.master, "alias_remove_alias_title"),
                _tr(self.master, "alias_select_alias"),
                parent=self,
            )
            return
        raw = self._alias_list.get(sel[0])
        if " [bundled]" in raw:
            messagebox.showinfo(
                _tr(self.master, "alias_remove_alias_title"),
                _tr(self.master, "alias_cannot_remove_bundled"),
                parent=self,
            )
            return
        row = self._draft[mid]
        row["local_aliases"] = [a for a in row["local_aliases"] if a != raw]
        self._dirty = True
        self._fill_detail(mid)

    def _save(self) -> None:
        if self._selected_mid:
            self._apply_machine_details(silent=True)
        # Rebuild local overlay from draft
        # 1) Drop every current local alias
        for raw, _entry in list(self._aliases.list_local_aliases()):
            self._aliases.remove_local_alias(raw)
        # 2) Write draft local aliases (and meta) per machine
        for mid, row in self._draft.items():
            locals_ = list(row.get("local_aliases") or [])
            needs_seed = False
            if not locals_ and row.get("local_only"):
                # New / shop-only machine with no folder spelling yet — keep it
                # in the catalog by seeding the machine id as a folder key.
                needs_seed = True
            elif not locals_ and self._meta_changed(mid, row):
                # Bundled machine: persist label/control/layout via a seed key
                needs_seed = True
            elif not locals_:
                # Bundled-only, unchanged meta — nothing to write
                continue
            if needs_seed:
                locals_ = [mid]
            self._aliases.set_local_aliases_for_machine(
                mid,
                locals_,
                label=str(row.get("label") or "") or None,
                control_family=str(row.get("control_family") or "") or None,
                layout=str(row.get("layout") or "") or None,
            )
        try:
            self._aliases.save_local(self._save_path)
        except OSError as exc:
            messagebox.showerror(
                _tr(self.master, "alias_save_title"), str(exc), parent=self
            )
            return
        self.saved = True
        self._dirty = False
        self.destroy()


class MachineForm(tk.Toplevel):
    """Create a new machine id + display metadata (+ optional first alias)."""

    def __init__(self, master: tk.Toplevel, *, title: str | None = None) -> None:
        super().__init__(master)
        self.title(title or _tr(master, "alias_add_machine_title"))
        self.transient(master)
        self.grab_set()
        self.result: Optional[tuple[str, str, str, str, str]] = None

        body = ttk.Frame(self, padding=12)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text=_tr(master, "machine_form_id")).grid(
            row=0, column=0, sticky=tk.W
        )
        self.mid_var = tk.StringVar()
        ttk.Entry(body, textvariable=self.mid_var, width=40).grid(
            row=0, column=1, sticky=tk.EW, padx=6, pady=4
        )
        ttk.Label(body, text=_tr(master, "machine_form_label")).grid(
            row=1, column=0, sticky=tk.W
        )
        self.label_var = tk.StringVar()
        ttk.Entry(body, textvariable=self.label_var, width=40).grid(
            row=1, column=1, sticky=tk.EW, padx=6, pady=4
        )
        ttk.Label(body, text=_tr(master, "machine_form_control")).grid(
            row=2, column=0, sticky=tk.W
        )
        self.control_var = tk.StringVar()
        ttk.Combobox(
            body,
            textvariable=self.control_var,
            values=["", "haas", "fanuc", "sinumerik"],
            width=38,
        ).grid(row=2, column=1, sticky=tk.EW, padx=6, pady=4)
        ttk.Label(body, text=_tr(master, "machine_form_layout")).grid(
            row=3, column=0, sticky=tk.W
        )
        self.layout_var = tk.StringVar()
        ttk.Combobox(
            body,
            textvariable=self.layout_var,
            values=[
                "",
                "haas_pgm",
                "haas_ngc",
                "fanuc_all_fldr",
                "fanuc_all_prog",
                "manual_nc_folder",
            ],
            width=38,
        ).grid(row=3, column=1, sticky=tk.EW, padx=6, pady=4)
        ttk.Label(body, text=_tr(master, "machine_form_alias")).grid(
            row=4, column=0, sticky=tk.W
        )
        self.alias_var = tk.StringVar()
        ttk.Entry(body, textvariable=self.alias_var, width=40).grid(
            row=4, column=1, sticky=tk.EW, padx=6, pady=4
        )
        ttk.Label(
            body,
            text=_tr(master, "machine_form_alias_hint"),
            style="Muted.TLabel",
            wraplength=420,
        ).grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))
        body.columnconfigure(1, weight=1)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btns, text=_tr(master, "cancel"), command=self.destroy).pack(
            side=tk.RIGHT
        )
        ttk.Button(btns, text=_tr(master, "ok"), command=self._ok).pack(
            side=tk.RIGHT, padx=8
        )

    def _ok(self) -> None:
        mid = self.mid_var.get().strip()
        if not mid:
            messagebox.showerror(
                _tr(self.master, "machine_form_title"),
                _tr(self.master, "machine_id_required"),
                parent=self,
            )
            return
        if mid == "unknown" or mid.startswith("unmapped:"):
            messagebox.showerror(
                _tr(self.master, "machine_form_title"),
                _tr(self.master, "machine_id_reserved"),
                parent=self,
            )
            return
        # Normalize id a bit: spaces → dashes
        mid = mid.replace(" ", "-")
        self.result = (
            mid,
            self.label_var.get().strip(),
            self.control_var.get().strip(),
            self.layout_var.get().strip(),
            self.alias_var.get().strip(),
        )
        self.destroy()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    from gcode_index.single_instance import (
        signal_existing_instance,
        try_acquire,
        try_activate_existing_window,
    )

    guard = try_acquire()
    if guard is None:
        log.info("Another GUI instance is already running — activating it")
        signal_existing_instance()
        try_activate_existing_window(
            title_substrings=[
                "G-code Backup Indexer",
                "Indeksator kopii G-code",
            ]
        )
        return
    try:
        app = IndexerApp()
        guard.watch_activation(app._activate_from_second_launch)
        app.mainloop()
    finally:
        guard.release()


if __name__ == "__main__":
    main()
