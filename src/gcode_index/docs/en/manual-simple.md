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

1. Set language if needed (**Settings** / **Ustawienia** → **Language** → `pl` or `en`).
2. Confirm this PC’s `gcode-index.ini` has `can_index = no` (default for shop copies).
3. Click the green **Open existing DB…** / **Otwórz istniejącą bazę…** and pick `gcode_index.sqlite`.

The database folder must also contain **`folder_colour_aliases.yaml`** so Flag colours match the shop catalogue. Without it you get a status warning and seed colours only. Keep **`folder_tree_map.yaml`** too if Flag hover tips should show path reasons. Do not expect `can_index` inside the shared pack.

Optional: under **Change…** / **Zmień…** set an **extract folder** for Wydobądź output (blank = same folder as the open database). Floor clients have **no** backup or database folder pickers — use **Open existing DB…** to choose the catalog.

---

## Find a program

1. Type in **Text** — program #, part #, or path fragment (e.g. `O03232`, `3232`, `P-00253232`). Search is case-insensitive; `O03232` / `03232` / `3232` match the same O-number.
2. Optionally open **Machines** and multi-select (Ctrl/Shift+click). Empty / all = every machine.
3. Optionally set **Date from / to** as `DD.MM.YYYY` (or open the small calendar via **▾** next to each field).
4. Tick **Newest only** / **Tylko najnowsze** to keep one row per program + machine (latest date).
5. **Include unassigned** / **Uwzględniaj nieprzypisane** stays **ON** and **locked** on floor clients — when you filter by machine, **MACHINE UNKNOWN** / unmapped rows still appear. (Indexer PCs can turn this off after a confirm warning; preference is `include_unknown` in the ini, default yes.)
6. Optionally tick **Hide duplicates** / **Ukryj duplikaty** — one row per identical program-body checksum (SHA); prefers green, then newest. Optionally tick **Only green** / **Tylko zielone** to keep rows whose Flag disc is green (hides yellow and override colours).
7. **More filters ▾** opens an advanced panel under the find bar (same as the indexer): source type, control, status, role, odbiorca, named **views**, size and file-date ranges. Click again (**Fewer filters ▴**) to hide — values stay applied. Open/closed is remembered in the ini.
8. Click a **column header** in the results table to sort ascending/descending (click again to flip).

Results appear in the table. **Preview** stays docked on the **right** (full height, resizable) — not under the table.

---

## Extract (Wydobądź)

1. Select one or more rows (Ctrl/Shift+click for several).
2. Click green **Extract selected…** / **Wydobądź zaznaczone…**, or double-click a row.  
   Right-click also offers extract / open folder / copy path.
3. Choose the save location (defaults to the extract folder).

If the source file is **missing on disk** (column **Source = MISSING**) or changed since the last index, extract is **refused** with a clear message — ask someone on the **indexer PC** (`can_index=yes`) to re-scan (or check path remap).

## Find in preview

Select a result row and open **Preview…**. Use **In preview** above the text to search inside the body — **▲** / **▼** (or Enter / Shift+Enter) move between matches; hits are highlighted. **Extract to…** on the preview action row writes the viewed program to a folder you choose (same as right-click on results).

---

## Flags in the results

| Column / colour | Meaning |
|-----------------|--------|
| **Green** machine flag (provenance) | From machine — main backup (**from backup**) or trusted catch (**trusted folder**) |
| **Yellow** | Status unknown — extra (non-backup) folder |
| **Source = MISSING** (red row) | Source file gone from disk since the last scan — still in the DB, but extract / preview will fail |
| **MACHINE UNKNOWN** | Path did not match a known machine name or alias |

These were assigned when the database was built on the indexer. Floor clients only read them. The **Source** column with **MISSING** is visible here too.

---

## Indexing happens on another PC

There is no **Mode** switch in the GUI. Shop PCs keep `can_index=no`; the indexer PC uses `can_index=yes` in its own `gcode-index.ini`.  
See the **Indexer manual** in the Help menu.

## Path remap (client)

If the index was built on a server as **C:** and this PC sees the same share as **Z:** (or you have several shares), open **Change…** → **Path remap (client)** and **Add…** one or more rules:

- **Prefix in index** = `C:\…` (as stored in the DB / `scan_root`)
- **Local prefix** = `Z:\…` (as on this PC)

Several rules are allowed — **longest matching prefix wins**. Applies to the main backup and green/yellow roots under that prefix. Search works without remap; **Extract** / preview use it. Saved in `gcode-index.ini` → `[path_remap]`.

On the indexer PC the same editor lives under **Indeks → Folders** (aligned with floor **Change…**). **Mapping…** is pack teach only.

Right-click a result → **Extract to…** to pick a destination folder (recent folders are remembered).

---

## After the indexer updates the database

When the indexer PC runs an **incremental** scan (Watch folders or safety rescan), it rewrites `gcode_index.sqlite` on the shared path. Floor clients do **not** need to close the DB or clear the find bar:

1. Tick **Auto-refresh results** / **Odświeżaj wyniki** (saved as `search_auto_refresh` in the ini; poll interval `search_auto_refresh_s`, default ~20 s).
2. When the DB file’s mtime changes, the app **re-runs the current search** with the same text, machines, dates, and filters.
3. New / updated / removed programs from the incremental scan show up in the table automatically.

Without auto-refresh, click **Search** again (or change a filter) after the indexer finishes.

## Operator lock

If this PC has `operator.lock` / `can_index.lock` beside the ini or exe, or `settings_locked=yes` in the ini, it stays retrieve-only even if someone edits `can_index=yes`. There is **no** Prosty/Pełny (Simple/Full) mode switch — capability is only `can_index` + lock.

## Pack hygiene (floor)

Open the **shared database folder**, not a lone sqlite copy. Keep `folder_colour_aliases.yaml` (and preferably `folder_tree_map.yaml`) beside `gcode_index.sqlite`. Your PC’s `gcode-index.ini` stays local — never put `can_index` in the shared pack. Prefer a separate **extract** folder so Wydobądź output does not clutter the pack.

Day-to-day index maintenance (Watch / Incremental vs Full / weekly quality check) lives on the indexer PC — see **Day-to-day database hygiene** in the Indexer manual.

For how the indexer should name folders and place backup / green / yellow trees so Flag colours and aliases stay correct on your PC, see **Help → Naming & placement…** (or the Indexer manual chapter **Naming & placement**).

## Tips

- Empty search + filters still lists rows (useful with Newest only).
- Column **Source** / **Lokalizacja** show where the program lives inside glued dumps.
- When results look empty: confirm the correct DB is open and that the indexer recently scanned.
- Every setting is documented (commented) in `gcode-index.ini.example`.
