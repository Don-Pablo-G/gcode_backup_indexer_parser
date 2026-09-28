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
- Use advanced filters, saved views, compare, scan report / index quality, duplicates
- Optionally write Excel after a scan
- Use Windows **autostart** / **tray** helpers

Indexer layout uses two primary navigation segments (large bar at the top):

| Tab | Contents |
|-----|----------|
| **Work / Praca** | Search / filters / **results table** \| **full-height preview on the right** — clean retrieve surface. One-line path summary + **Folders…** to open Index. Primary CTA: **Extract**. |
| **Index / Indeks** | Backup/DB/extract folders, green/yellow extras (Flag discs), **Run scan** on the right, doorways **Mapping…** / **Scan & watch…** / **Reports…** |

Floor clients (`can_index=no`) stay on a single retrieve surface — no Praca/Indeks tabs.

In the preview window, use **In preview** to find text in the G-code body (next/prev + highlight). Use **Extract to…** on the preview action row to write the viewed program to a chosen folder (same rules as the results context menu).

---

## Path remap (client)

If the index was built on a server as **C:** and this PC sees the same share as **Z:** (or you have several shares), open **Mapping…** and under **Path remap (client)** **Add…** one or more rules:

- **Prefix in index** = `C:\…` (as stored in the DB / `scan_root`)
- **Local prefix** = `Z:\…` (as on this PC)

Several rules are allowed — **longest matching prefix wins**. Applies to the main backup and green/yellow roots under that prefix. Search works without remap; **Extract** / preview use it. Saved in `gcode-index.ini` → `[path_remap]`.

On floor clients (`can_index=no`) path remap stays under **Change…** (no **Mapping…** doorway).

## Folders

| Folder | Purpose |
|--------|---------|
| **Backup folder** | Main CNC backup tree (`DATE\MACHINE\…`) |
| **Database folder** (`target`) | `gcode_index.sqlite` + sidecar files (`machine_folders.yaml`, `folder_tree_map.yaml`, `folder_colour_aliases.yaml`, `aliases.local.yaml`, `ui_settings.yaml`, …) |
| **Extract folder** | Default output for Wydobądź (blank = same as database folder) |

Browsing for backup / database / extract keeps the folder panel **open** so you can finish all paths. Collapse with **Done** / **Gotowe** when finished (or when a scan starts).

### Extra roots

- **Green** — treat like on-machine / catch folders for loose `.nc` (before backup misses them). Subfolders are scanned recursively. Programs get a **green** provenance flag.
- **Yellow** — extra trees not from the machine backup. Programs get a **yellow** status-unknown flag.

Roots are saved as `extra_scan_roots.yaml` next to the database (and in `gcode-index.ini`).

**Nested roots:** the **deepest** configured root (main backup or green/yellow) that contains a file owns it — that root’s colour and `scan_root` apply. Example: yellow parent + green child → files under the child are **green only** (no duplicate yellow row). Adding a root inside another shows a short note that the child overrides the parent colour.

### Status + folder roles

**Status** (ran on machine?) is stored from scan roots (`backup` / `extra`) — folder aliases never change that DB field:

| Badge | Meaning | Source |
|-------|---------|--------|
| 🟢 | On machine (`backup`) | Main backup tree, glued dumps, green catch / trusted roots |
| 🟡 | Status unknown (`extra`) | Any other subtree (yellow extras, etc.) |

**Flag column = status + distinct function colours.** Always one green **or** yellow status disc (unless a role with **can override main state colour** replaces it — prototype defaults on → single blue). Then one disc per **distinct** function colour from row roles (e.g. system programs orange beside green). Same colour never doubles. Row font colour follows the **primary** disc (status or override). True multi-colour discs are drawn as an image (not multiple text glyphs).

**`folder_colour_aliases.yaml` is mandatory** beside `gcode_index.sqlite` for truthful Flag colours on every client (floor or indexer). Opening a DB without that sidecar uses this software version’s seed colours and shows a status warning. **`folder_tree_map.yaml`** is needed when Flag tip reasons should show Map-tree path lines.

**Roles & aliases…** / **Role i aliasy…** (indexer) edits `folder_colour_aliases.yaml` next to the database — same layout as **Machines & aliases**:

1. **Left** — role list (add / edit / remove). Seeded: **prototype** (blue, override **on** by default), **personal** (red), **system programs** (orange), **fixture** (purple). Built-ins cannot be deleted. Yellow/green are status only — yellow must **never** read as fixture. Legacy seeds (production / WIP / test) remain as custom roles when already present in the file. Under the list: **Name exclusions** strip (folder spellings → do not index).
2. **Right** — selected role meta (`id`, labels PL+EN, colour picker / palette, badge, meaning, **can override main state colour**) plus nested **Folder aliases** for **that** role only. Deepest matching path segment wins. Aliases set roles only (they do not rewrite provenance). A folder may later receive **multiple** roles via the tree map.

When a matching role has **can override main state colour** enabled: Flag drops green/yellow and shows that role’s disc; row colour = role colour. Priority if several overrides match: **prototype first**, then stable order. Other (non-override) functions still appear as **additive coloured Flag discs** when their swatch differs from status. The **Role** text column is optional (hidden by default; show via **Columns**); Flag hover tip lists every function with alias / path / header / O9 reason.

**Mapuj drzewo…** / **Map tree…** (indexer) edits `folder_tree_map.yaml` next to the database: lazy folder tree from the backup + green/yellow roots. Per node: machine (optional), **multiple role tags**, exclude, or clear. ★ = explicit path rule, · = inherited. **Longest path prefix wins** over name-wide aliases (path tags **replace** the name-role union). **Right-click** a folder → *Alias name “…” everywhere* → machine or role (exact name; name-role aliases **accumulate**). Status cannot be changed from the menu. Reindex reapplies the saved rules.

Use separate **Status** and **Role** filters (role filter matches any tag). Exact Duplicates flag **role** (and status) conflicts. **Re-scan** after upgrading so `role` is filled.

---

## Map folders and aliases

1. **Folder names…** — name-binding hub: list from the backup and extra roots (most frequent first), **chips** for machine / function / recipient when bound. **Right-click** (or double-click) → new recipient/machine/function from this name or alias to an existing entry (label and alias prefilled from the folder spelling). Recipients / Machines / Roles catalogues stay for maintenance. Writes `aliases.local.yaml` / `folder_colour_aliases` / `odbiorcy.yaml`.
2. **Map tree…** — lazy path tree for machine + recipient + multi-role tags + exclude (`folder_tree_map.yaml`; deepest path wins). Right-click a folder → name alias everywhere (machine / role / recipient).
3. **Machines & aliases…** — machine list on the left; select one to edit its **folder aliases**, label, control, and layout. **Add machine** / **Remove machine** manage shop-local machines. Bundled catalog spellings stay read-only (`[bundled]`); add a local spelling to customize. Saved as `aliases.local.yaml`. Those folder aliases also match header `(…)` when **Machine from header** is on and the row is still MACHINE UNKNOWN.
4. **Roles & aliases…** — same pattern: select a role → meta + nested folder aliases; **Name exclusions** under the role list. Those aliases also match header paren comments `(…)` when **Roles from header** is on (accumulate after path/tree; before O9).
5. **Recipients & aliases…** — same pattern: select a recipient → labels + nested folder aliases; one odbiorca per program (like machine). Folder-name aliases also match header paren comments `(…)` when path/folder left odbiorca empty (**Odbiorca from header** toggle; reindex to backfill).

Header window (same for odbiorca / role / machine): first **40** lines of the program (or from glued `byte_start`); paren comments only; aliases only (not catalogue labels); min needle length 3. **Machine from header** fills only when the row is still **MACHINE UNKNOWN** — folder map / name alias / tree machine always win. Status 🟢/🟡 is never taken from the header.

### Loose `.nc` machine assignment

When indexing individual `.nc` / `.nc.copy` files, the scanner walks parent folders **deepest → shallowest**. The first folder name that matches the folder map or an alias becomes the **machine** for that file and everything under that folder. No match → **MACHINE UNKNOWN** (still indexed).

---

## Run index / scan

Order on **Index / Indeks** (top → bottom): **1 · Folders** (backup / DB / extract + extras) → **2 · Setup** (Mapping / Scan & watch / Reports as needed) → **3 · Scan** with **Run scan** on the right.

