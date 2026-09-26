# Indexer manual (`can_index=yes`)

**Audience:** people who **build and maintain** the program database from CNC backup trees.  
**Capability:** set `can_index = yes` in `gcode-index.ini` next to the exe (indexer PC).

Operators on shop PCs should use `can_index = no` and the operator manual.

Legacy note: older installs with `[ui] mode=full` map to `can_index=yes`.

---

## Role of the indexer

With `can_index=yes` the GUI can:

- Scan backup trees and write / update `gcode_index.sqlite`
- Add **green** (on-machine) and **yellow** (extra) scan roots
- Run **auto-index** on a schedule while the GUI stays open
- Map odd folder names to machines and edit **local aliases**
- Use advanced filters, presets, compare, scan report, duplicates
- Optionally write Excel after a scan
- Use Windows **autostart** / **tray** helpers

Indexer layout uses two primary navigation segments (large bar at the top):

| Tab | Contents |
|-----|----------|
| **Work / Praca** | Search / filters / **results table** \| **full-height preview on the right** — clean retrieve surface. One-line path summary + **Folders…** to open Index. Primary CTA: **Extract**. |
| **Index / Indeks** | Backup/DB/extract folders, green/yellow extras, path remap, **Index/scan**, Map, Machines & aliases, incremental, watch, schedule, history, autostart/tray, report/duplicates/Excel |

Floor clients (`can_index=no`) stay on a single retrieve surface — no Praca/Indeks tabs.

In the preview pane, use **In preview** to find text in the G-code body (next/prev + highlight).

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

**Nested roots:** the **deepest** configured root (main backup or green/yellow) that contains a file owns it — that root’s colour and `scan_root` apply. Example: yellow parent + green child → files under the child are **green only** (no duplicate yellow row). Adding a root inside another shows a short note that the child overrides the parent colour.

### Folder colours & aliases

**Kolory folderów…** / **Folder colours…** (indexer) edits `folder_colour_aliases.yaml` next to the database:

1. **Colours** — add / edit / remove colour entries (`id`, labels PL+EN, swatch `#RRGGBB`, badge, meaning text). Seeded: green (`backup`), yellow (`extra`), red (`wip`). Built-ins cannot be deleted; meanings and names are editable. Add more (e.g. orange = quarantine).
2. **Folder aliases** — folder-name → chosen colour **or exclude**. Deepest matching path segment wins (also inside the main backup).

Results Flag column and the flag filter use the catalogue (badges + swatch colours), not only the three hard-coded seeds.

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

Set **Auto-index**: amount + unit (seconds / minutes / hours / days), e.g. 15 minutes. While the GUI stays open, due scans run automatically. Floor clients (`can_index=no`) never run this.

A live **countdown** to the next run appears beside it (`In m:ss` / `h:mm:ss`, refreshing every second). Changing amount or unit **restarts** the timer immediately. While a scan runs, status shows **Auto-indexing…**.

### Watch folders

Tick **Watch folders** to watch the backup tree and extra (green/yellow) roots. When new or changed indexable files appear, the app waits a short debounce, then runs an **incremental** scan (no full rebuild).

Next to the checkbox, choose the watch **method** (segmented control):

| Method | Behavior |
|--------|----------|
| **Auto** (`watch_mode=hybrid`) | OS filesystem **events** on local disks; stamp-**poll** on network/UNC shares (`Z:\…`, `\\server\share`) |
| **Poll only** (`watch_mode=poll`) | Stamp-poll everywhere (previous safe behavior) |

The watch status strip shows which method is active per root (e.g. `D:\CNC=events · Z:\Share=poll`). Choice is saved in `gcode-index.ini` → `[scan] watch_mode`.

- Only available when `can_index=yes`.
- Takes a `gcode_index.lock` next to the database so **one PC** owns watching/indexing. Other indexer instances see “Watch locked” if they try to enable it. Floor clients never take the lock.
- Prefer: one indexer PC with Watch on; other PCs use `can_index=no` against the same DB.
- A compact **Watch** status strip under the toolbar shows last poll time, files seen (stamp count), last incremental run, per-root method, and who holds `gcode_index.lock`.

