# G-code backup indexer / parser

Index CNC machine **backup folder trees** into a portable **SQLite** catalog of **program instances** (program #, part #, machine, date, source location). Full G-code parsing is **out of scope** — this tool extracts **headers + locations only** so humans and other software can search and later extract spans.

**Canonical repo:** https://github.com/Don-Pablo-G/gcode_backup_indexer_parser

**Polski:** [README.pl.md](README.pl.md)

## User manuals

| Document | Audience |
|----------|----------|
| [Operator manual](docs/en/manual-simple.md) | Floor client (`can_index=no`) — search & extract |
| [Indexer manual](docs/en/manual-full.md) | Indexer PC (`can_index=yes`) — build & maintain the database |
| Polish manuals | [docs/pl/](docs/pl/) |

In the GUI: **Help / Pomoc** opens the same manuals (operator vs indexer text matches this PC’s `can_index`). Legacy filenames still say `manual-simple` / `manual-full`; there is **no** Prosty/Pełny mode switch.

## Requirements

- Python **3.11+** (tested on 3.12)
- Windows, Linux, or macOS
- **Windows GUI** uses **tkinter** (included with the official python.org Windows installer)

## Install

```bat
REM Windows (cmd) — from the repo root
python -m pip install -e ".[dev]"
```

```bash
# Linux / macOS / Git Bash
python3 -m pip install -e ".[dev]"
```

Entry points:

| Command | Role |
|---------|------|
| `gcode-index` | CLI: `scan` / `search` / `extract` |
| `gcode-index-gui` | Windows-friendly tkinter GUI |
| `python -m gcode_index` | Same as CLI |
| `python -m gcode_index.gui` | Same as GUI |

## Instance settings (``gcode-index.ini``)

The Windows GUI remembers folders and options in **`gcode-index.ini`** next to ``gcode-index-gui.exe`` (or in the working directory when run from source). Reopening the app restores backup / database / extract / green & yellow scan roots / language / `can_index` / schedule / watch / desktop prefs without re-picking folders.

- Example template in the repo: [`gcode-index.ini.example`](gcode-index.ini.example)
- Override location with env var ``GCODE_INDEX_INI=C:\path\to\gcode-index.ini``
- The GUI also keeps copies next to the **database** folder (`extra_scan_roots.yaml`, `ui_settings.yaml`) so the index stays portable
- **`target`** = database folder · **`extract`** = Wydobądź output (blank → same as `target`)

## Windows GUI (Phase 2)

```bat
gcode-index-gui
REM or:
python -m gcode_index.gui
```

The GUI capability comes from **`gcode-index.ini`** next to the exe (not a runtime Prosty/Pełny switch):

| `can_index` | Who | What you see |
|-------------|-----|----------------|
| **no** (default / shop PCs) | Operators | **Retrieve only** — open existing DB, search, machines, dates, newest-only, **Include unassigned** (locked ON), preview (+ find in preview), **Wydobądź** / Extract. Optional extract folder + path remap + auto-refresh. No scan / index / schedule / watch / map chrome. |
| **yes** (indexer PC) | Indexer | Two nav tabs — **Work / Praca** (search, results, preview) and **Index / Indeks** (folders, scan, map, watch Auto\|Poll, schedule + countdown, history, autostart/tray, report/duplicates/Excel). |

Deploy lock: `settings_locked=yes` or empty `operator.lock` / `can_index.lock` beside the ini forces retrieve-only. Legacy `[ui] mode=simple|full` still loads when `can_index` is absent (`simple`→`no`, `full`→`yes`). See `gcode-index.ini.example` for every setting commented.

### Floor client (`can_index=no`)

1. Click green **Otwórz istniejącą bazę…** / **Open existing DB…** and pick `gcode_index.sqlite`.  
2. Optionally set a separate **extract folder** for Wydobądź output (blank = same folder as the open DB). No backup/database path pickers.  
3. Search / pick machines (popup) / dates; tick **Tylko najnowsze**. **Include unassigned** stays ON (locked) so MACHINE UNKNOWN rows remain when filtering machines.  
4. Select a row → green **Wydobądź** (or double-click). Preview sits **beside** the results table; use **In preview** to find text in the body.  
5. Optional **Auto-refresh results**: when the indexer rewrites the shared DB after an incremental scan, the current search re-runs automatically (~20 s mtime poll).  
6. Indexing happens on the PC with `can_index=yes` (edit that install’s `.ini`). Path remap under **Change…** if this PC sees the backup share under a different drive letter.

### Indexer (`can_index=yes`)

Use the top nav: **Work / Praca** for day-to-day search & extract; **Index / Indeks** for folders and scanning.

1. On **Indeks**: **Browse** → pick the main **backup folder** tree.
2. **Browse** → pick a **database folder** (`gcode_index.sqlite` + sidecar yaml live here).
3. Optionally **Browse** a separate **extract folder** for Wydobądź output (leave blank to write next to the DB).
4. Optionally **Add folder…** under **Extra folders** for other trees to index (and their subfolders).
   - Main backup programs get a **green** flag (ran on the machine / from backup).
   - Extra-folder programs get a **yellow** flag (not from backup / not confirmed run).  
   - Nested roots: the **deepest** configured root that contains a file owns it (child colour wins; no duplicate rows).  
   - **Folder colours** (`folder_colour_aliases.yaml`): define colours (labels, swatch, meaning) + folder-name → colour/exclude aliases; deepest path segment wins.  
   - Extra roots are saved as `extra_scan_roots.yaml` next to the DB.
5. **Path remap (client)** under **Change…** if Extract/preview need a different drive letter than `scan_root` in the DB.
6. Click **Map folders…** (optional but recommended). The app scans `<date>/<machine>` folders, **auto-matches** names it knows from aliases, and lists **only unmatched** folders for manual assign. Subfolders inherit.
   - Map is saved as `machine_folders.yaml` next to the DB (wins over aliases).
   - Optional checkbox: also save assignments as **local aliases** (`aliases.local.yaml` next to the DB) so the same odd folder names auto-match on later scans.
   - First scan prompts only when unmatched folders remain.
   - **Machines & aliases…** opens a **machine list**: select a machine to edit its folder aliases (and label / control / layout). **Add machine** / **Remove machine** manage shop-local machines. Bundled spellings are read-only; add a local spelling to customize. Bundled `aliases.yaml` stays read-only.
7. Click **Run index / scan** (optional Excel export; optional **Incremental**; optional **Auto-index** schedule with live countdown).
   **Watch folders** — method **Auto** (OS events on local disks, stamp-poll on UNC/network) or **Poll only**. One PC holds `gcode_index.lock`.
   **Scan history…** lists recent runs from `scan_history.json` (added/updated/removed/unchanged).
   Windows: **Start at Windows logon**, **Close to tray** / **Minimize to tray**.
   After a successful scan the table lists indexed programs with **source path** and **in-file location**.
8. On **Praca**: **Find programs** with free text (letters, digits, dashes — e.g. `P-00253232 VA` or `O03232`; **case-insensitive**), plus filters:
   - **Machines** (multi-select list — Ctrl/Shift+click; **All** / **None** buttons; empty selection = all machines).
     The list is seeded from `aliases.yaml` + local aliases (so **HAAS UMC750**, ST-20Y, … always appear) plus **MACHINE UNKNOWN**, and merged with machines seen in the last scan.
     VF-2 has three entries (legacy / **nowa** / **stara**); selecting **HAAS VF-2** also matches the nowa/stara ids.
   - **Include unassigned** / **Uwzględniaj nieprzypisane** (default ON) — keep MACHINE UNKNOWN rows when a machine filter is active (`include_unknown` in ini).
   - **Date from / to** (`DD.MM.YYYY`, e.g. `15.09.2026`)
   - **Source type** (`loose_nc`, `haas_pgm_glued`, …)
   - **Control** (`haas`, `fanuc`, `sinumerik`)
   - **Flag** — all / green (backup) / yellow (extra)
   - **Programmer** — next-line `(LP1)` / `(MS1)` when present (case-insensitive; other comments ignored)
   - **Newest only** — one row per program + machine (latest backup date)
   - **Preset** — **Save current…** / **Load** / **Delete** named filter sets (`filter_presets.yaml` next to the DB)
   - Click any **results column header** to sort asc/desc (also on floor clients)
   - **More filters** (indexer): size from/to (`10k` / `1.5M`) and file date (mtime/creation) ranges
   - **Language** — Polish UI by default; switch to English anytime (`ui_settings.yaml` next to the DB)
   Search matches program #, part #, path, machine names, FANUC folder paths, and programmer.
   Program-number search is **O / zero-padding aware**: `O03232`, `03232`, and `3232` find the same program.
   Empty text + filters still works.
9. Select a row → **Extract selected…** / **Wydobądź zaznaczone…** (or double-click) to write the program body for your other parser (defaults into the **extract folder**).
   **Multi-select** (Ctrl/Shift+click) → batch extract into a folder (filenames include program, machine, date).
   Or use **Open folder** / **Copy path** (also on right-click) to jump to the source file in Explorer / copy its absolute path.
   Extract **checks SHA-256 + size** stamped at scan time — if the source file changed, extract is refused (re-scan first).
   The **Preview** pane beside the results shows the selected program body (**In preview** find with next/prev + highlight). Large programs are truncated in the pane only.
   Select **exactly two** rows → **Compare…** for a unified diff (also on right-click).
10. After each successful scan a **Scan report** panel opens (also via **Scan report…**): per-machine counts, `*.nc.copy` totals, MACHINE UNKNOWN samples, unmapped folders, skipped dumps / errors.
11. **Duplicates…** finds **exact** copies (same content SHA-256) and **near**-duplicates (same program # + similar size, different hash) across machines/dates; **Show in results** loads a group into the main table.

While **Run index / scan** is running, a progress bar shows file count and ETA. You can also **Open existing DB…** without re-scanning. **Clear filters** resets the find bar. Floor clients with **Auto-refresh results** re-query when this PC’s incremental scan updates the shared sqlite.

## Windows standalone app (`.exe`)

You do **not** need Python installed if you use a prebuilt bundle from GitHub Actions (or a Release on a `v*` tag).

### Download a prebuilt zip (recommended)

1. Open **Actions** → workflow **Windows GUI build**:  
   https://github.com/Don-Pablo-G/gcode_backup_indexer_parser/actions/workflows/windows-build.yml  
2. Open the latest successful run (or click **Run workflow**).  
3. Download the artifact named like **`gcode-index-gui-windows-0.2.60-b80`** (version + build in the name).  
4. Unzip anywhere and run **`gcode-index-gui.exe`** inside the `gcode-index-gui-<version>` folder.  
   Keep the whole folder together (this is an **onedir** build — DLLs sit next to the exe).  
   A `VERSION.txt` beside the exe records `version=` and `build=`.

On a version tag (`v0.2.60`, …), the same zip (e.g. `gcode-index-gui-windows-0.2.60-b80.zip`) is also attached as a **Release** asset.

### Build the exe yourself on Windows

Requires Python **3.11+** from [python.org](https://www.python.org/downloads/) (include **tcl/tk**).

```bat
cd path\to\gcode_backup_indexer_parser
python -m pip install -e ".[dev,build]"
scripts\build_windows.bat
```

Output:

- Folder: `dist\gcode-index-gui-<version>\gcode-index-gui.exe`
- Zip: `dist\gcode-index-gui-windows-<version>-<build>.zip`  
  (`<build>` = Actions run number, else git short SHA, else timestamp)

Native Windows binaries are produced on **Windows** (local or GitHub Actions). Linux cannot emit a Windows `.exe` with stock PyInstaller.

## Scan a backup tree (CLI)

```bat
gcode-index scan "D:\CNC\Backups" --db "D:\CNC\Index\gcode_index.sqlite" --excel "D:\CNC\Index\gcode_index.xlsx" --folder-map "D:\CNC\Index\machine_folders.yaml" --extra-root "D:\CNC\OtherPrograms"
```

```bash
gcode-index scan /path/to/backup --db ./gcode_index.sqlite --excel ./gcode_index.xlsx
```

Optional `--aliases path\to\aliases.yaml` overrides the bundled machine alias map.  
Shop-local overlay: `aliases.local.yaml` next to `--db` is loaded automatically (or pass `--local-aliases`).

### Expected backup layout

```text
backup_folder/
  15.09.2026/                 # date folder
    SL-20/                    # machine folder (fuzzy names OK)
      SL20.PGM
    doosan d/
      ALL-FLDR.TXT
    doosan m/
      ALL-PROG.TXT
    ST20Y/
      HaasBackup(09-15-2026)/Memory/**/*.nc
    SBL/
      *.nc                    # Sinumerik manual drops
  loose1234.nc                # also indexed as loose_nc
```

### What gets indexed

| Source | `source_type` | Location |
|--------|---------------|----------|
| `*.pgm` | `haas_pgm_glued` | line + byte span (CRLF-aware) |
| `ALL-FLDR.TXT` | `fanuc_all_fldr` | line + byte span; `&F=` folder |
| `ALL-PROG.TXT` | `fanuc_all_prog` | line + byte span |
| `HaasBackup(*)/Memory/**/*.nc` | `haas_ngc_nc` | whole file; program # from in-file `O#####` (not filename) |
| `HaasBackup(*)/Memory/**/*.nc.copy` | `haas_ngc_nc_copy` | same as `.nc`, but marked as Haas NGC **copy** sibling |
| Manual `.nc` (SBL / config) | `manual_nc_folder` | whole file |
| Manual `*.nc.copy` | `manual_nc_folder_copy` | copy sibling under manual layout |
| Any other `*.nc` under the backup tree | `loose_nc` | whole file; machine from deepest ancestor folder matching map/alias (inherited by subfolders), else **MACHINE UNKNOWN** |
| Any other `*.nc.copy` | `loose_nc_copy` | copy sibling; same machine rules as `loose_nc` |

**Date source of truth:** filesystem **creation/birth time** of the dump or `.nc` (`backup_date` / `file_ctime`, `date_source=birth`). On Linux, birth time is used when the filesystem exposes it via `statx`; otherwise the indexer falls back to **mtime** and records `date_source=mtime`. On Windows, creation time (`st_ctime`) is used as birth.

Unmapped machine folders are logged to the `unknowns` table — the scanner does **not** invent locators from contents alone.

## Search / extract (CLI)

```bat
gcode-index search gcode_index.sqlite 1234
gcode-index search gcode_index.sqlite "P-00253232" --machine haas-umc750 --from 2026-01-01 --to 2026-12-31
gcode-index extract gcode_index.sqlite <instance_id> --backup-root "D:\CNC\Backups" -o slice.nc
```

- Free-text query (letters / digits / symbols) on program #, part #, path, machine.
- Optional `--machine`, `--from` / `--to` (`DD.MM.YYYY` or `YYYY-MM-DD`), `--type`.
- Prefix hits rank above mid-string hits.
- Extract slices glued dumps by stored line/byte span, or copies whole-file `.nc` types, for an **external** parser.
- Extracted glued programs are wrapped with `%` … `%` when missing. Whole-file `.nc` / `.nc.copy` are copied as-is (no `%` added).

## Machine aliases

Edit `aliases.yaml` (or pass `--aliases`). Keys are matched after normalize: lowercase → strip spaces/`-`/`_` → strip punctuation. Examples: `doosan d` / `doosan duzy` → `doosan-dnm-6700`; `SBL` / `SBL500` → `sbl-500` (Sinumerik, `manual_nc_folder`).

## Tests

```bash
python -m pytest -q
```

Unit tests use tiny synthetic fixtures under `tests/fixtures/synthetic/`. Optional smoke tests run against Project store samples when present (not committed to git).

## Non-goals

- Full G-code parse / validation / simulation
- Committing multi-MB backup dumps into this repository
- Modifying backup source files — **scan / parse / extract never write into the backup tree** (extract writes only to a path you choose)

## License

TBD