1. Set backup + database folders (and extras if needed), or use **Open existing DB…** on the toolbar to pick an already-built `gcode_index.sqlite`.
2. Click green **Run scan** / **Uruchom skan** (right side). Setup is under **Mapping…**, **Scan & watch…**, and **Reports…**.
3. Deep setup is under **Mapping…** (including path remap), **Scan & watch…** (incremental / Excel / header toggles / O9 / watch / tray), and **Reports…**.
4. Progress shows file count and ETA. A **scan report** opens when finished (also via **Scan report…**).

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
- **Only green** / **Tylko zielone** — show only rows whose Flag disc is green (backup/trusted); hides yellow and prototype-override colours. AND with other filters. Saved as `[filters] only_green` (default off).
- **More filters** — source type, control, flag (green/yellow), role, odbiorca, programmer, **views** (named filter sets in `views.yaml` next to the DB), **size from/to** (bytes or `10k` / `1.5M`), **file date from/to** (source mtime / creation; calendar via **▾**)
- Click any **results column header** to sort ascending/descending
- **Compare…** — unified diff of exactly two selected rows
- **Index quality…** — UNKNOWN machines, missing odbiorca, `system_programs` (O9000–O9099), colour conflicts; click a row to filter results
- **Duplicates…** — exact groups use **program-body** SHA-256 (`program_sha256`: normalized extract text with `%` frame + LF newlines), so glued dump slices can match loose `.nc` / `.nc.copy` with the same body. Members show **colour badges**; groups with ≥2 colours for the same body are flagged as **colour conflicts** (**Konflikt kolorów**) with a filter to show only those. Near-duplicates: same program # + similar size, different body hash. Whole-file `content_sha256` is unchanged for extract integrity. **Re-scan** after upgrade to fill `program_sha256` on older rows.
- **Open folder** / **Copy path** on the source file
- Right-click → **Extract to…** — pick a folder (recent destinations remembered in the ini)

**Wydobądź / Extract** writes program bodies to the extract folder (or a path you choose). Sources are never modified. Extract checks whole-file SHA-256 (`content_sha256`) + size from scan time.

---

## Scan history

**Scan history…** (indexer only) lists the last index runs from `scan_history.json` next to the database: when, duration, programs, files **added / updated / removed / unchanged**. Survives DB rebuilds — useful when diagnosing network spikes during incremental scans.

---

## Day-to-day database hygiene

Practical routine to **build and keep** the index healthy. Each successful scan walks the configured trees (read-only), assigns machine / roles / odbiorca / Flag status, then **deletes and rewrites** `gcode_index.sqlite` in the database folder. There is **no** separate VACUUM step — size tracks program count, not scan history. History lives in capped `scan_history.json` (~40 runs).

### Incremental vs Full

| Use **Incremental** (default; leave checked) | Use **Full** (uncheck Incremental) |
|----------------------------------------------|------------------------------------|
| Day-to-day new backups / new folders under known roots | After machine map or machine-alias edits that should reassign **old** files |
| Watch / schedule (always force incremental) | After **removing** function-colour aliases (clear stale roles) |
| Fast catch-up when most files are unchanged | After turning **O9 → system programs** off (or cleaning legacy O9 tags) |
| First scan after adding a root (new files miss cache anyway) | After a major tree reorganisation you do not trust cache for |
| | Once after upgrading if you need fresh `program_sha256` / duplicate hygiene on old rows |

**Incremental** still walks the whole tree, but **reuses** parsed rows when **size + mtime** match the previous DB; only new/changed files are fully parsed. **Full** re-parses every indexable file and rebuilds machine inference from today’s maps/aliases.

Rule of thumb: **Incremental keeps the catalog current with the disk. Full rebuilds assignments from today’s maps for every file.**

### Daily (indexer PC)

1. Keep **one** indexer owning the share (`gcode_index.lock` / Watch). Floor PCs stay `can_index=no`.
2. Prefer **Watch** and/or a modest **Auto-index** schedule so new dumps enter the DB without babysitting (both run incremental).
3. Before expecting Haas NGC rows: confirm UMC / ST-20Y zips were **unzipped** under the date/machine folder (scanner ignores `.zip`).
4. Glance at the Indeks status line (last schedule / watch) and any **missing source** count after a search.

### Weekly (or after a busy backup week)

1. **Reports → Index quality…** / **Jakość indeksu…** — click through MACHINE UNKNOWN, missing odbiorca, colour conflicts.
2. Spot-check **Scan history…** / **Historia skanów…** — added / updated / removed should look sane (spikes → network or path issues).
3. If UNKNOWN climbed: fix maps/aliases in **Mapping…** / **Mapowanie…**, then one **full** rescan.
4. Optionally trim old files in the **extract** folder (leave the DB pack alone).

### After config / YAML changes