### Autostart and tray (Windows)

On the third toolbar row (Windows builds):

- **Start at Windows logon** — installs or removes either a Startup-folder shortcut or a Task Scheduler “at logon” entry (choose **Method**). Preference is saved in `gcode-index.ini` under `[desktop]`.
- **Close to tray** — the window **X** hides to the system tray instead of quitting. Double-click the tray icon (or **Restore**) brings the window back; **Quit** on the tray menu exits for real.
- **Minimize to tray** — iconify also hides to the tray.

Turn **Close to tray** off if you want **X** to quit. Floor clients always quit on close and have no tray/autostart controls.

The GUI is **single-instance**: launching again (including while it sits in the tray) restores the existing window instead of starting a second process.

---

## Search and extract

Same find bar as the floor client, plus:

- **Include unassigned** / **Uwzględniaj nieprzypisane** (default **ON**) — when a machine multi-select is active, keep **MACHINE UNKNOWN** / `unmapped:…` rows in the results. Turning OFF shows a confirm warning. Saved as `[scan] include_unknown` in `gcode-index.ini`. Floor clients and locked installs force this **ON** (control disabled).
- **More filters** — source type, control, flag (green/yellow), programmer, presets, **size from/to** (bytes or `10k` / `1.5M`), **file date from/to** (source mtime / creation; calendar via **▾**)
- Click any **results column header** to sort ascending/descending
- **Compare…** — unified diff of exactly two selected rows
- **Duplicates…** — exact groups use **program-body** SHA-256 (`program_sha256`: normalized extract text with `%` frame + LF newlines), so glued dump slices can match loose `.nc` / `.nc.copy` with the same body. Near-duplicates: same program # + similar size, different body hash. Whole-file `content_sha256` is unchanged for extract integrity. **Re-scan** after upgrade to fill `program_sha256` on older rows.
- **Open folder** / **Copy path** on the source file

**Wydobądź / Extract** writes program bodies to the extract folder (or a path you choose). Sources are never modified. Extract checks whole-file SHA-256 (`content_sha256`) + size from scan time.

---

## Scan history

**Scan history…** (indexer only) lists the last index runs from `scan_history.json` next to the database: when, duration, programs, files **added / updated / removed / unchanged**. Survives DB rebuilds — useful when diagnosing network spikes during incremental scans.

## Operator lock (floor deploy)

Shop PCs should stay retrieve-only. Either:

- set `[capabilities] settings_locked = yes` in `gcode-index.ini`, or
- place an empty `operator.lock` (or `can_index.lock`) next to the ini / exe.

When locked, `can_index` is forced to **no** even if the ini says yes. Remove the lock only on the indexer PC.

## Auto-refresh search (clients after incremental index)

Tick **Auto-refresh results** / **Odświeżaj wyniki** to **re-run the current search** when `gcode_index.sqlite` changes (mtime poll, default ~20 s). Useful on floor clients that open a **network** copy of the DB while the indexer runs Watch / scheduled incremental scans: new rows appear without clearing filters or reopening the file. Saved as `search_auto_refresh` / `search_auto_refresh_s` in the ini. Without it, operators click Search again after the indexer finishes.

## Instance settings

`gcode-index.ini` next to the exe remembers folders, greens/yellows, **`can_index`**, language, schedule, desktop prefs, and window size.  
Every available key is commented in `gcode-index.ini.example`. Override path with env `GCODE_INDEX_INI=…`.

Deploy:

- Shop / floor PCs → `can_index = no`
- Indexer PC → `can_index = yes`

---

## Haas NGC zip backups

Do **not** expect the scanner to open `.zip` files. Unzip Haas NGC backups into the machine folder first (e.g. `…/HaasBackup(…)/Memory/**/*.nc`), then scan.

---

## Floor clients

There is no runtime **Mode** switch. Put `can_index = no` in that PC’s `gcode-index.ini` so operators only open the DB, search, and extract. See the **Operator (retrieve) manual**.
