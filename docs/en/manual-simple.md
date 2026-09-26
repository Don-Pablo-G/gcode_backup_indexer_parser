# Operator manual — floor client (`can_index=no`)

**Audience:** shop-floor operators who need to **find and extract** a program from an existing index.  
**Capability:** set `can_index = no` in `gcode-index.ini` next to the exe (shop / floor PCs). This install does **not** build or update the database.

Legacy note: older installs with `[ui] mode=simple` map to `can_index=no`.

---

## What this app does

The indexer stores a catalog of CNC programs found in machine backups: program number, part number, machine, date, and where the program lives on disk.  
On a floor client you **open that catalog**, search, preview, and **extract** (Wydobądź) a program file for another tool or the machine.

You never change the backup files. Extract always writes to a separate folder.

---

## First steps

1. Set language if needed (**Język / Language** → `pl` or `en`).
2. Confirm this PC’s `gcode-index.ini` has `can_index = no` (default for shop copies).
3. Click the green **Open existing DB…** / **Otwórz istniejącą bazę…** and pick `gcode_index.sqlite`.

Optional: under **Change…** / **Zmień…** set an **extract folder** for Wydobądź output (blank = same folder as the open database). Floor clients have **no** backup or database folder pickers — use **Open existing DB…** to choose the catalog.

---

## Find a program

1. Type in **Text** — program #, part #, or path fragment (e.g. `O03232`, `3232`, `P-00253232`). Search is case-insensitive; `O03232` / `03232` / `3232` match the same O-number.
2. Optionally open **Machines** and multi-select (Ctrl/Shift+click). Empty / all = every machine.
3. Optionally set **Date from / to** as `DD.MM.YYYY` (or open the small calendar via **▾** next to each field).
4. Tick **Newest only** / **Tylko najnowsze** to keep one row per program + machine (latest date).
5. Click a **column header** in the results table to sort ascending/descending (click again to flip).

Results appear in the table. **Preview** stays docked on the **right** (full height, resizable) — not under the table.

---

## Extract (Wydobądź)

1. Select one or more rows (Ctrl/Shift+click for several).
2. Click green **Extract selected…** / **Wydobądź zaznaczone…**, or double-click a row.  
   Right-click also offers extract / open folder / copy path.
3. Choose the save location (defaults to the extract folder).

If the source file is **missing on disk** (column **Source = MISSING**) or changed since the last index, extract is **refused** with a clear message — ask someone on the **indexer PC** (`can_index=yes`) to re-scan (or check path remap).

## Find in preview

Select a result row to load G-code in the right-hand **Preview**. Use **In preview** above the text to search inside the body — **▲** / **▼** (or Enter / Shift+Enter) move between matches; hits are highlighted.

---

## Flags in the results

| Column / colour | Meaning |
|-----------------|--------|
| **Green** machine flag (provenance) | From the main backup / on-machine catch |
| **Yellow** | From an extra (non-backup) folder |
| **Source = MISSING** (red row) | Source file gone from disk since the last scan — still in the DB, but extract / preview will fail |
| **MACHINE UNKNOWN** | Path did not match a known machine name or alias |

These were assigned when the database was built on the indexer. Floor clients only read them. The **Source** column with **MISSING** is visible here too.

---

## Indexing happens on another PC

There is no **Mode** switch in the GUI. Shop PCs keep `can_index=no`; the indexer PC uses `can_index=yes` in its own `gcode-index.ini`.  
See the **Indexer manual** in the Help menu.

## Path remap (client)

If the index was built on a server as **C:** and this PC sees the same share as **Z:**, open **Change…** and set **Path remap (client)**:

- **Prefix in index** = `C:\…` (as stored in the DB / `scan_root`)
- **Local prefix** = `Z:\…` (as on this PC)

Applies to the main backup and green/yellow roots under that prefix. Search works without remap; **Extract** / preview use it. Saved in `gcode-index.ini` → `[path_remap]`.

---

## Auto-refresh search

Optional: tick **Auto-refresh results** so the table updates when the indexer writes a new database (shared network path). No need to clear or retype the search. Preference is stored in `gcode-index.ini`.

## Operator lock

If this PC has `operator.lock` (or `settings_locked=yes`), it stays retrieve-only even if someone edits `can_index=yes` in the ini.

## Tips

- Empty search + filters still lists rows (useful with Newest only).
- Column **Source** / **Lokalizacja** show where the program lives inside glued dumps.
- When results look empty: confirm the correct DB is open and that the indexer recently scanned.
- Every setting is documented (commented) in `gcode-index.ini.example`.