| Change | Next action |
|--------|-------------|
| New files only / new subfolder under an existing root | Incremental (Watch / schedule / manual) |
| Machine folders map or machine aliases for **already indexed** paths | Full rescan |
| Removed function-colour rules (or want roles rebuilt clean) | Full rescan |
| Added colour / tree / O9 rules that still match paths | Incremental usually enough |
| Odbiorcy catalogue / header toggle | Incremental usually enough (odbiorca re-applied on post-pass; header fills only if still empty) |
| Role / machine header toggles or new role/machine aliases | Incremental usually enough for **adds** (roles accumulate; machine only upgrades UNKNOWN → known). **Full** if you disabled a toggle or removed aliases and need to clear stale header-taught values |
| New green/yellow root | Add root → scan (incremental OK for discovery) |
| Moved pack to another PC / share | Confirm whole folder copied; **Prepare indexer…** / **Przygotuj indeksator…** on the listening PC; remap paths |

### Pack beside the DB (copy the whole folder)

Treat the **database folder** as one kit. Share the **whole folder**, not sqlite alone.

| File | Why |
|------|-----|
| `gcode_index.sqlite` | Program rows (status, roles, paths, hashes) |
| `folder_colour_aliases.yaml` | **Mandatory** for truthful Flag colours on every client |
| `folder_tree_map.yaml` | Map-tree overrides; Flag tip path reasons |
| `aliases.local.yaml`, `machine_folders.yaml` | Machine teaching for the next scan |
| `odbiorcy.yaml` | Recipient catalogue |
| `extra_scan_roots.yaml` | Green/yellow roots |
| `indexer_settings.yaml` | Shop scan/watch/schedule **defaults** (never forces `can_index`) |

Optional: `scan_history.json`, `ui_settings.yaml`, `views.yaml`, `gcode_index.xlsx`.

**Per PC (not in the pack):** `gcode-index.ini` next to the exe — `can_index`, absolute paths, path remap, language, floor locks.

### What not to do

- Do **not** copy only `gcode_index.sqlite` to floor PCs and expect correct Flag colours.
- Do **not** put `can_index=yes` in the shared pack or promote every PC to indexer.
- Do **not** run Watch on two indexer PCs against the same DB.
- Do **not** expect the scanner to open Haas `.zip` files — unzip first.
- Do **not** edit backup originals to “fix” the index; extract writes elsewhere; sources stay read-only.
- Do **not** assume Incremental reassigns machines after map edits — use Full.
- Do **not** delete sidecars “to clean disk”; that breaks Flag / next-scan teaching. Prefer cleaning **extract** output instead.
- Do **not** rely on vacuum/compact rituals — the app already rewrites sqlite each scan.
- Do **not** leave extract path blank on a shared DB folder if operators dump many extracts there — use a separate extract folder.

Deleted/moved sources drop on the **next** scan; until then the row shows a **missing source** badge.

## Operator lock (floor deploy)

Shop PCs should stay retrieve-only. Either:

- set `[capabilities] settings_locked = yes` in `gcode-index.ini`, or
- place an empty `operator.lock` (or `can_index.lock`) next to the ini / exe.

When locked, `can_index` is forced to **no** even if the ini says yes. Remove the lock only on the indexer PC.

## Auto-refresh search (clients after incremental index)

Tick **Auto-refresh results** / **Odświeżaj wyniki** to **re-run the current search** when `gcode_index.sqlite` changes (mtime poll, default ~20 s). Useful on floor clients that open a **network** copy of the DB while the indexer runs Watch / scheduled incremental scans: new rows appear without clearing filters or reopening the file. Saved as `search_auto_refresh` / `search_auto_refresh_s` in the ini. Without it, operators click Search again after the indexer finishes.

## Instance settings

**Ustawienia wracają po restarcie** / settings survive restart: `gcode-index.ini` next to the exe remembers folders, greens/yellows, **`can_index`**, language, desktop prefs, window size, path remap, **last find-bar filters**, sort column, and Praca/Indeks layout. Next to the DB: `indexer_settings.yaml` — **shared shop defaults** for scan / schedule / watch (data pack; does **not** force `can_index`). The indexer updates this file when those toggles change.

**Prepare indexer…** (Tools / Index): confirm backup and extract paths plus remap, apply pack defaults, set `can_index=yes`, optionally enable watch. Floor clients stay on `can_index=no` (plus optional `operator.lock`).  

Sidecars next to the database (`machine_folders.yaml`, `folder_tree_map.yaml`, `folder_colour_aliases.yaml`, `aliases.local.yaml`, …) auto-load with the DB folder — tree/role/machine assignments are never lost on restart.  

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
