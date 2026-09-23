# G-code backup indexer / parser

Index CNC machine **backup folder trees** into a portable **SQLite** catalog of **program instances** (program #, part #, machine, date, source location). Full G-code parsing is **out of scope** — this tool extracts **headers + locations only** so humans and other software can search and later extract spans.

**Canonical repo:** https://github.com/Don-Pablo-G/gcode_backup_indexer_parser

## Requirements

- Python **3.11+** (tested on 3.12)
- Windows, Linux, or macOS

## Install

```bat
REM Windows (cmd) — from the repo root
python -m pip install -e ".[dev]"
```

```bash
# Linux / macOS / Git Bash
python3 -m pip install -e ".[dev]"
# or: uv pip install -e ".[dev]"
```

Entry point: `gcode-index` (also `python -m gcode_index`).

## Scan a backup tree

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

## Search / extract (thin CLI)

```bat
gcode-index search gcode_index.sqlite 1234
gcode-index extract gcode_index.sqlite <instance_id> --backup-root "D:\CNC\Backups" -o slice.txt
```

Search requires a query with **≥4 digits**. Matches substring on `program_number` and `part_number`.

## Machine aliases

Edit `aliases.yaml` (or pass `--aliases`). Keys are matched after normalize: lowercase → strip spaces/`-`/`_` → strip punctuation. Examples: `doosan d` / `doosan duzy` → `doosan-dnm-6700`; `SBL` / `SBL500` → `sbl-500` (Sinumerik, `manual_nc_folder`).

## Tests

```bash
python -m pytest -q
```

Unit tests use tiny synthetic fixtures under `tests/fixtures/synthetic/`. Optional smoke tests run against Project store samples when present (not committed to git).

## Non-goals (Phase 1)

- Full G-code parse / validation / simulation
- Windows GUI (Phase 2)
- Committing multi-MB backup dumps into this repository

## License

TBD
