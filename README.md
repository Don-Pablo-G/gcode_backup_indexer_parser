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
3. Click **Run index / scan** (optional Excel export checkbox).  
4. Type a query with **≥4 digits** — closest matches refresh as you type (≈200 ms debounce). Results show **program #**, **part number**, **machine**, **date**.  
5. Select a row → **Extract selected…** (or double-click) to write the program body for your other parser.

You can also **Open existing DB…** without re-scanning.

## Windows standalone app (`.exe`)

You do **not** need Python installed if you use a prebuilt bundle from GitHub Actions (or a Release on a `v*` tag).

### Download a prebuilt zip (recommended)

1. Open **Actions** → workflow **Windows GUI build**:  
   https://github.com/Don-Pablo-G/gcode_backup_indexer_parser/actions/workflows/windows-build.yml  
2. Open the latest successful run (or click **Run workflow**).  
3. Download the artifact **`gcode-index-gui-windows`** (a zip).  
4. Unzip anywhere and run **`gcode-index-gui.exe`** inside the folder.  
   Keep the whole folder together (this is an **onedir** build — DLLs sit next to the exe).

On a version tag (`v0.2.1`, …), the same zip is also attached as a **Release** asset.

### Build the exe yourself on Windows

Requires Python **3.11+** from [python.org](https://www.python.org/downloads/) (include **tcl/tk**).

```bat
cd path\to\gcode_backup_indexer_parser
python -m pip install -e ".[dev,build]"
scripts\build_windows.bat
```

Output: `dist\gcode-index-gui\gcode-index-gui.exe` (distribute the entire `gcode-index-gui` folder).

Native Windows binaries are produced on **Windows** (local or GitHub Actions). Linux cannot emit a Windows `.exe` with stock PyInstaller.

## Scan a backup tree (CLI)

```bat
gcode-index scan "D:\CNC\Backups" --db "D:\CNC\Index\gcode_index.sqlite" --excel "D:\CNC\Index\gcode_index.xlsx"
```

```bash
gcode-index scan /path/to/backup --db ./gcode_index.sqlite --excel ./gcode_index.xlsx
```

Optional `--aliases path\to\aliases.yaml` overrides the bundled machine alias map.

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
| `HaasBackup(*)/Memory/**/*.nc` | `haas_ngc_nc` | whole file |
| Manual `.nc` (SBL / config) | `manual_nc_folder` | whole file |
| Loose root `.nc` | `loose_nc` | whole file |

**Date source of truth:** filesystem **creation/birth time** of the dump or `.nc` (`backup_date` / `file_ctime`, `date_source=birth`). On Linux, birth time is used when the filesystem exposes it via `statx`; otherwise the indexer falls back to **mtime** and records `date_source=mtime`. On Windows, creation time (`st_ctime`) is used as birth.

Unmapped machine folders are logged to the `unknowns` table — the scanner does **not** invent locators from contents alone.

## Search / extract (CLI)

```bat
gcode-index search gcode_index.sqlite 1234
gcode-index extract gcode_index.sqlite <instance_id> --backup-root "D:\CNC\Backups" -o slice.nc
```

- Search requires a query with **≥4 digits**.
- Matches **substring** on `program_number` and `part_number`; **prefix** hits rank above mid-string hits.
- Extract slices glued dumps by stored line/byte span, or copies whole-file `.nc` types, for an **external** parser.

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

## License

TBD
