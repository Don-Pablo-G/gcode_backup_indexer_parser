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

from gcode_index.aliases import AliasMap, default_aliases_path
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
from gcode_index.path_util import (
    format_eta,
    open_path_in_file_manager,
    resolve_source_abspath,
)
from gcode_index.scanner import scan_backup_tree

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

        actions = ttk.Frame(root)
        actions.pack(fill=tk.X, **pad)
        self.scan_btn = ttk.Button(actions, text="Run index / scan", command=self._start_scan)
        self.scan_btn.pack(side=tk.LEFT)
        ttk.Button(actions, text="Open existing DB…", command=self._pick_existing_db).pack(
            side=tk.LEFT, padx=8
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

        row_actions = ttk.Frame(filt)
        row_actions.grid(row=2, column=6, sticky=tk.E, pady=(6, 0))
        ttk.Button(row_actions, text="Open folder", command=self._open_selected_folder).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(row_actions, text="Copy path", command=self._copy_selected_path).pack(
            side=tk.LEFT, padx=2
        )

        hint = ttk.Label(
            filt,
            text="Text is case-insensitive. Empty machine selection = all machines. "
            "MACHINE UNKNOWN = files with no matching machine folder. "
            "Right-click a row for Open folder / Copy path. "
            "Extract refuses if the source file changed since the scan (SHA-256).",
            foreground="#444",
        )
        hint.grid(row=3, column=0, columnspan=7, sticky=tk.W, pady=(6, 0))

        filt.columnconfigure(1, weight=1)

        cols = ("program", "part", "machine", "date", "type", "control", "path", "location")
        tree_frame = ttk.Frame(root)
        tree_frame.pack(fill=tk.BOTH, expand=True, **pad)
        self.tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings", selectmode="browse"
        )
        headings = {
            "program": ("Program #", 90),
            "part": ("Part number", 150),
            "machine": ("Machine", 120),
            "date": ("Date", 130),
            "type": ("Source type", 110),
            "control": ("Control", 80),
            "path": ("Source path", 280),
            "location": ("In-file location", 140),
        }
        for key, (label, width) in headings.items():
            self.tree.heading(key, text=label)
            stretch = key in ("path", "part")
            self.tree.column(key, width=width, stretch=stretch, minwidth=50)
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

    def _pick_existing_db(self) -> None:
        path = filedialog.askopenfilename(
            title="Open existing gcode_index.sqlite",
            filetypes=[("SQLite", "*.sqlite *.db"), ("All", "*.*")],
        )
        if not path:
            return
        db = Path(path)
        self.target_var.set(str(db.parent))
        self.status_var.set(f"Using existing DB: {db}")
        self._refresh_filter_choices()
        self._clear_filters()

    def _db_path(self) -> Optional[Path]:
        target = self.target_var.get().strip()
        if not target:
            return None
        return Path(target) / DEFAULT_DB_NAME

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
        self._scan_busy = True
        self.scan_btn.configure(state=tk.DISABLED)
        self.progress_var.set(0.0)
        self.progress_label_var.set("Starting…")
        self.status_var.set("Scanning…")
        write_excel = bool(self.excel_var.get())
        threading.Thread(
            target=self._scan_worker,
            args=(Path(backup), Path(target), write_excel),
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

    def _scan_worker(self, backup: Path, target: Path, write_excel: bool) -> None:
        try:
            aliases_path = default_aliases_path()
            alias_map = AliasMap.load(aliases_path)
            result = scan_backup_tree(backup, alias_map, progress=self._on_scan_progress)
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
            msg = (
                f"Indexed {len(result.instances)} programs "
                f"[{type_note}] "
                f"({len(result.unknowns)} unknown folders{unk_note}) → {db_path.name} "
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
            seed = AliasMap.load(default_aliases_path()).known_machine_displays()
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
        summary = " · ".join(bits)
        if status_prefix:
            self.status_var.set(f"{status_prefix} — {summary}")
        else:
            self.status_var.set(summary)

    def _fill_tree(self, rows: list) -> None:
        self._result_rows = rows
        for i, r in enumerate(rows):
            date = format_display_date(r["backup_date"])
            machine = r["machine_label"] or r["machine_id"] or ""
            keys = r.keys() if hasattr(r, "keys") else ()
            control = r["control_family"] if "control_family" in keys else ""
            self.tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(
                    r["program_number"] or "",
                    r["part_number"] or "",
                    machine,
                    date,
                    r["source_type"] or "",
                    control or "",
                    r["source_path"] or "",
                    format_location(r),
                ),
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
        return resolve_source_abspath(sp, backup or None)

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
        if not backup or not Path(backup).is_dir():
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


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    app = IndexerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
