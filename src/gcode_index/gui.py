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
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from gcode_index.aliases import (
    AliasMap,
    LOCAL_ALIASES_FILENAME,
    default_aliases_path,
    local_aliases_path_for_target,
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
    default_extract_filename,
    extract_to_path,
)
from gcode_index.extra_roots import (
    EXTRA_ROOTS_FILENAME,
    extra_roots_path_for_target,
    load_extra_roots,
    normalize_extra_roots,
    save_extra_roots,
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
from gcode_index.scanner import scan_backup_tree, scan_with_extra_roots

log = logging.getLogger(__name__)

SEARCH_DEBOUNCE_MS = 250
DEFAULT_DB_NAME = "gcode_index.sqlite"
BROWSE_LIMIT = 500
ALL = "(all)"
UNKNOWN_MACHINE_DISPLAY = "MACHINE UNKNOWN (unknown)"

# Re-export helpers for callers that imported them from gui
__all__ = [
    "IndexerApp",
    "main",
    "SEARCH_DEBOUNCE_MS",
    "format_eta",
    "open_path_in_file_manager",
    "resolve_source_abspath",
]


class IndexerApp(tk.Tk):
    """Main window: backup + target folders, scan, live search, extract."""

    def __init__(self) -> None:
        super().__init__()
        self.title("G-code Backup Indexer")
        self.minsize(1040, 620)
        self.geometry("1320x720")

        self.backup_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.date_from_var = tk.StringVar()
        self.date_to_var = tk.StringVar()
        self.source_type_var = tk.StringVar(value=ALL)
        self.control_var = tk.StringVar(value=ALL)
        self.provenance_var = tk.StringVar(value=ALL)
        self.status_var = tk.StringVar(
            value="Pick a backup folder and a target folder for the database."
        )
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_label_var = tk.StringVar(value="")

        self._search_after_id: Optional[str] = None
        self._result_rows: list = []
        self._scan_busy = False
        self._filter_trace_lock = False
        self._machine_names: list[str] = []

        self._build()
        # Seed machine list from aliases before any scan
        self._refresh_filter_choices()
        self.search_var.trace_add("write", self._on_filter_changed)
        for var in (
            self.date_from_var,
            self.date_to_var,
            self.source_type_var,
            self.control_var,
            self.provenance_var,
        ):
            var.trace_add("write", self._on_filter_changed)

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        paths = ttk.LabelFrame(root, text="Folders", padding=8)
        paths.pack(fill=tk.X, **pad)

        ttk.Label(paths, text="Backup folder").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(paths, textvariable=self.backup_var).grid(
            row=0, column=1, sticky=tk.EW, padx=4
        )
        ttk.Button(paths, text="Browse…", command=self._pick_backup).grid(row=0, column=2)

        ttk.Label(paths, text="Target folder (DB / extracts)").grid(
            row=1, column=0, sticky=tk.W
        )
        ttk.Entry(paths, textvariable=self.target_var).grid(
            row=1, column=1, sticky=tk.EW, padx=4
        )
        ttk.Button(paths, text="Browse…", command=self._pick_target).grid(row=1, column=2)
        paths.columnconfigure(1, weight=1)

        extra = ttk.LabelFrame(
            root,
            text="Extra folders (yellow flag — not from machine backup)",
            padding=8,
        )
        extra.pack(fill=tk.X, **pad)
        extra_row = ttk.Frame(extra)
        extra_row.pack(fill=tk.X)
        self.extra_list = tk.Listbox(extra_row, height=3, selectmode=tk.EXTENDED)
        extra_sb = ttk.Scrollbar(extra_row, orient=tk.VERTICAL, command=self.extra_list.yview)
        self.extra_list.configure(yscrollcommand=extra_sb.set)
        self.extra_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        extra_sb.pack(side=tk.RIGHT, fill=tk.Y)
        extra_btns = ttk.Frame(extra)
        extra_btns.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(extra_btns, text="Add folder…", command=self._add_extra_root).pack(
            side=tk.LEFT
        )
        ttk.Button(extra_btns, text="Remove selected", command=self._remove_extra_roots).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Label(
            extra_btns,
            text="Main backup = green (ran on machine). Extra = yellow (not in backup).",
            foreground="#444",
        ).pack(side=tk.LEFT, padx=8)

        actions = ttk.Frame(root)
        actions.pack(fill=tk.X, **pad)
        self.scan_btn = ttk.Button(actions, text="Run index / scan", command=self._start_scan)
        self.scan_btn.pack(side=tk.LEFT)
        ttk.Button(actions, text="Map folders…", command=self._open_folder_map).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Button(actions, text="Aliases…", command=self._open_alias_editor).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(actions, text="Open existing DB…", command=self._pick_existing_db).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(actions, text="Clear filters", command=self._clear_filters).pack(
            side=tk.LEFT, padx=4
        )
        self.excel_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions, text="Also write Excel", variable=self.excel_var).pack(
            side=tk.LEFT
        )

        prog_frame = ttk.Frame(root)
        prog_frame.pack(fill=tk.X, **pad)
        self.progress = ttk.Progressbar(
            prog_frame,
            mode="determinate",
            maximum=100.0,
            variable=self.progress_var,
        )
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(prog_frame, textvariable=self.progress_label_var, width=42).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        filt = ttk.LabelFrame(
            root,
            text="Find programs — text · machines (multi-select) · date · source",
            padding=8,
        )
        filt.pack(fill=tk.X, **pad)

        ttk.Label(filt, text="Text").grid(row=0, column=0, sticky=tk.W)
        self.search_entry = ttk.Entry(filt, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=1, columnspan=5, sticky=tk.EW, padx=4)
        ttk.Button(filt, text="Extract selected…", command=self._extract_selected).grid(
            row=0, column=6, padx=4
        )

        ttk.Label(filt, text="Machines").grid(row=1, column=0, sticky=tk.NW, pady=(6, 0))
        mach_frame = ttk.Frame(filt)
        mach_frame.grid(row=1, column=1, sticky=tk.NSEW, padx=4, pady=(6, 0))
        self.machine_list = tk.Listbox(
            mach_frame,
            selectmode=tk.EXTENDED,
            height=5,
            exportselection=False,
            width=36,
        )
        mach_sb = ttk.Scrollbar(mach_frame, orient=tk.VERTICAL, command=self.machine_list.yview)
        self.machine_list.configure(yscrollcommand=mach_sb.set)
        self.machine_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        mach_sb.pack(side=tk.LEFT, fill=tk.Y)
        self.machine_list.bind("<<ListboxSelect>>", self._on_filter_changed)

        mach_btns = ttk.Frame(filt)
        mach_btns.grid(row=1, column=2, sticky=tk.NW, pady=(6, 0))
        ttk.Button(mach_btns, text="All", width=8, command=self._select_all_machines).pack(
            anchor=tk.W, pady=1
        )
        ttk.Button(mach_btns, text="None", width=8, command=self._clear_machine_selection).pack(
            anchor=tk.W, pady=1
        )
        ttk.Label(mach_btns, text="Ctrl/Shift+click\nfor multi-select", foreground="#555").pack(
            anchor=tk.W, pady=(4, 0)
        )

        ttk.Label(filt, text="Date from").grid(row=1, column=3, sticky=tk.NW, pady=(6, 0))
        date_box = ttk.Frame(filt)
        date_box.grid(row=1, column=4, columnspan=3, sticky=tk.NW, padx=4, pady=(6, 0))
        ttk.Entry(date_box, textvariable=self.date_from_var, width=11).grid(
            row=0, column=0, sticky=tk.W
        )
        ttk.Label(date_box, text=" to ").grid(row=0, column=1, sticky=tk.W)
        ttk.Entry(date_box, textvariable=self.date_to_var, width=11).grid(
            row=0, column=2, sticky=tk.W
        )
        ttk.Label(date_box, text="DD.MM.YYYY", foreground="#555").grid(
            row=1, column=0, columnspan=3, sticky=tk.W, pady=(2, 0)
        )

        ttk.Label(filt, text="Source type").grid(row=2, column=0, sticky=tk.W, pady=(6, 0))
        self.type_combo = ttk.Combobox(
            filt, textvariable=self.source_type_var, values=[ALL], state="readonly", width=22
        )
        self.type_combo.grid(row=2, column=1, sticky=tk.EW, padx=4, pady=(6, 0))

        ttk.Label(filt, text="Control").grid(row=2, column=3, sticky=tk.W, pady=(6, 0))
        self.control_combo = ttk.Combobox(
            filt, textvariable=self.control_var, values=[ALL], state="readonly", width=14
        )
        self.control_combo.grid(row=2, column=4, sticky=tk.W, padx=4, pady=(6, 0))

        ttk.Label(filt, text="Flag").grid(row=2, column=5, sticky=tk.W, pady=(6, 0))
        self.provenance_combo = ttk.Combobox(
            filt,
            textvariable=self.provenance_var,
            values=[ALL, "green — backup (ran)", "yellow — extra (not run)"],
            state="readonly",
            width=26,
        )
        self.provenance_combo.grid(row=2, column=6, sticky=tk.W, padx=4, pady=(6, 0))

        row_actions = ttk.Frame(filt)
        row_actions.grid(row=3, column=6, sticky=tk.E, pady=(6, 0))
        ttk.Button(row_actions, text="Open folder", command=self._open_selected_folder).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(row_actions, text="Copy path", command=self._copy_selected_path).pack(
            side=tk.LEFT, padx=2
        )

        hint = ttk.Label(
            filt,
            text="Green flag = from main backup (ran on machine). "
            "Yellow = from an extra folder (not in backup). "
            "Empty machine selection = all machines. "
            "Right-click a row for Open folder / Copy path.",
            foreground="#444",
        )
        hint.grid(row=4, column=0, columnspan=7, sticky=tk.W, pady=(6, 0))

        filt.columnconfigure(1, weight=1)

        cols = (
            "flag",
            "program",
            "part",
            "machine",
            "date",
            "type",
            "control",
            "path",
            "location",
        )
        tree_frame = ttk.Frame(root)
        tree_frame.pack(fill=tk.BOTH, expand=True, **pad)
        self.tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings", selectmode="browse"
        )
        headings = {
            "flag": ("Flag", 56),
            "program": ("Program #", 90),
            "part": ("Part number", 150),
            "machine": ("Machine", 120),
            "date": ("Date", 110),
            "type": ("Source type", 110),
            "control": ("Control", 80),
            "path": ("Source path", 260),
            "location": ("In-file location", 130),
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
        if sys.platform == "darwin":
            self.tree.bind("<Button-2>", self._on_tree_context)
            self.tree.bind("<Control-Button-1>", self._on_tree_context)

        self._ctx_menu = tk.Menu(self, tearoff=0)
        self._ctx_menu.add_command(label="Extract selected…", command=self._extract_selected)
        self._ctx_menu.add_command(label="Open folder", command=self._open_selected_folder)
        self._ctx_menu.add_command(label="Copy path", command=self._copy_selected_path)

        status = ttk.Label(root, textvariable=self.status_var, anchor=tk.W)
        status.pack(fill=tk.X, **pad)

    # --- paths ------------------------------------------------------------------

    def _pick_backup(self) -> None:
        path = filedialog.askdirectory(title="Select CNC backup folder")
        if path:
            self.backup_var.set(path)

    def _pick_target(self) -> None:
        path = filedialog.askdirectory(title="Select target folder for database / extracts")
        if path:
            self.target_var.set(path)
            self._load_extra_roots_into_list()

    def _pick_existing_db(self) -> None:
        path = filedialog.askopenfilename(
            title="Open existing gcode_index.sqlite",
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

    def _extra_roots_from_list(self) -> list[str]:
        return [self.extra_list.get(i) for i in range(self.extra_list.size())]

    def _load_extra_roots_into_list(self) -> None:
        self.extra_list.delete(0, tk.END)
        target = self.target_var.get().strip()
        if not target:
            return
        path = extra_roots_path_for_target(target)
        for root in load_extra_roots(path):
            self.extra_list.insert(tk.END, root)

    def _persist_extra_roots(self) -> None:
        target = self.target_var.get().strip()
        if not target:
            return
        Path(target).mkdir(parents=True, exist_ok=True)
        save_extra_roots(extra_roots_path_for_target(target), self._extra_roots_from_list())

    def _add_extra_root(self) -> None:
        path = filedialog.askdirectory(title="Select extra folder to scan (and subfolders)")
        if not path:
            return
        existing = {p.casefold() for p in self._extra_roots_from_list()}
        backup = self.backup_var.get().strip()
        try:
            resolved = str(Path(path).resolve())
        except OSError:
            resolved = path
        if backup:
            try:
                if str(Path(backup).resolve()) == resolved:
                    messagebox.showinfo(
                        "Extra folder",
                        "That folder is already the main backup root.",
                    )
                    return
            except OSError:
                pass
        if resolved.casefold() in existing or path.casefold() in existing:
            messagebox.showinfo("Extra folder", "That folder is already in the list.")
            return
        self.extra_list.insert(tk.END, resolved)
        self._persist_extra_roots()

    def _remove_extra_roots(self) -> None:
        sel = list(self.extra_list.curselection())
        if not sel:
            return
        for i in reversed(sel):
            self.extra_list.delete(i)
        self._persist_extra_roots()

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

    def _start_scan(self) -> None:
        if self._scan_busy:
            return
        backup = self.backup_var.get().strip()
        target = self.target_var.get().strip()
        if not backup or not Path(backup).is_dir():
            messagebox.showerror("Backup folder", "Choose a valid backup folder.")
            return
        if not target:
            messagebox.showerror("Target folder", "Choose a target folder for the database.")
            return
        Path(target).mkdir(parents=True, exist_ok=True)
        # Offer mapper only when unmatched folders remain
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
        self.scan_btn.configure(state=tk.DISABLED)
        self.progress_var.set(0.0)
        self.progress_label_var.set("Starting…")
        self.status_var.set("Scanning…")
        write_excel = bool(self.excel_var.get())
        self._persist_extra_roots()
        extras = normalize_extra_roots(
            self._extra_roots_from_list(),
            backup_root=backup,
        )
        threading.Thread(
            target=self._scan_worker,
            args=(Path(backup), Path(target), write_excel, extras),
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
        extras: list[Path],
    ) -> None:
        try:
            aliases_path = default_aliases_path()
            local_path = local_aliases_path_for_target(target)
            alias_map = AliasMap.load_merged(aliases_path, local_path)
            folder_map = FolderMachineMap.load(map_path_for_target(target))
            fmap = folder_map if folder_map.assignments else None
            if extras:
                result = scan_with_extra_roots(
                    backup,
                    alias_map,
                    extra_roots=extras,
                    progress=self._on_scan_progress,
                    folder_map=fmap,
                )
            else:
                result = scan_backup_tree(
                    backup,
                    alias_map,
                    progress=self._on_scan_progress,
                    folder_map=fmap,
                    provenance=PROVENANCE_BACKUP,
                )
            db_path = target / DEFAULT_DB_NAME
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
            msg = (
                f"Indexed {len(result.instances)} programs "
                f"[{type_note}] "
                f"({len(result.unknowns)} unknown folders{unk_note}{local_note}{flag_note}) "
                f"→ {db_path.name} "
                f"(run {run_id[:8]}…){excel_note}"
            )
            self.after(0, lambda: self._scan_done(True, msg))
        except Exception as exc:  # noqa: BLE001 — show in UI
            log.exception("scan failed")
            self.after(0, lambda: self._scan_done(False, str(exc)))

    def _scan_done(self, ok: bool, message: str) -> None:
        self._scan_busy = False
        self.scan_btn.configure(state=tk.NORMAL)
        try:
            self.progress.stop()
        except tk.TclError:
            pass
        self.progress.configure(mode="determinate")
        if ok:
            self.progress_var.set(100.0)
            self.progress_label_var.set("Done")
        else:
            self.progress_var.set(0.0)
            self.progress_label_var.set("")
        self.status_var.set(message)
        if not ok:
            messagebox.showerror("Scan failed", message)
            return
        self._refresh_filter_choices()
        self._clear_filters(status_prefix=message)

    # --- filters / search -------------------------------------------------------

    def _selected_machines(self) -> list[str]:
        sel = self.machine_list.curselection()
        if not sel:
            return []
        names = [self.machine_list.get(i) for i in sel]
        # Treating "all selected" the same as none keeps the query unfiltered
        if self._machine_names and len(names) == len(self._machine_names):
            return []
        return names

    def _select_all_machines(self) -> None:
        self.machine_list.selection_set(0, tk.END)
        self._on_filter_changed()

    def _clear_machine_selection(self) -> None:
        self.machine_list.selection_clear(0, tk.END)
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
        self.machine_list.delete(0, tk.END)
        for name in self._machine_names:
            self.machine_list.insert(tk.END, name)
        for i, name in enumerate(self._machine_names):
            if name in prev:
                self.machine_list.selection_set(i)
        self.type_combo["values"] = [ALL, *vals["source_types"]]
        self.control_combo["values"] = [ALL, *vals["control_families"]]

    def _clear_filters(self, status_prefix: Optional[str] = None) -> None:
        self._filter_trace_lock = True
        try:
            self.search_var.set("")
            self.machine_list.selection_clear(0, tk.END)
            self.date_from_var.set("")
            self.date_to_var.set("")
            self.source_type_var.set(ALL)
            self.control_var.set(ALL)
            self.provenance_var.set(ALL)
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

        try:
            conn = open_db(db_path)
            try:
                rows = query_instances(
                    conn,
                    text=text,
                    machines=machines or None,
                    date_from=date_from,
                    date_to=date_to,
                    source_type=source_type,
                    control_family=control,
                    provenance=provenance,
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
        if source_type and source_type != ALL:
            bits.append(f"type={source_type}")
        if control and control != ALL:
            bits.append(f"control={control}")
        if provenance:
            bits.append(f"flag={provenance}")
        summary = " · ".join(bits)
        if status_prefix:
            self.status_var.set(f"{status_prefix} — {summary}")
        else:
            self.status_var.set(summary)

    def _provenance_filter_value(self) -> Optional[str]:
        raw = self.provenance_var.get().strip()
        if not raw or raw == ALL:
            return None
        low = raw.casefold()
        if "yellow" in low or "extra" in low:
            return PROVENANCE_EXTRA
        if "green" in low or "backup" in low:
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
                    machine,
                    date,
                    r["source_type"] or "",
                    control or "",
                    r["source_path"] or "",
                    format_location(r),
                ),
                tags=(tag,),
            )

    # --- row actions ------------------------------------------------------------

    def _selected_row(self):
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            idx = int(sel[0])
        except ValueError:
            return None
        if idx < 0 or idx >= len(self._result_rows):
            return None
        return self._result_rows[idx]

    def _on_tree_context(self, event) -> None:
        row_id = self.tree.identify_row(event.y)
        if row_id:
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
        row = self._selected_row()
        if row is None:
            messagebox.showinfo("Extract", "Select a search result first.")
            return
        backup = self.backup_var.get().strip()
        target = self.target_var.get().strip()
        if not backup:
            backup = self._backup_root_from_db() or ""
        keys = row.keys() if hasattr(row, "keys") else ()
        scan_root = str(row["scan_root"]) if "scan_root" in keys and row["scan_root"] else ""
        # Extra-folder rows resolve via scan_root; backup folder still preferred for backup rows
        if not backup and not scan_root:
            messagebox.showerror(
                "Backup folder",
                "Set the backup folder (needed to resolve relative source paths).",
            )
            return
        if backup and not Path(backup).is_dir() and not scan_root:
            messagebox.showerror(
                "Backup folder",
                "Set the backup folder (needed to resolve relative source paths).",
            )
            return
        if not target:
            messagebox.showerror("Target folder", "Set the target folder for extracts.")
            return

        suggested = default_extract_filename(row)
        out = filedialog.asksaveasfilename(
            title="Save extracted program",
            initialdir=target,
            initialfile=suggested,
            defaultextension=".nc",
            filetypes=[("NC / text", "*.nc *.txt"), ("All", "*.*")],
        )
        if not out:
            return
        try:
            path = extract_to_path(row, out, backup_root=backup)
        except ExtractError as exc:
            messagebox.showerror("Extract failed", str(exc))
            return
        self.status_var.set(f"Extracted → {path}")
        messagebox.showinfo("Extracted", f"Wrote:\n{path}")

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
