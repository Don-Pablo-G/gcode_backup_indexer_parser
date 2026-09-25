# Operator manual — Simple mode (Prosty)

**Audience:** shop-floor operators who need to **find and extract** a program from an existing index.  
**Mode:** **Prosty / Simple** (default). This mode does **not** build or update the database.

---

## What this app does

The indexer stores a catalog of CNC programs found in machine backups: program number, part number, machine, date, and where the program lives on disk.  
In Simple mode you **open that catalog**, search, preview, and **extract** (Wydobądź) a program file for another tool or the machine.

You never change the backup files. Extract always writes to a separate folder.

---

## First steps

1. Set language if needed (**Język / Language** → `pl` or `en`).
2. Stay in **Prosty / Simple** (or switch back to it via **Tryb / Mode**).
3. Click the green **Open existing DB…** / **Otwórz istniejącą bazę…** and pick `gcode_index.sqlite`.

Optional: under **Change…** / **Zmień…** set an **extract folder** for Wydobądź output (blank = same folder as the open database). Simple mode has **no** backup or database folder pickers — use **Open existing DB…** to choose the catalog.

---

## Find a program

1. Type in **Text** — program #, part #, or path fragment (e.g. `O03232`, `3232`, `P-00253232`). Search is case-insensitive; `O03232` / `03232` / `3232` match the same O-number.
2. Optionally open **Machines** and multi-select (Ctrl/Shift+click). Empty / all = every machine.
3. Optionally set **Date from / to** as `DD.MM.YYYY` (or open the small calendar via **▾** next to each field).
4. Tick **Newest only** / **Tylko najnowsze** to keep one row per program + machine (latest date).
5. Click a **column header** in the results table to sort ascending/descending (click again to flip).

Results appear in the table. The **Preview** pane on the right shows the selected program body.

---

## Extract (Wydobądź)

1. Select one or more rows (Ctrl/Shift+click for several).
2. Click green **Extract selected…** / **Wydobądź zaznaczone…**, or double-click a row.  
   Right-click also offers extract / open folder / copy path.
3. Choose the save location (defaults to the extract folder).

If the source file changed since the last index, extract may be refused — ask someone with **Full** mode to re-scan.

---

## Flags in the results

| Column / colour | Meaning |
|-----------------|--------|
| **Green** machine flag (provenance) | From the main backup / on-machine catch |
| **Yellow** | From an extra (non-backup) folder |
| **MACHINE UNKNOWN** | Path did not match a known machine name or alias |

These were assigned when the database was built (Full mode). Simple mode only reads them.

---

## Switching to Full mode
## Path remap (client)

If the index was built on a server as **C:** and this PC sees the same share as **Z:**, open **Change…** and set **Path remap (client)**:

- **Prefix in index** = `C:\…` (as stored in the DB / `scan_root`)
- **Local prefix** = `Z:\…` (as on this PC)

Applies to the main backup and green/yellow roots under that prefix. Search works without remap; **Extract** / preview use it. Saved in `gcode-index.ini` → `[path_remap]`.


Switching to **Full** requires a PIN (4–12 digits) set on this PC.


Use **Tryb / Mode → Pełny / Full** when you need to **index / scan**, map folders, edit aliases, or change auto-index.  
See the **Indexer (Full mode) manual** from the Help menu.

---

## Tips

- Settings for this PC are stored in `gcode-index.ini` next to the exe.
- **Clear filters** resets the find bar.
- If search is empty, ask whether the right database was opened and whether Full mode has scanned recently.
