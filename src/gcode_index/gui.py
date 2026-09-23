"""Windows-friendly tkinter GUI for scan / live search / extract.

Stdlib only (no MSVC / extra GUI wheels). Launch::

    gcode-index-gui
    python -m gcode_index.gui
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from gcode_index.aliases import AliasMap, default_aliases_path
from gcode_index.db import (
    format_location,
    list_instances,
    open_db,
    query_digit_count,
    search_instances,
    write_scan_result,
)
from gcode_index.excel_export import export_excel
from gcode_index.extract import (
    ExtractError,
    default_extract_filename,
    extract_to_path,
)
from gcode_index.scanner import scan_backup_tree

log = logging.getLogger(__name__)

SEARCH_DEBOUNCE_MS = 200
MIN_DIGITS = 4
DEFAULT_DB_NAME = "gcode_index.sqlite"
BROWSE_LIMIT = 500


class IndexerApp(tk.Tk):
    """Main window: backup + target folders, scan, live search, extract."""

    def __init__(self) -> None:
        super().__init__()
        self.title("G-code Backup Indexer")
        self.minsize(960, 520)
        self.geometry("1180x620")

        self.backup_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(
            value="Pick a backup folder and a target folder for the database."
        )

        self._search_after_id: Optional[str] = None
        self._result_rows: list = []
        self._scan_busy = False

        self._build()
        self.search_var.trace_add("write", self._on_search_changed)

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
        ttk.Button(actions, text="Show all in DB", command=self._browse_all).pack(
            side=tk.LEFT, padx=4
        )
        self.excel_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions, text="Also write Excel", variable=self.excel_var).pack(
            side=tk.LEFT
        )

        search_frame = ttk.LabelFrame(
            root, text="Search (≥4 digits in program #, part #, or path) — empty = browse",
            padding=8,
        )
        search_frame.pack(fill=tk.X, **pad)
        ttk.Label(search_frame, text="Query").pack(side=tk.LEFT)
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(search_frame, text="Extract selected…", command=self._extract_selected).pack(
            side=tk.LEFT
        )

        cols = ("program", "part", "machine", "date", "type", "path", "location")
        tree_frame = ttk.Frame(root)
        tree_frame.pack(fill=tk.BOTH, expand=True, **pad)
        self.tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings", selectmode="browse"
        )
        headings = {
            "program": ("Program #", 90),
            "part": ("Part number", 160),
            "machine": ("Machine", 120),
            "date": ("Date", 140),
            "type": ("Source type", 110),
            "path": ("Source path", 320),
            "location": ("In-file location", 150),
        }
        for key, (label, width) in headings.items():
            self.tree.heading(key, text=label)
            stretch = key in ("path", "part")
            self.tree.column(key, width=width, stretch=stretch, minwidth=60)
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _e: self._extract_selected())

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
        self.search_var.set("")
        self._browse_all()

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
        self.status_var.set("Scanning…")
        write_excel = bool(self.excel_var.get())
        threading.Thread(
            target=self._scan_worker,
            args=(Path(backup), Path(target), write_excel),
            daemon=True,
        ).start()

    def _scan_worker(self, backup: Path, target: Path, write_excel: bool) -> None:
        try:
            aliases_path = default_aliases_path()
            alias_map = AliasMap.load(aliases_path)
            result = scan_backup_tree(backup, alias_map)
            db_path = target / DEFAULT_DB_NAME
            # Fresh DB each scan so the table matches this backup pass.
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
            conn.close()
            excel_note = ""
            if write_excel:
                xlsx = target / "gcode_index.xlsx"
                export_excel(xlsx, result.instances)
                excel_note = f"; Excel → {xlsx.name}"
            msg = (
                f"Indexed {len(result.instances)} programs "
                f"[{type_note}] "
                f"({len(result.unknowns)} unknown folders) → {db_path.name} "
                f"(run {run_id[:8]}…){excel_note}"
            )
            self.after(0, lambda: self._scan_done(True, msg))
        except Exception as exc:  # noqa: BLE001 — show in UI
            log.exception("scan failed")
            self.after(0, lambda: self._scan_done(False, str(exc)))

    def _scan_done(self, ok: bool, message: str) -> None:
        self._scan_busy = False
        self.scan_btn.configure(state=tk.NORMAL)
        self.status_var.set(message)
        if not ok:
            messagebox.showerror("Scan failed", message)
        else:
            # Clear search so we browse all indexed rows (including loose .nc).
            self.search_var.set("")
            self._browse_all(status_prefix=message)

    # --- search / browse --------------------------------------------------------

    def _on_search_changed(self, *_args) -> None:
        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
        self._search_after_id = self.after(SEARCH_DEBOUNCE_MS, self._run_search_now)

    def _browse_all(self, status_prefix: Optional[str] = None) -> None:
        """Fill the table with newest DB rows (no digit query required)."""
        self._search_after_id = None
        self.tree.delete(*self.tree.get_children())
        self._result_rows = []

        db_path = self._db_path()
        if db_path is None or not db_path.is_file():
            self.status_var.set("No database yet — run a scan or open an existing DB.")
            return

        try:
            conn = open_db(db_path)
            try:
                rows = list_instances(conn, limit=BROWSE_LIMIT)
                total = conn.execute("SELECT COUNT(*) FROM program_instances").fetchone()[0]
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Browse error: {exc}")
            return

        self._fill_tree(rows)
        shown = len(rows)
        base = (
            f"Showing {shown} of {total} indexed program(s)"
            if total > shown
            else f"Showing all {total} indexed program(s)"
        )
        if status_prefix:
            self.status_var.set(f"{status_prefix} — {base}")
        else:
            self.status_var.set(base)

    def _run_search_now(self) -> None:
        self._search_after_id = None
        query = self.search_var.get().strip()

        if not query:
            self._browse_all()
            return

        self.tree.delete(*self.tree.get_children())
        self._result_rows = []

        if query_digit_count(query) < MIN_DIGITS:
            self.status_var.set(
                f"Type at least {MIN_DIGITS} digits to search "
                f"(or clear the box to browse all)."
            )
            return

        db_path = self._db_path()
        if db_path is None or not db_path.is_file():
            self.status_var.set("No database yet — run a scan or open an existing DB.")
            return

        try:
            conn = open_db(db_path)
            try:
                rows = search_instances(conn, query, limit=200)
            finally:
                conn.close()
        except ValueError as exc:
            self.status_var.set(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Search error: {exc}")
            return

        self._fill_tree(rows)
        self.status_var.set(f"{len(rows)} match(es) for {query!r}")

    def _fill_tree(self, rows: list) -> None:
        self._result_rows = rows
        for i, r in enumerate(rows):
            date = str(r["backup_date"] or "")[:19].replace("T", " ")
            machine = r["machine_label"] or r["machine_id"] or ""
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
                    r["source_path"] or "",
                    format_location(r),
                ),
            )

    # --- extract ----------------------------------------------------------------

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
