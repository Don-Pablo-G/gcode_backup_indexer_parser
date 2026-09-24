# G-code backup indexer / parser

Index CNC machine **backup folder trees** into a portable **SQLite** catalog of **program instances** (program #, part #, machine, date, source location). Full G-code parsing is **out of scope** — this tool extracts **headers + locations only** so humans and other software can search and later extract spans.

**Canonical repo:** https://github.com/Don-Pablo-G/gcode_backup_indexer_parser

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

## Windows GUI (Phase 2)

```bat
gcode-index-gui
REM or:
python -m gcode_index.gui
```

1. **Browse** → pick the main **backup folder** tree.  
2. **Browse** → pick a **target folder** (database + extract output live here as `gcode_index.sqlite`).  
3. Click **Map folders…** (optional but recommended). The app scans `<date>/<machine>` folders, **auto-matches** names it knows from aliases, and lists **only unmatched** folders for manual assign. Subfolders inherit.  
   - Map is saved as `machine_folders.yaml` next to the DB (wins over aliases).  
   - Optional checkbox: also save assignments as **local aliases** (`aliases.local.yaml` next to the DB) so the same odd folder names auto-match on later scans.  
   - First scan prompts only when unmatched folders remain.  
   - **Aliases…** opens an editor to **add / change / remove** local aliases (and override bundled ones). Bundled `aliases.yaml` stays read-only.  
4. Click **Run index / scan** (optional Excel export checkbox).  
   After a successful scan the table lists indexed programs with **source path** and **in-file location**.  
5. **Find programs** with free text (letters, digits, dashes — e.g. `P-00253232 VA` or `O03232`; **case-insensitive**), plus filters:  
   - **Machines** (multi-select list — Ctrl/Shift+click; **All** / **None** buttons; empty selection = all machines).  
     The list is seeded from `aliases.yaml` + local aliases (so **HAAS UMC750**, ST-20Y, … always appear) plus **MACHINE UNKNOWN**, and merged with machines seen in the last scan.  
     VF-2 has three entries (legacy / **nowa** / **stara**); selecting **HAAS VF-2** also matches the nowa/stara ids.  
   - **Date from / to** (`DD.MM.YYYY`, e.g. `15.09.2026`)  
   - **Source type** (`loose_nc`, `haas_pgm_glued`, …)  
   - **Control** (`haas`, `fanuc`, `sinumerik`)  
   Text matches program #, part #, path, machine names, and FANUC folder paths. Empty text + filters still works.  
6. Select a row → **Extract selected…** (or double-click) to write the program body for your other parser.  
   Or use **Open folder** / **Copy path** (also on right-click) to jump to the source file in Explorer / copy its absolute path.  
   Extract **checks SHA-256 + size** stamped at scan time — if the source file changed, extract is refused (re-scan first).

While **Run index / scan** is running, a progress bar shows file count and ETA. You can also **Open existing DB…** without re-scanning. **Clear filters** resets the find bar.

## Windows standalone app (`.exe`)

You do **not** need Python installed if you use a prebuilt bundle from GitHub Actions (or a Release on a `v*` tag).

### Download a prebuilt zip (recommended)

1. Open **Actions** → workflow **Windows GUI build**:  
   https://github.com/Don-Pablo-G/gcode_backup_indexer_parser/actions/workflows/windows-build.yml  
2. Open the latest successful run (or click **Run workflow**).  
3. Download the artifact named like **`gcode-index-gui-windows-0.2.3-b42`** (version + build in the name).  
4. Unzip anywhere and run **`gcode-index-gui.exe`** inside the `gcode-index-gui-<version>` folder.  
   Keep the whole folder together (this is an **onedir** build — DLLs sit next to the exe).  
   A `VERSION.txt` beside the exe records `version=` and `build=`.

On a version tag (`v0.2.3`, …), the same zip (e.g. `gcode-index-gui-windows-0.2.3-b42.zip`) is also attached as a **Release** asset.

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
gcode-index scan "D:\CNC\Backups" --db "D:\CNC\Index\gcode_index.sqlite" --excel "D:\CNC\Index\gcode_index.xlsx" --folder-map "D:\CNC\Index\machine_folders.yaml"
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
| Any other `*.nc` under the backup tree | `loose_nc` | whole file; machine via fuzzy folder match, else **MACHINE UNKNOWN** |
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
