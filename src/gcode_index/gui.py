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
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from gcode_index.aliases import (
    AliasMap,
    LOCAL_ALIASES_FILENAME,
    default_aliases_path,
    local_aliases_path_for_target,
)
from gcode_index.compare import (
    instance_label,
    preview_text,
    unified_diff_programs,
)
from gcode_index.db import (
    format_display_date,
    format_location,
    list_filter_values,
    open_db,
    query_instances,
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
from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA
from gcode_index.path_util import (
    format_eta,
    open_path_in_file_manager,
    resolve_source_abspath,
)
from gcode_index.instance_ini import (
    InstanceConfig,
    default_instance_ini_path,
    load_instance_ini,
    save_instance_ini,
)
from gcode_index.i18n import (
    DEFAULT_LANG,
    DEFAULT_UI_MODE,
    load_ui_settings,
    normalize_lang,
    normalize_ui_mode,
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
    SCHEDULE_CHOICES,
    SCHEDULE_DAILY,
    SCHEDULE_HOURLY,
    SCHEDULE_OFF,
    SCHEDULE_WEEKLY,
    format_iso_datetime,
    is_schedule_due,
    next_schedule_at,
    normalize_schedule,
    parse_iso_datetime,
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
from gcode_index.scanner import scan_backup_tree, scan_with_extra_roots
from gcode_index.ui_theme import (
    UI_ACCENT,
    UI_ACCENT_HOVER,
    UI_ACCENT_TEXT,
    UI_KEY_FG,
    UI_MUTED_FG,
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


class IndexerApp(tk.Tk):
    """Main window: backup + database + extract folders, scan, live search, extract."""

    def __init__(self) -> None:
        super().__init__()
        self.title("G-code Backup Indexer")
        self.minsize(1040, 700)
        self.geometry("1320x820")

        self.backup_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.extract_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.date_from_var = tk.StringVar()
        self.date_to_var = tk.StringVar()
        self.source_type_var = tk.StringVar(value=ALL)
        self.control_var = tk.StringVar(value=ALL)
        self.provenance_var = tk.StringVar(value=ALL)
        self.programmer_var = tk.StringVar(value=ALL)
        self.newest_only_var = tk.BooleanVar(value=False)
        self.incremental_var = tk.BooleanVar(value=True)
        self.excel_var = tk.BooleanVar(value=True)
        self.lang_var = tk.StringVar(value=DEFAULT_LANG)
        self.ui_mode_var = tk.StringVar(value="")
        self.schedule_var = tk.StringVar(value=SCHEDULE_OFF)
        self.schedule_status_var = tk.StringVar(value="")
        self.preset_var = tk.StringVar(value="")
        self.preview_header_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_label_var = tk.StringVar(value="")

        self._search_after_id: Optional[str] = None
        self._schedule_after_id: Optional[str] = None
        self._result_rows: list = []
        self._scan_busy = False
        self._filter_trace_lock = False
        self._machine_names: list[str] = []
        self._last_scan_report: Optional[ScanReport] = None
        self._root_frame: Optional[ttk.Frame] = None
        self._lang = DEFAULT_LANG
        self._ui_mode = DEFAULT_UI_MODE
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

        self._apply_instance_ini(load_instance_ini(self._instance_ini_path))
        self._configure_styles()
        self._build()
        # Seed machine list from aliases before any scan
        self._refresh_filter_choices()
        self._maybe_auto_collapse_folders()
        self._arm_schedule_timer()
        if self._folders_ready():
            self.status_var.set(
                self._(
                    "status_loaded_ini",
                    filename=self._instance_ini_path.name,
                )
            )
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.search_var.trace_add("write", self._on_filter_changed)
        for var in (
            self.date_from_var,
            self.date_to_var,
            self.source_type_var,
            self.control_var,
            self.provenance_var,
            self.programmer_var,
            self.newest_only_var,
        ):
            var.trace_add("write", self._on_filter_changed)
        # Persist folder edits typed by hand (debounced)
        self.backup_var.trace_add("write", self._on_folder_path_changed)
        self.target_var.trace_add("write", self._on_folder_path_changed)
        self.extract_var.trace_add("write", self._on_folder_path_changed)
        self._folder_save_after_id: Optional[str] = None

    def _(self, key: str, **kwargs) -> str:
        return t(self._lang, key, **kwargs)

    def _apply_instance_ini(self, cfg: InstanceConfig) -> None:
        """Load last session paths/settings before the first widget build."""
        self._lang = normalize_lang(cfg.language)
        self._ui_mode = normalize_ui_mode(cfg.ui_mode)
        self.lang_var.set(self._lang)
        self._schedule = normalize_schedule(cfg.schedule)
        self._schedule_last_run = cfg.schedule_last_run or None
        self.schedule_var.set(self._schedule)
        self.backup_var.set(cfg.backup or "")
        self.target_var.set(cfg.target or "")
        self.extract_var.set(cfg.extract or "")
        self.incremental_var.set(bool(cfg.incremental))
        self.excel_var.set(bool(cfg.also_excel))
        self.newest_only_var.set(bool(cfg.newest_only))
        self._hidden_root_specs = list(cfg.root_specs())
        self._ini_notes = cfg.notes or ""
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
            ui_mode=self._ui_mode,
            schedule=self._schedule,
            schedule_last_run=self._schedule_last_run or "",
            incremental=bool(self.incremental_var.get()),
            also_excel=bool(self.excel_var.get()),
            newest_only=bool(self.newest_only_var.get()),
            geometry=geom,
            notes=self._ini_notes,
        )

    def _save_instance_ini(self) -> None:
        try:
            save_instance_ini(self._instance_ini_path, config=self._collect_instance_config())
        except OSError:
            log.exception("save instance ini failed: %s", self._instance_ini_path)

    def _on_folder_path_changed(self, *_args) -> None:
        if getattr(self, "_folder_save_after_id", None):
            try:
                self.after_cancel(self._folder_save_after_id)
            except tk.TclError:
                pass
        self._folder_save_after_id = self.after(800, self._save_instance_ini)

    def _on_close(self) -> None:
        self._save_instance_ini()
        self.destroy()

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
        return self._ui_mode == "simple"

    def _mode_label(self, mode: str) -> str:
        return self._("mode_simple") if normalize_ui_mode(mode) == "simple" else self._("mode_full")

    def _mode_from_label(self, label: str) -> str:
        raw = (label or "").strip()
        if raw == self._("mode_simple"):
            return "simple"
        if raw == self._("mode_full"):
            return "full"
        return normalize_ui_mode(raw)

    def _snapshot_ui(self) -> dict:
        return {
            "backup": self.backup_var.get(),
            "target": self.target_var.get(),
            "extract": self.extract_var.get(),
            "search": self.search_var.get(),
            "date_from": self.date_from_var.get(),
            "date_to": self.date_to_var.get(),
            "source_type": self.source_type_var.get(),
            "control": self.control_var.get(),
            "provenance": self.provenance_var.get(),
            "programmer": self.programmer_var.get(),
            "newest": bool(self.newest_only_var.get()),
            "incremental": bool(self.incremental_var.get()),
            "excel": bool(self.excel_var.get()),
            "machines": self._selected_machines(),
            "roots": list(self._scan_root_specs()),
            "folders_expanded": bool(self._folders_expanded),
            "more_filters": bool(self._more_filters_open),
            "schedule": self._schedule,
        }

    def _persist_ui_settings(self, target: Optional[str] = None) -> None:
        dest = (target if target is not None else self.target_var.get()).strip()
        if dest:
            try:
                save_ui_settings(
                    ui_settings_path_for_target(dest),
                    language=self._lang,
                    ui_mode=self._ui_mode,
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

    def _set_ui_mode(self, mode: str, *, persist: bool = True) -> None:
        code = normalize_ui_mode(mode)
        if code == self._ui_mode and self._root_frame is not None:
            return
        preserved = self._snapshot_ui()
        self._ui_mode = code
        self.ui_mode_var.set(self._mode_label(code))
        if persist:
            self._persist_ui_settings(preserved["target"])
        self._rebuild(preserved)
        # Prosty is retrieve-only — never run scheduled scans while in that mode.
        self._arm_schedule_timer()

    def _on_ui_mode_selected(self, *_args) -> None:
        self._set_ui_mode(self._mode_from_label(self.ui_mode_var.get()))

    def _rebuild(self, preserved: Optional[dict] = None) -> None:
        if self._root_frame is not None:
            self._root_frame.destroy()
            self._root_frame = None
        self._build()
        if preserved:
            self.backup_var.set(preserved.get("backup") or "")
            self.target_var.set(preserved.get("target") or "")
            self.extract_var.set(preserved.get("extract") or "")
            self.search_var.set(preserved.get("search") or "")
            self.date_from_var.set(preserved.get("date_from") or "")
            self.date_to_var.set(preserved.get("date_to") or "")
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
            low = prov.casefold()
            if any(x in low for x in ("yellow", "żółt", "zoltt", "extra", "dodatk")):
                self.provenance_var.set(self._("flag_yellow"))
            elif any(x in low for x in ("green", "zielon", "backup", "kopi")):
                self.provenance_var.set(self._("flag_green"))
            else:
                self.provenance_var.set(self._all_token())
            self.newest_only_var.set(bool(preserved.get("newest")))
            self.incremental_var.set(bool(preserved.get("incremental", True)))
            self.excel_var.set(bool(preserved.get("excel", True)))
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
        self._run_query_now()

    def _short_path(self, path: str, *, maxlen: int = 42) -> str:
        raw = (path or "").strip()
        if not raw:
            return self._("path_unset")
        if len(raw) <= maxlen:
            return raw
        return "…" + raw[-(maxlen - 1) :]

    def _folders_ready(self) -> bool:
        # Prosty (retrieve-only): target/DB folder is enough; backup is optional for extract.
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
                        backup=self._short_path(bak) if bak else unset,
                        target=self._short_path(tgt),
                        extract=extract_disp,
                    )
                )
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

    def _extract_dir(self) -> str:
        """Resolved extract output folder (explicit extract, else database/target)."""
        return self.extract_var.get().strip() or self.target_var.get().strip()

    def _set_folders_expanded(self, expanded: bool, *, persist: bool = True) -> None:
        self._folders_expanded = bool(expanded)
        if not hasattr(self, "_folders_expanded_frame"):
            return
        before = getattr(self, "_actions_frame", None)
        pack_opts: dict = {"fill": tk.X, "padx": 8, "pady": 4}
        if before is not None and before.winfo_exists():
            pack_opts["before"] = before
        if self._folders_expanded:
            self._folders_summary_frame.pack_forget()
            self._folders_expanded_frame.pack(**pack_opts)
        else:
            self._folders_expanded_frame.pack_forget()
            self._update_folders_summary()
            self._folders_summary_frame.pack(**pack_opts)

    def _maybe_auto_collapse_folders(self) -> None:
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
                # Pack just above the find bar if possible
                if hasattr(self, "filt_frame") and self.filt_frame.winfo_ismapped():
                    self.prog_frame.pack(
                        fill=tk.X, padx=8, pady=4, before=self.filt_frame
                    )
                else:
                    self.prog_frame.pack(fill=tk.X, padx=8, pady=4)
        else:
            self.prog_frame.pack_forget()

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        simple = self._is_simple()
        self.title(self._("app_title"))
        self.ui_mode_var.set(self._mode_label(self._ui_mode))
        self._update_machines_button()
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)
        self._root_frame = root

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

        # --- Folders: collapsed summary OR expanded editors -------------------------
        self._folders_summary_frame = ttk.Frame(root)
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
            root,
            text=(
                self._("folders_step_simple") if simple else self._("folders")
            ),
            padding=8,
            style="Primary.TLabelframe",
        )
        paths = self._folders_expanded_frame
        ttk.Label(
            paths,
            text=(
                self._("backup_folder_optional") if simple else self._("backup_folder")
            ),
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
            text=(
                self._("target_folder_simple") if simple else self._("target_folder")
            ),
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
        paths.columnconfigure(1, weight=1)

        # Additional folders (green catch + yellow extras) — Full mode only
        if not simple:
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
        elif hasattr(self, "extra_list"):
            delattr(self, "extra_list")

        done_row = ttk.Frame(paths)
        done_row.grid(
            row=5 if not simple else 4,
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

        # --- Actions ---------------------------------------------------------------
        actions = ttk.Frame(root)
        self._actions_frame = actions
        actions.pack(fill=tk.X, **pad)

        settings = ttk.Frame(actions)
        settings.pack(side=tk.RIGHT)
        if not simple:
            ttk.Label(settings, text=self._("schedule"), style="Muted.TLabel").pack(
                side=tk.LEFT, padx=(0, 2)
            )
            self.schedule_var.set(self._schedule_label(self._schedule))
            sched_combo = ttk.Combobox(
                settings,
                textvariable=self.schedule_var,
                values=[self._schedule_label(c) for c in SCHEDULE_CHOICES],
                state="readonly",
                width=14,
            )
            sched_combo.pack(side=tk.LEFT)
            sched_combo.bind("<<ComboboxSelected>>", self._on_schedule_selected)
            ttk.Label(
                settings, textvariable=self.schedule_status_var, style="Muted.TLabel"
            ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(settings, text=self._("language"), style="Muted.TLabel").pack(
            side=tk.LEFT, padx=(12 if not simple else 0, 2)
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
        ttk.Label(settings, text=self._("ui_mode"), style="Muted.TLabel").pack(
            side=tk.LEFT, padx=(12, 2)
        )
        mode_combo = ttk.Combobox(
            settings,
            textvariable=self.ui_mode_var,
            values=[self._("mode_simple"), self._("mode_full")],
            state="readonly",
            width=10,
        )
        mode_combo.pack(side=tk.LEFT)
        mode_combo.bind("<<ComboboxSelected>>", self._on_ui_mode_selected)
        if not simple:
            self._update_schedule_status()

        if simple:
            # Retrieve-only: Open DB is the primary CTA; no scan / index.
            self.scan_btn = None
            self.open_db_btn = self._make_primary_button(
                actions, self._("open_db"), self._pick_existing_db
            )
            self.open_db_btn.pack(side=tk.LEFT)
            ttk.Button(
                actions, text=self._("clear_filters"), command=self._clear_filters
            ).pack(side=tk.LEFT, padx=8)
        else:
            self.scan_btn = self._make_primary_button(
                actions, self._("run_scan"), self._start_scan
            )
            self.scan_btn.pack(side=tk.LEFT)
            ttk.Button(
                actions, text=self._("map_folders"), command=self._open_folder_map
            ).pack(side=tk.LEFT, padx=8)
            ttk.Button(
                actions, text=self._("aliases"), command=self._open_alias_editor
            ).pack(side=tk.LEFT, padx=4)
            ttk.Button(
                actions, text=self._("open_db"), command=self._pick_existing_db
            ).pack(side=tk.LEFT, padx=8)
            ttk.Button(
                actions, text=self._("scan_report"), command=self._open_scan_report
            ).pack(side=tk.LEFT, padx=4)
            ttk.Button(
                actions, text=self._("duplicates"), command=self._open_duplicates
            ).pack(side=tk.LEFT, padx=4)
            ttk.Button(
                actions, text=self._("clear_filters"), command=self._clear_filters
            ).pack(side=tk.LEFT, padx=4)
            ttk.Checkbutton(
                actions, text=self._("also_excel"), variable=self.excel_var
            ).pack(side=tk.LEFT)
            ttk.Checkbutton(
                actions, text=self._("incremental"), variable=self.incremental_var
            ).pack(side=tk.LEFT, padx=8)

        # Progress — hidden until a scan runs
        self.prog_frame = ttk.Frame(root)
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

        # --- Compact find bar ------------------------------------------------------
        find_title = self._("find_programs_step") if simple else self._("find_programs")
        self.filt_frame = ttk.LabelFrame(
            root, text=find_title, padding=8, style="Primary.TLabelframe"
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
        ttk.Entry(filt, textvariable=self.date_from_var, width=11).grid(
            row=0, column=4, sticky=tk.W
        )
        ttk.Label(filt, text=self._("date_to_sep")).grid(row=0, column=5, sticky=tk.W)
        ttk.Entry(filt, textvariable=self.date_to_var, width=11).grid(
            row=0, column=6, sticky=tk.W
        )
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

            ttk.Label(adv, text=self._("flag")).grid(
                row=0, column=4, sticky=tk.W, padx=(12, 0), pady=2
            )
            self.provenance_combo = ttk.Combobox(
                adv,
                textvariable=self.provenance_var,
                values=[
                    self._all_token(),
                    self._("flag_green"),
                    self._("flag_yellow"),
                ],
                state="readonly",
                width=28,
            )
            self.provenance_combo.grid(row=0, column=5, sticky=tk.W, padx=4, pady=2)

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
            preset_row.grid(row=1, column=3, columnspan=3, sticky=tk.W, padx=4, pady=2)
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
            self._apply_more_filters_visibility()
        else:
            for attr in (
                "type_combo",
                "control_combo",
                "provenance_combo",
                "programmer_combo",
                "preset_combo",
                "_more_filters_frame",
                "_more_filters_btn",
            ):
                if hasattr(self, attr):
                    delattr(self, attr)

        # --- Results: table | preview side-by-side (C) -----------------------------
        cols = (
            "flag",
            "program",
            "part",
            "programmer",
            "machine",
            "date",
            "type",
            "control",
            "path",
            "location",
        )
        results_pane = ttk.Panedwindow(root, orient=tk.HORIZONTAL)
        results_pane.pack(fill=tk.BOTH, expand=True, **pad)

        tree_frame = ttk.Frame(results_pane)
        results_pane.add(tree_frame, weight=3)
        self.tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings", selectmode="extended"
        )
        headings = {
            "flag": (self._("col_flag"), 56),
            "program": (self._("col_program"), 90),
            "part": (self._("col_part"), 130),
            "programmer": (self._("col_programmer"), 56),
            "machine": (self._("col_machine"), 110),
            "date": (self._("col_date"), 100),
            "type": (self._("col_type"), 100),
            "control": (self._("col_control"), 70),
            "path": (self._("col_path"), 240),
            "location": (self._("col_location"), 120),
        }
        for key, (label, width) in headings.items():
            self.tree.heading(key, text=label)
            stretch = key in ("path", "part")
            self.tree.column(key, width=width, stretch=stretch, minwidth=40)
        self.tree.tag_configure("flag_backup", foreground="#1a7f37")
        self.tree.tag_configure("flag_extra", foreground="#b58900")
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
        prev_inner = ttk.Frame(preview_frame)
        prev_inner.pack(fill=tk.BOTH, expand=True)
        self.preview_text = tk.Text(
            prev_inner,
            wrap=tk.NONE,
            height=10,
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

        status = ttk.Label(root, textvariable=self.status_var, anchor=tk.W)
        status.pack(fill=tk.X, **pad)

    # --- paths ------------------------------------------------------------------

    def _pick_backup(self) -> None:
        path = filedialog.askdirectory(title="Select CNC backup folder")
        if path:
            self.backup_var.set(path)
            self._update_folders_summary()
            self._maybe_auto_collapse_folders()
            self._save_instance_ini()

    def _pick_target(self) -> None:
        path = filedialog.askdirectory(title=self._("target_folder"))
        if path:
            self.target_var.set(path)
            self._load_extra_roots_into_list()
            self._refresh_preset_combo()
            self._update_folders_summary()
            settings = load_ui_settings(ui_settings_path_for_target(path))
            lang = settings["language"]
            mode = settings["ui_mode"]
            self._schedule_last_run = settings.get("schedule_last_run") or None
            self._set_schedule(settings.get("schedule") or SCHEDULE_OFF, persist=False)
            if lang != self._lang or mode != self._ui_mode:
                preserved = self._snapshot_ui()
                preserved["target"] = path
                preserved["folders_expanded"] = False
                preserved["schedule"] = self._schedule
                self._lang = lang
                self._ui_mode = mode
                self.lang_var.set(lang)
                self.ui_mode_var.set(self._mode_label(mode))
                self._rebuild(preserved)
            else:
                self._persist_ui_settings(path)
                self._maybe_auto_collapse_folders()

    def _pick_extract(self) -> None:
        path = filedialog.askdirectory(title=self._("extract_folder"))
        if path:
            self.extract_var.set(path)
            self._update_folders_summary()
            self._maybe_auto_collapse_folders()
            self._save_instance_ini()

    def _pick_existing_db(self) -> None:
        path = filedialog.askopenfilename(
            title=self._("open_db"),
            filetypes=[("SQLite", "*.sqlite *.db"), ("All", "*.*")],
        )
        if not path:
            return
        db = Path(path)
        self.target_var.set(str(db.parent))
        self._load_extra_roots_into_list()
        self.status_var.set(f"Using existing DB: {db}")
        self._refresh_filter_choices()
        self._clear_filters()
        self._update_folders_summary()
        self._maybe_auto_collapse_folders()
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
                        "That folder is already the main backup root.",
                    )
                    return
            except OSError:
                pass
        if resolved.casefold() in existing or path.casefold() in existing:
            messagebox.showinfo(
                self._("extra_folders"), "That folder is already in the list."
            )
            return
        specs = self._scan_root_specs()
        specs.append(ScanRootSpec(path=resolved, provenance=provenance))
        self._fill_extra_list(specs)
        self._persist_extra_roots()

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

    def _schedule_label(self, code: str) -> str:
        key = {
            SCHEDULE_OFF: "schedule_off",
            SCHEDULE_HOURLY: "schedule_hourly",
            SCHEDULE_DAILY: "schedule_daily",
            SCHEDULE_WEEKLY: "schedule_weekly",
        }.get(normalize_schedule(code), "schedule_off")
        return self._(key)

    def _schedule_from_label(self, label: str) -> str:
        raw = (label or "").strip()
        for code in SCHEDULE_CHOICES:
            if raw == self._schedule_label(code):
                return code
        return normalize_schedule(raw)

    def _on_schedule_selected(self, *_args) -> None:
        self._set_schedule(self._schedule_from_label(self.schedule_var.get()))

    def _set_schedule(self, schedule: str, *, persist: bool = True) -> None:
        code = normalize_schedule(schedule)
        self._schedule = code
        self.schedule_var.set(self._schedule_label(code))
        if persist:
            self._persist_ui_settings()
        self._update_schedule_status()
        self._arm_schedule_timer()

    def _update_schedule_status(self) -> None:
        if not hasattr(self, "schedule_status_var"):
            return
        if self._schedule == SCHEDULE_OFF:
            self.schedule_status_var.set(self._("schedule_idle"))
            return
        nxt = next_schedule_at(self._schedule, self._schedule_last_run)
        if nxt is None:
            self.schedule_status_var.set(self._("schedule_idle"))
            return
        local = nxt.astimezone().strftime("%Y-%m-%d %H:%M")
        self.schedule_status_var.set(self._("schedule_next", when=local))

    def _arm_schedule_timer(self) -> None:
        if self._schedule_after_id is not None:
            try:
                self.after_cancel(self._schedule_after_id)
            except tk.TclError:
                pass
            self._schedule_after_id = None
        # Prosty is retrieve-only — no auto-index timer.
        if self._is_simple():
            return
        # Check every 30s while a schedule is armed
        if self._schedule != SCHEDULE_OFF:
            self._schedule_after_id = self.after(30_000, self._schedule_tick)

    def _schedule_tick(self) -> None:
        self._schedule_after_id = None
        try:
            self._maybe_run_scheduled_scan()
        finally:
            self._arm_schedule_timer()
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
        self._start_scan(auto=True)

    def _mark_schedule_ran(self) -> None:
        from datetime import datetime, timezone

        self._schedule_last_run = format_iso_datetime(datetime.now(timezone.utc))
        self._persist_ui_settings()
        self._update_schedule_status()

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
            messagebox.showerror("Backup folder", "Choose a valid backup folder first.")
            return
        if not target:
            messagebox.showerror(
                "Target folder",
                "Choose a target folder (map + local aliases are saved next to the database).",
            )
            return
        Path(target).mkdir(parents=True, exist_ok=True)
        try:
            aliases = self._load_alias_map()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Aliases", str(exc))
            return
        folders = discover_machine_folders(backup)
        if not folders:
            messagebox.showinfo(
                "Map folders",
                "No date/machine folders found under the backup root.\n"
                "Expected layout: <date>/<machine>/…",
            )
            return
        existing = self._load_folder_map()
        part = partition_folders(folders, aliases, existing)
        if not part.needs_manual:
            auto_n = part.auto_count
            prev_n = len(part.previously_mapped)
            messagebox.showinfo(
                "Map folders",
                f"All machine folders are already connected.\n\n"
                f"Auto-matched via aliases: {auto_n}\n"
                f"Previously mapped: {prev_n}\n\n"
                f"Nothing left for manual mapping.",
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
            bits = [f"Saved folder map → {map_path_for_target(target).name}"]
            if dlg.aliases_saved:
                bits.append(f"local aliases → {LOCAL_ALIASES_FILENAME}")
            self.status_var.set("; ".join(bits))

    def _open_alias_editor(self) -> None:
        target = self.target_var.get().strip()
        if not target:
            messagebox.showerror(
                "Target folder",
                "Choose a target folder first.\n"
                f"Local aliases are saved as {LOCAL_ALIASES_FILENAME} next to the database.",
            )
            return
        Path(target).mkdir(parents=True, exist_ok=True)
        try:
            aliases = self._load_alias_map()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Aliases", str(exc))
            return
        dlg = AliasEditorDialog(
            self,
            aliases=aliases,
            save_path=local_aliases_path_for_target(target),
        )
        self.wait_window(dlg)
        if dlg.saved:
            self.status_var.set(f"Saved local aliases → {LOCAL_ALIASES_FILENAME}")
            self._refresh_filter_choices()

    # --- scan -------------------------------------------------------------------

    def _start_scan(self, auto: bool = False) -> None:
        if self._scan_busy:
            return
        # Prosty is retrieve-only — indexing lives in Full mode.
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
                messagebox.showerror("Backup folder", "Choose a valid backup folder.")
            return
        if not target:
            if not auto:
                messagebox.showerror("Target folder", "Choose a target folder for the database.")
            return
        Path(target).mkdir(parents=True, exist_ok=True)
        self._persist_ui_settings(target)
        # Offer mapper only in Full mode (manual) when unmatched folders remain
        if not auto and not self._is_simple():
            try:
                aliases = self._load_alias_map()
                folders = discover_machine_folders(backup)
                part = partition_folders(folders, aliases, self._load_folder_map())
            except Exception:  # noqa: BLE001
                log.exception("folder partition before scan failed")
                part = None
            if part is not None and part.needs_manual:
                prompt = (
                    f"{part.manual_count} folder(s) could not be matched automatically "
                    f"({part.auto_count} auto-matched via aliases).\n\n"
                    "Open the mapper to assign only the unmatched folders?"
                )
                if messagebox.askyesno("Map folders", prompt):
                    self._open_folder_map()
        self._scan_busy = True
        self._set_primary_button_enabled(self.scan_btn, False)
        self.progress_var.set(0.0)
        self.progress_label_var.set("Starting…")
        self.status_var.set(
            self._("schedule_running") if auto else "Scanning…"
        )
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
            self.progress_label_var.set(message or "Counting…")
            self.status_var.set(message or "Counting source files…")
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
            aliases_path = default_aliases_path()
            local_path = local_aliases_path_for_target(target)
            alias_map = AliasMap.load_merged(aliases_path, local_path)
            folder_map = FolderMachineMap.load(map_path_for_target(target))
            fmap = folder_map if folder_map.assignments else None
            db_path = target / DEFAULT_DB_NAME
            cache = None
            n_cached = 0
            if incremental and db_path.is_file():
                try:
                    prior = open_db(db_path)
                    try:
                        cache = load_scan_cache(prior)
                    finally:
                        prior.close()
                except Exception:  # noqa: BLE001
                    log.exception("load scan cache failed; falling back to full scan")
                    cache = None
            if root_specs:
                result = scan_with_extra_roots(
                    backup,
                    alias_map,
                    root_specs=root_specs,
                    progress=self._on_scan_progress,
                    folder_map=fmap,
                    cache=cache,
                )
            else:
                result = scan_backup_tree(
                    backup,
                    alias_map,
                    progress=self._on_scan_progress,
                    folder_map=fmap,
                    provenance=PROVENANCE_BACKUP,
                    cache=cache,
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
            conn.close()
            excel_note = ""
            if write_excel:
                xlsx = target / "gcode_index.xlsx"
                export_excel(xlsx, result.instances)
                excel_note = f"; Excel → {xlsx.name}"
            unk_note = (
                f"; {unknown_prog} MACHINE UNKNOWN programs"
                if unknown_prog
                else "; 0 MACHINE UNKNOWN programs"
            )
            local_note = (
                f"; +{alias_map.local_alias_count} local aliases"
                if alias_map.local_alias_count
                else ""
            )
            flag_note = f"; flags green={n_green} yellow={n_yellow}"
            cache_note = f"; reused {n_cached} unchanged files" if n_cached else ""
            mode_note = "; incremental" if cache is not None else "; full scan"
            auto_note = "; auto" if auto else ""
            msg = (
                f"Indexed {len(result.instances)} programs "
                f"[{type_note}] "
                f"({len(result.unknowns)} unknown folders{unk_note}{local_note}"
                f"{flag_note}{cache_note}{mode_note}{auto_note}) "
                f"→ {db_path.name} "
                f"(run {run_id[:8]}…){excel_note}"
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
            self.progress_label_var.set("Done")
            self._mark_schedule_ran()
        else:
            self.progress_var.set(0.0)
            self.progress_label_var.set("")
        self.status_var.set(message)
        # Hide progress bar shortly after finish to free vertical space
        self.after(1200, lambda: self._show_progress(False) if not self._scan_busy else None)
        if not ok:
            if not auto:
                messagebox.showerror("Scan failed", message)
            return
        if report is not None:
            self._last_scan_report = report
        self._refresh_filter_choices()
        self._clear_filters(status_prefix=message)
        if report is not None and not self._is_simple() and not auto:
            self._show_scan_report(report)

    def _open_scan_report(self) -> None:
        report = self._last_scan_report
        if report is None:
            db_path = self._db_path()
            if db_path is None or not db_path.is_file():
                messagebox.showinfo(
                    "Scan report",
                    "No database yet — run a scan or open an existing DB first.",
                )
                return
            try:
                conn = open_db(db_path)
                try:
                    report = load_scan_report(conn)
                finally:
                    conn.close()
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Scan report", str(exc))
                return
        if report is None:
            messagebox.showinfo("Scan report", "No completed scan found in this database.")
            return
        self._last_scan_report = report
        self._show_scan_report(report)

    def _show_scan_report(self, report: ScanReport) -> None:
        ScanReportDialog(self, report=report)

    def _open_duplicates(self) -> None:
        db_path = self._db_path()
        if db_path is None or not db_path.is_file():
            messagebox.showinfo(
                "Duplicates",
                "No database yet — run a scan or open an existing DB first.",
            )
            return
        try:
            conn = open_db(db_path)
            try:
                groups = find_duplicate_groups(conn)
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Duplicates", str(exc))
            return
        if not groups:
            messagebox.showinfo(
                "Duplicates",
                "No exact or near-duplicates found in this index.",
            )
            return
        dlg = DuplicatesDialog(self, groups=groups)
        self.wait_window(dlg)
        if dlg.selected_members:
            self.tree.delete(*self.tree.get_children())
            self._fill_tree(dlg.selected_members)
            self.status_var.set(
                f"Showing {len(dlg.selected_members)} instances from duplicate group"
            )

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
            self.provenance_combo["values"] = [
                self._all_token(),
                self._("flag_green"),
                self._("flag_yellow"),
            ]
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
            source_type=self.source_type_var.get().strip() or ALL,
            control=self.control_var.get().strip() or ALL,
            provenance=self.provenance_var.get().strip() or ALL,
            programmer=self.programmer_var.get().strip() or ALL,
            newest_only=bool(self.newest_only_var.get()),
        )

    def _apply_filter_preset(self, preset: FilterPreset) -> None:
        self._filter_trace_lock = True
        try:
            self.search_var.set(preset.text or "")
            self.date_from_var.set(preset.date_from or "")
            self.date_to_var.set(preset.date_to or "")
            self.source_type_var.set(preset.source_type or ALL)
            self.control_var.set(preset.control or ALL)
            self.provenance_var.set(preset.provenance or ALL)
            self.programmer_var.set(preset.programmer or ALL)
            self.newest_only_var.set(bool(preset.newest_only))
            wanted = {m.strip() for m in (preset.machines or []) if m.strip()}
            self._machine_sel = {
                n for n in self._machine_names if n in wanted
            } if wanted else set()
            self._update_machines_button()
            self.preset_var.set(preset.name)
        finally:
            self._filter_trace_lock = False
        self._run_query_now(status_prefix=f"Loaded preset {preset.name!r}")

    def _save_current_preset(self) -> None:
        path = self._presets_path()
        if path is None:
            messagebox.showerror(
                "Presets",
                "Choose a target folder first (presets are saved next to the database).",
            )
            return
        Path(path.parent).mkdir(parents=True, exist_ok=True)
        initial = self.preset_var.get().strip()
        name = simpledialog.askstring(
            "Save preset",
            "Name for this filter set:",
            initialvalue=initial,
            parent=self,
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showerror("Presets", "Preset name cannot be empty.")
            return
        existing = get_preset(path, name)
        if existing is not None:
            if not messagebox.askyesno(
                "Presets",
                f"Replace existing preset {name!r}?",
                parent=self,
            ):
                return
        preset = self._current_filter_preset(name)
        try:
            upsert_preset(path, preset)
        except OSError as exc:
            messagebox.showerror("Presets", str(exc))
            return
        self._refresh_preset_combo()
        self.preset_var.set(name)
        self.status_var.set(f"Saved preset {name!r} → {PRESETS_FILENAME}")

    def _load_selected_preset(self) -> None:
        path = self._presets_path()
        name = self.preset_var.get().strip()
        if path is None:
            messagebox.showerror("Presets", "Choose a target folder first.")
            return
        if not name:
            messagebox.showinfo("Presets", "Select a preset name, then Load.")
            return
        preset = get_preset(path, name)
        if preset is None:
            messagebox.showinfo("Presets", f"Preset {name!r} not found.")
            self._refresh_preset_combo()
            return
        self._apply_filter_preset(preset)

    def _delete_selected_preset(self) -> None:
        path = self._presets_path()
        name = self.preset_var.get().strip()
        if path is None:
            messagebox.showerror("Presets", "Choose a target folder first.")
            return
        if not name:
            messagebox.showinfo("Presets", "Select a preset to delete.")
            return
        if not messagebox.askyesno("Presets", f"Delete preset {name!r}?", parent=self):
            return
        try:
            delete_preset(path, name)
        except OSError as exc:
            messagebox.showerror("Presets", str(exc))
            return
        self.preset_var.set("")
        self._refresh_preset_combo()
        self.status_var.set(f"Deleted preset {name!r}")

    def _clear_filters(self, status_prefix: Optional[str] = None) -> None:
        self._filter_trace_lock = True
        try:
            self.search_var.set("")
            self._machine_sel = set()
            self._update_machines_button()
            self.date_from_var.set("")
            self.date_to_var.set("")
            self.source_type_var.set(self._all_token())
            self.control_var.set(self._all_token())
            self.provenance_var.set(self._all_token())
            self.programmer_var.set(self._all_token())
            self.newest_only_var.set(False)
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

    def _run_query_now(self, status_prefix: Optional[str] = None) -> None:
        self._search_after_id = None
        self.tree.delete(*self.tree.get_children())
        self._result_rows = []
        self._clear_preview()

        db_path = self._db_path()
        if db_path is None or not db_path.is_file():
            self.status_var.set("No database yet — run a scan or open an existing DB.")
            return

        text = self.search_var.get().strip() or None
        machines = self._selected_machines()
        date_from = self.date_from_var.get().strip() or None
        date_to = self.date_to_var.get().strip() or None
        source_type = self.source_type_var.get().strip()
        control = self.control_var.get().strip()
        provenance = self._provenance_filter_value()
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
                    source_type=None if self._is_all_token(source_type) else source_type,
                    control_family=None if self._is_all_token(control) else control,
                    provenance=provenance,
                    programmer=programmer_filter,
                    newest_only=bool(self.newest_only_var.get()),
                    limit=BROWSE_LIMIT,
                )
                total = conn.execute("SELECT COUNT(*) FROM program_instances").fetchone()[0]
            finally:
                conn.close()
        except ValueError as exc:
            self.status_var.set(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Search error: {exc}")
            return

        self._fill_tree(rows)
        bits = [f"{len(rows)} shown"]
        if total > len(rows):
            bits.append(f"of {total} in DB")
        if text:
            bits.append(f"text={text!r}")
        if machines:
            bits.append(f"machines={len(machines)}")
        if date_from or date_to:
            bits.append(f"dates={date_from or '…'}→{date_to or '…'}")
        if source_type and not self._is_all_token(source_type):
            bits.append(f"type={source_type}")
        if control and not self._is_all_token(control):
            bits.append(f"control={control}")
        if provenance:
            bits.append(f"flag={provenance}")
        if programmer_filter:
            bits.append(f"programmer={programmer_filter}")
        if self.newest_only_var.get():
            bits.append("newest-only")
        summary = " · ".join(bits)
        if status_prefix:
            self.status_var.set(f"{status_prefix} — {summary}")
        else:
            self.status_var.set(summary)

    def _provenance_filter_value(self) -> Optional[str]:
        raw = self.provenance_var.get().strip()
        if self._is_all_token(raw):
            return None
        low = raw.casefold()
        if any(x in low for x in ("yellow", "żółt", "extra", "dodatk")):
            return PROVENANCE_EXTRA
        if any(x in low for x in ("green", "zielon", "backup", "kopi")):
            return PROVENANCE_BACKUP
        if raw in {PROVENANCE_BACKUP, PROVENANCE_EXTRA}:
            return raw
        return None

    def _fill_tree(self, rows: list) -> None:
        self._result_rows = rows
        for i, r in enumerate(rows):
            date = format_display_date(r["backup_date"])
            machine = r["machine_label"] or r["machine_id"] or ""
            keys = r.keys() if hasattr(r, "keys") else ()
            control = r["control_family"] if "control_family" in keys else ""
            prog_flag = ""
            if "programmer" in keys and r["programmer"]:
                prog_flag = str(r["programmer"])
            prov = ""
            if "provenance" in keys:
                prov = str(r["provenance"] or PROVENANCE_BACKUP)
            if prov == PROVENANCE_EXTRA:
                flag = "🟡"
                tag = "flag_extra"
            else:
                flag = "🟢"
                tag = "flag_backup"
            self.tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(
                    flag,
                    r["program_number"] or "",
                    r["part_number"] or "",
                    prog_flag,
                    machine,
                    date,
                    r["source_type"] or "",
                    control or "",
                    r["source_path"] or "",
                    format_location(r),
                ),
                tags=(tag,),
            )
        self._refresh_preview()

    def _set_preview_body(self, header: str, body: str, *, is_error: bool = False) -> None:
        self.preview_header_var.set(header)
        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", body)
        self.preview_text.configure(
            state=tk.DISABLED,
            foreground="#a40000" if is_error else "#222222",
        )

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
            header = f"Preview — {label}  (first of {len(rows)} selected; Compare… for two)"
        else:
            header = f"Preview — {label}"
        backup = self.backup_var.get().strip() or (self._backup_root_from_db() or "")
        body, err = preview_text(row, backup_root=backup or None)
        if err:
            self._set_preview_body(header, f"Cannot preview:\n{err}", is_error=True)
            return
        self._set_preview_body(header, body)

    def _compare_selected(self) -> None:
        rows = self._selected_rows()
        if len(rows) != 2:
            messagebox.showinfo(
                "Compare",
                "Select exactly two result rows (Ctrl/Shift+click), then Compare…",
            )
            return
        backup = self.backup_var.get().strip() or (self._backup_root_from_db() or "")
        diff_text, err = unified_diff_programs(
            rows[0], rows[1], backup_root=backup or None
        )
        if err:
            messagebox.showerror("Compare", err)
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
            messagebox.showinfo("Selection", "Select a search result first.")
            return None
        backup = self.backup_var.get().strip() or (self._backup_root_from_db() or "")
        sp = str(row["source_path"] or "")
        if not sp:
            messagebox.showerror("Path", "This row has no source path.")
            return None
        keys = row.keys() if hasattr(row, "keys") else ()
        scan_root = None
        if "scan_root" in keys and row["scan_root"]:
            scan_root = str(row["scan_root"])
        return resolve_source_abspath(sp, backup or None, scan_root)

    def _open_selected_folder(self) -> None:
        path = self._row_source_path()
        if path is None:
            return
        if not path.exists():
            messagebox.showerror(
                "Open folder",
                f"Path not found on disk:\n{path}\n\n"
                "Check that the backup folder is set correctly.",
            )
            return
        try:
            open_path_in_file_manager(path)
            self.status_var.set(f"Opened folder for {path.name}")
        except OSError as exc:
            messagebox.showerror("Open folder", str(exc))

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
            messagebox.showerror("Copy path", str(exc))
            return
        self.status_var.set(f"Copied path: {text}")

    def _extract_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            messagebox.showinfo("Extract", "Select one or more search results first.")
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
                "Backup folder",
                "Set the backup folder (needed to resolve relative source paths).",
            )
            return

        Path(extract_dir).mkdir(parents=True, exist_ok=True)

        if len(rows) == 1:
            row = rows[0]
            suggested = default_extract_filename(row)
            out = filedialog.asksaveasfilename(
                title="Save extracted program",
                initialdir=extract_dir,
                initialfile=suggested,
                defaultextension=".nc",
                filetypes=[("NC / text", "*.nc *.txt"), ("All", "*.*")],
            )
            if not out:
                return
            try:
                path = extract_to_path(row, out, backup_root=backup or None)
            except ExtractError as exc:
                messagebox.showerror("Extract failed", str(exc))
                return
            self.status_var.set(f"Extracted → {path}")
            messagebox.showinfo("Extracted", f"Wrote:\n{path}")
            return

        # Batch: pick output folder, write unique filenames
        out_dir = filedialog.askdirectory(
            title=f"Extract {len(rows)} programs into folder",
            initialdir=extract_dir,
        )
        if not out_dir:
            return
        used: set[str] = set()
        ok = 0
        errors: list[str] = []
        for row in rows:
            name = batch_extract_filename(row, used=used)
            dest = Path(out_dir) / name
            try:
                extract_to_path(row, dest, backup_root=backup or None)
                ok += 1
            except ExtractError as exc:
                prog = row["program_number"] if "program_number" in row.keys() else "?"
                errors.append(f"{prog}: {exc}")
        msg = f"Extracted {ok} / {len(rows)} → {out_dir}"
        if errors:
            msg += f"\n\n{len(errors)} failed:\n" + "\n".join(errors[:8])
            if len(errors) > 8:
                msg += f"\n… +{len(errors) - 8} more"
            messagebox.showwarning("Batch extract", msg)
        else:
            messagebox.showinfo("Batch extract", msg)
        self.status_var.set(f"Extracted {ok} / {len(rows)} programs")

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
        self.title("Compare programs")
        self.minsize(640, 420)
        self.geometry("860x560")
        self.transient(master)
        self.grab_set()

        ttk.Label(
            self,
            text=f"A: {label_a}\nB: {label_b}",
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
        ttk.Button(btns, text="Close", command=self.destroy).pack(side=tk.RIGHT)


class ScanReportDialog(tk.Toplevel):
    """Post-scan quality summary (#14): counts, copies, UNKNOWN, skipped."""

    def __init__(self, master: tk.Tk, *, report: ScanReport) -> None:
        super().__init__(master)
        self.title("Scan report")
        self.minsize(560, 420)
        self.geometry("720x560")
        self.transient(master)
        self.grab_set()

        ttk.Label(
            self,
            text="Index quality after the last scan — machines, copies, "
            "MACHINE UNKNOWN, unmapped folders, skipped dumps.",
            wraplength=680,
        ).pack(fill=tk.X, padx=12, pady=(12, 6))

        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        text = tk.Text(frame, wrap=tk.WORD, font=("Consolas", 10), height=24)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=sb.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        body = format_scan_report(report)
        text.insert("1.0", body)
        text.configure(state=tk.DISABLED)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btns, text="Close", command=self.destroy).pack(side=tk.RIGHT)


class DuplicatesDialog(tk.Toplevel):
    """Exact SHA and near-duplicate (same O# + similar size) finder (#13)."""

    def __init__(self, master: tk.Tk, *, groups: list[DuplicateGroup]) -> None:
        super().__init__(master)
        self.title("Duplicate / near-duplicate finder")
        self.minsize(640, 440)
        self.geometry("780x520")
        self.transient(master)
        self.grab_set()
        self.selected_members: list = []
        self._groups = groups

        n_exact = sum(1 for g in groups if g.kind == "exact")
        n_near = sum(1 for g in groups if g.kind == "near")
        ttk.Label(
            self,
            text=(
                f"{n_exact} exact SHA group(s), {n_near} near-duplicate group(s). "
                "Select a group, then Show in results to load members into the main table."
            ),
            wraplength=740,
        ).pack(fill=tk.X, padx=12, pady=(12, 6))

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
        for g in groups:
            prefix = "SHA" if g.kind == "exact" else "Near"
            self.group_list.insert(tk.END, f"[{prefix}] {g.label}")
        self.group_list.bind("<<ListboxSelect>>", self._on_group_select)

        cols = ("program", "machine", "date", "size", "sha", "path")
        self.member_tree = ttk.Treeview(
            bottom, columns=cols, show="headings", selectmode="browse", height=10
        )
        headings = {
            "program": ("Program #", 90),
            "machine": ("Machine", 120),
            "date": ("Date", 100),
            "size": ("Size", 70),
            "sha": ("SHA-256", 120),
            "path": ("Source path", 280),
        }
        for key, (label, width) in headings.items():
            self.member_tree.heading(key, text=label)
            self.member_tree.column(key, width=width, stretch=(key == "path"), minwidth=40)
        msb = ttk.Scrollbar(bottom, orient=tk.VERTICAL, command=self.member_tree.yview)
        self.member_tree.configure(yscrollcommand=msb.set)
        self.member_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        msb.pack(side=tk.RIGHT, fill=tk.Y)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Show in results", command=self._show_in_results).pack(
            side=tk.RIGHT, padx=8
        )

        if groups:
            self.group_list.selection_set(0)
            self._on_group_select()

    def _on_group_select(self, *_args) -> None:
        self.member_tree.delete(*self.member_tree.get_children())
        sel = self.group_list.curselection()
        if not sel:
            return
        group = self._groups[sel[0]]
        for i, m in enumerate(group.members):
            sha = str(m["content_sha256"] or "")
            sha_short = (sha[:12] + "…") if len(sha) > 12 else sha
            size = m["source_size"]
            size_s = str(size) if size is not None else ""
            machine = m["machine_label"] or m["machine_id"] or ""
            self.member_tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(
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
            messagebox.showinfo("Duplicates", "Select a group first.", parent=self)
            return
        self.selected_members = list(self._groups[sel[0]].members)
        self.destroy()


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
        self.title("Map unmatched folders → machines")
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

        summary = (
            f"Auto-matched via aliases: {partition.auto_count}  ·  "
            f"Previously mapped: {len(partition.previously_mapped)}  ·  "
            f"Need manual assign: {partition.manual_count}"
        )
        ttk.Label(self, text=summary, wraplength=640).pack(
            fill=tk.X, padx=12, pady=(12, 4)
        )
        ttk.Label(
            self,
            text="Only unmatched folders are listed. Assign a machine, then Save. "
            "Optional: also store the folder name as a local alias for future scans "
            f"({LOCAL_ALIASES_FILENAME} next to the database).",
            wraplength=640,
        ).pack(fill=tk.X, padx=12, pady=(0, 6))

        if partition.auto_matched:
            auto_frame = ttk.LabelFrame(self, text="Auto-matched (skipped)")
            auto_frame.pack(fill=tk.X, padx=12, pady=4)
            preview = ", ".join(
                f"{name}→{info.label or info.machine_id}"
                for name, info in partition.auto_matched[:12]
            )
            if len(partition.auto_matched) > 12:
                preview += f", … (+{len(partition.auto_matched) - 12} more)"
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

        ttk.Label(inner, text="Folder").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Label(inner, text="Machine").grid(row=0, column=1, sticky=tk.W, padx=4, pady=2)

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
            text="Also save assignments as local aliases (for new scans)",
            variable=self._save_aliases_var,
        ).pack(anchor=tk.W, padx=12, pady=(4, 0))

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Save map", command=self._save).pack(side=tk.RIGHT, padx=8)

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
            messagebox.showerror("Save map", str(exc), parent=self)
            return
        if self._save_aliases_var.get() and self._aliases.local_alias_count:
            try:
                self._aliases.save_local(self._local_aliases_path)
                self.aliases_saved = True
            except OSError as exc:
                messagebox.showerror("Save local aliases", str(exc), parent=self)
                return
        self.saved = True
        self.destroy()


class AliasEditorDialog(tk.Toplevel):
    """Add / change / remove shop-local machine aliases (aliases.local.yaml)."""

    def __init__(
        self,
        master: tk.Tk,
        *,
        aliases: AliasMap,
        save_path: Path,
    ) -> None:
        super().__init__(master)
        self.title("Machine aliases")
        self.minsize(640, 420)
        self.geometry("760x520")
        self.transient(master)
        self.grab_set()
        self.saved = False
        self._aliases = aliases
        self._save_path = Path(save_path)
        self._dirty = False

        ttk.Label(
            self,
            text=(
                "Local aliases live next to the database and override the bundled map. "
                "Add a folder spelling (e.g. VF2_old) → catalog machine. "
                "Bundled aliases below are read-only — use Override to copy one into local."
            ),
            wraplength=720,
        ).pack(fill=tk.X, padx=12, pady=(12, 6))

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        local_tab = ttk.Frame(nb)
        bundled_tab = ttk.Frame(nb)
        nb.add(local_tab, text="Local (editable)")
        nb.add(bundled_tab, text="Bundled (read-only)")

        cols = ("folder", "machine_id", "label", "layout")
        local_pane = ttk.Frame(local_tab)
        local_pane.pack(fill=tk.BOTH, expand=True)
        self._local_tree = ttk.Treeview(
            local_pane, columns=cols, show="headings", selectmode="browse"
        )
        for c, w, t in (
            ("folder", 160, "Folder name"),
            ("machine_id", 140, "Machine id"),
            ("label", 160, "Label"),
            ("layout", 120, "Layout"),
        ):
            self._local_tree.heading(c, text=t)
            self._local_tree.column(c, width=w, stretch=True)
        local_sb = ttk.Scrollbar(local_pane, orient=tk.VERTICAL, command=self._local_tree.yview)
        self._local_tree.configure(yscrollcommand=local_sb.set)
        self._local_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        local_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._local_tree.bind("<Double-1>", lambda _e: self._edit_selected())

        local_btns = ttk.Frame(local_tab)
        local_btns.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(local_btns, text="Add…", command=self._add).pack(side=tk.LEFT)
        ttk.Button(local_btns, text="Edit…", command=self._edit_selected).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(local_btns, text="Remove", command=self._remove_selected).pack(
            side=tk.LEFT, padx=6
        )

        bun_pane = ttk.Frame(bundled_tab)
        bun_pane.pack(fill=tk.BOTH, expand=True)
        self._bundled_tree = ttk.Treeview(
            bun_pane, columns=cols, show="headings", selectmode="browse"
        )
        for c, w, t in (
            ("folder", 160, "Folder key"),
            ("machine_id", 140, "Machine id"),
            ("label", 160, "Label"),
            ("layout", 120, "Layout"),
        ):
            self._bundled_tree.heading(c, text=t)
            self._bundled_tree.column(c, width=w, stretch=True)
        bun_sb = ttk.Scrollbar(bun_pane, orient=tk.VERTICAL, command=self._bundled_tree.yview)
        self._bundled_tree.configure(yscrollcommand=bun_sb.set)
        self._bundled_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        bun_sb.pack(side=tk.RIGHT, fill=tk.Y)

        bun_btns = ttk.Frame(bundled_tab)
        bun_btns.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(
            bun_btns,
            text="Override selected → local…",
            command=self._override_bundled,
        ).pack(side=tk.LEFT)

        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=12, pady=12)
        ttk.Label(
            footer,
            text=f"Saves to: {self._save_path.name}",
        ).pack(side=tk.LEFT)
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(footer, text="Save", command=self._save).pack(side=tk.RIGHT, padx=8)

        self._reload_trees()

    def _reload_trees(self) -> None:
        for tree in (self._local_tree, self._bundled_tree):
            for item in tree.get_children():
                tree.delete(item)
        for folder, entry in self._aliases.list_local_aliases():
            self._local_tree.insert(
                "",
                tk.END,
                iid=f"local:{folder}",
                values=(
                    folder,
                    entry.get("machine_id") or "",
                    entry.get("label") or "",
                    entry.get("layout") or "",
                ),
            )
        for folder, entry in self._aliases.list_bundled_alias_keys():
            self._bundled_tree.insert(
                "",
                tk.END,
                iid=f"bun:{folder}",
                values=(
                    folder,
                    entry.get("machine_id") or "",
                    entry.get("label") or "",
                    entry.get("layout") or "",
                ),
            )

    def _selected_local_folder(self) -> Optional[str]:
        sel = self._local_tree.selection()
        if not sel:
            return None
        vals = self._local_tree.item(sel[0], "values")
        return str(vals[0]) if vals else None

    def _add(self) -> None:
        form = AliasEditForm(
            self,
            title="Add local alias",
            aliases=self._aliases,
            initial_folder="",
            initial_machine_id="",
        )
        self.wait_window(form)
        if not form.result:
            return
        folder, mid, label, layout = form.result
        self._aliases.add_local_alias(folder, mid, label=label, layout=layout or None)
        self._dirty = True
        self._reload_trees()

    def _edit_selected(self) -> None:
        folder = self._selected_local_folder()
        if not folder:
            messagebox.showinfo("Edit alias", "Select a local alias first.", parent=self)
            return
        entry = None
        for raw, ent in self._aliases.list_local_aliases():
            if raw == folder:
                entry = ent
                break
        if entry is None:
            return
        form = AliasEditForm(
            self,
            title="Edit local alias",
            aliases=self._aliases,
            initial_folder=folder,
            initial_machine_id=str(entry.get("machine_id") or ""),
            initial_label=str(entry.get("label") or ""),
            initial_layout=str(entry.get("layout") or ""),
        )
        self.wait_window(form)
        if not form.result:
            return
        new_folder, mid, label, layout = form.result
        if new_folder != folder:
            self._aliases.rename_local_alias(folder, new_folder)
            folder = new_folder
        self._aliases.add_local_alias(folder, mid, label=label, layout=layout or None)
        self._dirty = True
        self._reload_trees()

    def _remove_selected(self) -> None:
        folder = self._selected_local_folder()
        if not folder:
            messagebox.showinfo("Remove alias", "Select a local alias first.", parent=self)
            return
        if not messagebox.askyesno(
            "Remove alias",
            f"Remove local alias “{folder}”?",
            parent=self,
        ):
            return
        self._aliases.remove_local_alias(folder)
        self._dirty = True
        self._reload_trees()

    def _override_bundled(self) -> None:
        sel = self._bundled_tree.selection()
        if not sel:
            messagebox.showinfo(
                "Override",
                "Select a bundled alias first.",
                parent=self,
            )
            return
        vals = self._bundled_tree.item(sel[0], "values")
        folder, mid, label, layout = (str(v) for v in vals)
        form = AliasEditForm(
            self,
            title="Override → local alias",
            aliases=self._aliases,
            initial_folder=folder,
            initial_machine_id=mid,
            initial_label=label,
            initial_layout=layout,
        )
        self.wait_window(form)
        if not form.result:
            return
        new_folder, new_mid, new_label, new_layout = form.result
        self._aliases.add_local_alias(
            new_folder, new_mid, label=new_label, layout=new_layout or None
        )
        self._dirty = True
        self._reload_trees()

    def _save(self) -> None:
        try:
            self._aliases.save_local(self._save_path)
        except OSError as exc:
            messagebox.showerror("Save aliases", str(exc), parent=self)
            return
        self.saved = True
        self._dirty = False
        self.destroy()


class AliasEditForm(tk.Toplevel):
    """Small form: folder spelling + machine picker."""

    def __init__(
        self,
        master: tk.Toplevel,
        *,
        title: str,
        aliases: AliasMap,
        initial_folder: str,
        initial_machine_id: str,
        initial_label: str = "",
        initial_layout: str = "",
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.grab_set()
        self.result: Optional[tuple[str, str, Optional[str], str]] = None
        self._aliases = aliases
        self._catalog = aliases.catalog_machines()
        self._display_to_id: dict[str, str] = {}
        choices: list[str] = []
        for m in self._catalog:
            mid = m["machine_id"]
            lab = str(m.get("label") or "").strip()
            disp = f"{lab} ({mid})" if lab and lab != mid else mid
            choices.append(disp)
            self._display_to_id[disp] = mid
        initial_disp = ""
        for disp, mid in self._display_to_id.items():
            if mid == initial_machine_id:
                initial_disp = disp
                break
        if initial_machine_id and not initial_disp:
            initial_disp = initial_machine_id
            choices.append(initial_disp)
            self._display_to_id[initial_disp] = initial_machine_id

        body = ttk.Frame(self, padding=12)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text="Folder name (as in backup tree)").grid(
            row=0, column=0, sticky=tk.W
        )
        self.folder_var = tk.StringVar(value=initial_folder)
        ttk.Entry(body, textvariable=self.folder_var, width=40).grid(
            row=0, column=1, sticky=tk.EW, padx=6, pady=4
        )
        ttk.Label(body, text="Machine").grid(row=1, column=0, sticky=tk.W)
        self.machine_var = tk.StringVar(value=initial_disp)
        self._machine_combo = ttk.Combobox(
            body,
            textvariable=self.machine_var,
            values=choices,
            state="readonly",
            width=38,
        )
        self._machine_combo.grid(row=1, column=1, sticky=tk.EW, padx=6, pady=4)
        self._machine_combo.bind("<<ComboboxSelected>>", self._on_machine_picked)
        ttk.Label(body, text="Label (optional)").grid(row=2, column=0, sticky=tk.W)
        self.label_var = tk.StringVar(value=initial_label)
        ttk.Entry(body, textvariable=self.label_var, width=40).grid(
            row=2, column=1, sticky=tk.EW, padx=6, pady=4
        )
        ttk.Label(body, text="Layout (optional)").grid(row=3, column=0, sticky=tk.W)
        layouts = [
            "",
            "haas_pgm",
            "haas_ngc",
            "fanuc_all_fldr",
            "fanuc_all_prog",
            "manual_nc_folder",
        ]
        self.layout_var = tk.StringVar(value=initial_layout)
        ttk.Combobox(
            body,
            textvariable=self.layout_var,
            values=layouts,
            width=38,
        ).grid(row=3, column=1, sticky=tk.EW, padx=6, pady=4)
        body.columnconfigure(1, weight=1)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=8)
        if initial_disp and not initial_label:
            self._on_machine_picked()

    def _on_machine_picked(self, _event: object = None) -> None:
        mid = self._display_to_id.get(self.machine_var.get().strip(), "")
        info = self._aliases.info_for_machine_id(mid, self.folder_var.get() or mid)
        if info is None:
            return
        if info.label and not self.label_var.get().strip():
            self.label_var.set(info.label)
        if info.layout and not self.layout_var.get().strip():
            self.layout_var.set(info.layout)

    def _ok(self) -> None:
        folder = self.folder_var.get().strip()
        disp = self.machine_var.get().strip()
        mid = self._display_to_id.get(disp, "")
        if not mid and disp:
            # Allow typing a raw machine_id if somehow not in catalog
            parsed_mid, _ = parse_machine_display(disp)
            mid = parsed_mid if parsed_mid != UNKNOWN_ID else disp
        if not folder:
            messagebox.showerror("Alias", "Folder name is required.", parent=self)
            return
        if not mid or mid == UNKNOWN_ID:
            messagebox.showerror("Alias", "Choose a machine.", parent=self)
            return
        label = self.label_var.get().strip() or None
        layout = self.layout_var.get().strip()
        self.result = (folder, mid, label, layout)
        self.destroy()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    app = IndexerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
