# Indexer manual — Full mode (Pełny)

**Audience:** people who **build and maintain** the program database from CNC backup trees.  
**Mode:** **Pełny / Full**.

Operators who only search and extract should use **Simple mode** and the operator manual.

---

## Role of Full mode

Full mode can:

- Scan backup trees and write / update `gcode_index.sqlite`
- Add **green** (on-machine) and **yellow** (extra) scan roots
- Run **auto-index** on a schedule while the GUI stays open
- Map odd folder names to machines and edit **local aliases**
- Use advanced filters, presets, compare, scan report, duplicates
- Optionally write Excel after a scan

Full mode uses two tabs:

| Tab | Contents |
|-----|----------|
| **Work** | Search / filters / **results table** \| **full-height preview on the right** — Prosty-like density, no fat folder strips. One-line path summary + button to Index. Primary CTA: **Extract**. |
| **Index** | Backup/DB/extract folders, green/yellow extras, path remap, **Index/scan**, Map, Machines & aliases, incremental, watch, schedule, autostart/tray, watch status strip, report/duplicates/Excel |

---




## Path remap (client)

If the index was built on a server as **C:** and this PC sees the same share as **Z:**, open **Change…** and set **Path remap (client)**:

- **Prefix in index** = `C:\…` (as stored in the DB / `scan_root`)
- **Local prefix** = `Z:\…` (as on this PC)

Applies to the main backup and green/yellow roots under that prefix. Search works without remap; **Extract** / preview use it. Saved in `gcode-index.ini` → `[path_remap]`.

## Folders

| Folder | Purpose |
|--------|---------|
| **Backup folder** | Main CNC backup tree (`DATE\MACHINE\…`) |
| **Database folder** (`target`) | `gcode_index.sqlite` + sidecar files (`machine_folders.yaml`, `aliases.local.yaml`, `ui_settings.yaml`, …) |
| **Extract folder** | Default output for Wydobądź (blank = same as database folder) |

Browsing for backup / database / extract keeps the folder panel **open** so you can finish all paths. Collapse with **Done** / **Gotowe** when finished (or when a scan starts).

### Extra roots

- **Green** — treat like on-machine / catch folders for loose `.nc` (before backup misses them). Subfolders are scanned recursively. Programs get a **green** provenance flag.
- **Yellow** — extra trees not from the machine backup. Programs get a **yellow** flag.

Roots are saved as `extra_scan_roots.yaml` next to the database (and in `gcode-index.ini`).

---

## Map folders and aliases

1. **Map folders…** — discovers `<date>/<machine>` folders, auto-matches known aliases, and lists only unmatched names for manual assign. Map is saved as `machine_folders.yaml` (wins over aliases).
2. Optional: save assignments as **local aliases** (`aliases.local.yaml`) for later scans.
3. **Machines & aliases…** — machine list on the left; select one to edit its **folder aliases**, label, control, and layout. **Add machine** / **Remove machine** manage shop-local machines. Bundled catalog spellings stay read-only (`[bundled]`); add a local spelling to customize. Saved as `aliases.local.yaml`.

### Loose `.nc` machine assignment

When indexing individual `.nc` / `.nc.copy` files, the scanner walks parent folders **deepest → shallowest**. The first folder name that matches the folder map or an alias becomes the **machine** for that file and everything under that folder. No match → **MACHINE UNKNOWN** (still indexed).

---

## Run index / scan

1. Set backup + database folders (and extras if needed), or use **Open existing DB…** on the toolbar to pick an already-built `gcode_index.sqlite`.
2. Click green **Run index / scan** / **Indeksuj / skanuj**.
3. Options (second toolbar row under **Indeksuj**):
   - **Incremental** — skip unchanged files (size + mtime); reuse previous rows
   - **Also write Excel** — export workbook next to the DB after scan
   - **Watch folders** — see below
4. Progress shows file count and ETA. A **scan report** opens when finished (also via **Scan report…** on the same row).

### Auto-index

In Full mode, set **Auto-index** (right side of the second toolbar row) to an interval (seconds / minutes / hours / days), e.g. 15 minutes. While the GUI stays open, due scans run automatically. Simple mode hides and disables this.

### Watch folders

On the **second** Full-mode toolbar row, tick **Watch folders** to poll the backup tree and extra (green/yellow) roots every few seconds. When new or changed indexable files appear, the app waits a short debounce, then runs an **incremental** scan (no full rebuild).

- Only available in **Full** mode.
- Takes a `gcode_index.lock` next to the database so **one PC** owns watching/indexing. Other Full instances see “Watch locked” if they try to enable it. Prosty clients never take the lock.
- Prefer: one indexer PC with Watch on; other PCs use Simple mode against the same DB.
- A compact **Watch** status strip under the toolbar shows last poll time, files seen (stamp count), last incremental run, and who holds `gcode_index.lock`.

### Autostart and tray (Windows)

On the **third** Full-mode toolbar row (Windows builds):

- **Start at Windows logon** — installs or removes either a Startup-folder shortcut or a Task Scheduler “at logon” entry (choose **Method**). Preference is saved in `gcode-index.ini` under `[desktop]`.
- **Close to tray** — the window **X** hides to the system tray instead of quitting. Double-click the tray icon (or **Restore**) brings the window back; **Quit** on the tray menu exits for real.
- **Minimize to tray** — iconify also hides to the tray.

Turn **Close to tray** off if you want **X** to quit. Simple mode always quits on close and has no tray/autostart controls.

---

## Search and extract

Same find bar as Simple mode, plus:

- **More filters** — source type, control, flag (green/yellow), programmer, presets, **size from/to** (bytes or `10k` / `1.5M`), **file date from/to** (source mtime / creation; calendar via **▾**)
- Click any **results column header** to sort ascending/descending (both modes)
- **Compare…** — unified diff of exactly two selected rows
- **Duplicates…** — exact and near-duplicate groups
- **Open folder** / **Copy path** on the source file

**Wydobądź / Extract** writes program bodies to the extract folder (or a path you choose). Sources are never modified. Extract checks SHA-256 + size from scan time.

---

## Instance settings

`gcode-index.ini` next to the exe remembers folders, greens/yellows, language, mode, schedule, and window size. Override path with env `GCODE_INDEX_INI=…`.

---

## Haas NGC zip backups

Do **not** expect the scanner to open `.zip` files. Unzip Haas NGC backups into the machine folder first (e.g. `…/HaasBackup(…)/Memory/**/*.nc`), then scan.

---

## Switching to Simple mode

**Tryb / Mode → Prosty / Simple** hides indexing UI so operators only open the DB, search, and extract. See the **Operator (Simple mode) manual**.
