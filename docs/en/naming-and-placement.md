# Naming & placement — best practices

**Audience:** indexer operators who shape the backup tree, green/yellow extras, aliases, and headers so Flag, machines, roles, recipients (odbiorcy), Watch, and teach lists work well.  
**Capability:** most of this is configured on the indexer PC (`can_index=yes`). Floor clients only need the **pack beside the DB**.  
**Reflects behaviour through 0.2.118** (stacked on 0.2.117).
**Polish:** `docs/pl/naming-and-placement.md` (Help → **Nazwy i rozmieszczenie…**).

In the GUI: **Help → Naming & placement…** opens this guide. The same topics also appear as a chapter in the **Indexer manual**.

---

## 1. Backup folder tree vs green vs yellow

| Place | Meaning | Flag / status |
|-------|---------|----------------|
| **Main backup folder** | The shop’s CNC backup tree (Haas dumps, dated folders, machine folders, …) | 🟢 **From machine** — tip: **from backup** |
| **Green extras** (trusted / “z maszyny”) | Catch folders for loose `.nc` that should count like machine copy before the next full backup | 🟢 same green disc — tip: **trusted folder** |
| **Yellow extras** | Other trees (scratch, WIP, unknown provenance) | 🟡 **Status unknown** |

**Practical:**

- Put the real machine backup under **Backup**. That is what operators mean by “from the machine.”
- Use **green** only for folders you trust as machine-side / catch copies. Do not paint every loose share green.
- Use **yellow** for anything that must be searchable but must **not** look like a confirmed machine run.
- Nested roots: the **deepest** configured root that contains a file owns it (child colour wins; no duplicate rows).
- Folder **name aliases never change** green/yellow — only scan-root provenance does. Roles (personal, prototype, system programs, …) are separate Flag discs.

---

## 2. Folder naming — token boundaries

Aliases match **tokens**, not mashed prefixes. Tokens are split on **space**, `_`, and `-` (and similar separators).

| Folder / comment | Alias `pat` | Match? |
|------------------|-------------|--------|
| `pat` | personal | Yes |
| `pat_backup` / `pat-backup` / `foo pat bar` | personal | Yes (token `pat`) |
| `pattyn` | personal | **No** (one token; not fuzzy-bleed) |
| `VF2S` | `VF2` | Yes (fuzzy **inside** one token, short residual) |

**Do:**

- Name folders so the machine / role / recipient spelling is its **own** token: `2026-03-15_VF2S_backup`, `Acme_Sp_parts`, `PROTO OP1`.
- Prefer aliases at least **3** characters; avoid one- or two-letter needles that collide across the shop.
- After changing aliases, **reindex** (full when you need old rows reassigned).

**Don’t:**

- Rely on old fuzzy “prefix of the whole stripped name” (`pat` → `pattyn`). That bleed is gone.
- Use the same short alias for two different machines or a machine and a recipient.
- Expect catalogue **labels** (display names) to match paths — only **aliases** are needles.

---

## 3. Teaching roles, machines, and recipients

Teach once; the same needles apply to **folder names** and to **O-line** `(…)` comments.

| Where | What it writes | Best for |
|-------|----------------|----------|
| **Folder names…** / **Nazwy folderów…** | Frequency list → create or link alias | Repeating folder spellings across the tree |
| **Map tree…** / **Mapuj drzewo…** | Path-specific machine / multi-role / odbiorca / exclude | One odd path that must override name aliases |
| **Machines / Roles / Recipients & aliases…** | Catalogue maintenance | Labels, colours, adding spellings by hand |
| **Unassigned header tokens…** (scan report) | Same alias sidecars from O-line tokens | Frequent header spellings not yet bound |

**Precedence (simplified):**

1. Tree map path rules (longest prefix) replace name-role unions for that path.
2. Name aliases accumulate roles; machine / odbiorca fill when still empty / UNKNOWN.
3. Header O-line aliases fill gaps (machine only if still UNKNOWN; odbiorca only if still empty; roles accumulate).
4. Optional **O9000–O9099 → system programs** adds that role by program number.

Right-click a folder in **Map tree** → *Alias name “…” everywhere* teaches a **name-wide** alias (not status).

---

## 4. Header O-line comments (auto-match vs teach list)

**Auto-match** (machine / role / odbiorca from header) looks only at paren comments **on the same line as the program number**:

```text
O9001 (VF2S) (PROTO) (Pawel)
O03232 (P-00253232 VA OP1/OP2)
```

Comments on the next lines or deeper in the body are **ignored** for auto-assign.

**Teach list** (**Unassigned header tokens…**):

- Same O-line window by default (**Header scan depth** = **1** in Scan options).
- Depth widens **only** the teach list (1–20; stops before the next `%`). It does **not** widen auto-match.
- Excludes program numbers and tokens with **more than 4 digit characters** (drawing / part-number noise).
- After you assign aliases, a **full** rescan refreshes the list so taught tokens drop out.

**Do** put machine / role / recipient tags in `(…)` on the **O#####** line.  
**Don’t** expect body comments or off-O-line notes to drive Flag / machine / odbiorca.

---

## 5. Program numbers `O#####` and system programs

- Normal part programs use a machine program number on an `O#####` line (padding varies; search treats `O03232` / `3232` alike).
- Optional scan toggle **O9 → system programs** (default **on**): numbers in **O9000–O9099** get role **`system_programs`** (orange) automatically. Outside that band (e.g. O9100) there is **no** auto tag — use a folder or header alias if you still want the role.
- O9 tagging does **not** change green/yellow status, machine, or odbiorca.

---

## 6. What Watch watches (and safety)

With **Watch folders** on (indexer only):

| Setting | Default | Effect |
|---------|---------|--------|
| **Exclude backup folder** | **On** | Live listeners / stamp-poll cover **green/yellow extras only** — not the main backup tree |
| Min. quiet between scans | 45 s | Coalesce busy dump bursts |
| Safety rescan | Off | Optional forced incremental on an interval; optional **at HH:MM** (local wall clock) |

**Important:**

- Manual **Run scan**, Watch-triggered incremental, and **safety** still index **backup + extras** through the normal scan pipeline. Exclude-backup only skips **live** watch/poll of the backup root.
- Prefer green/yellow catch folders for near-live dumps; leave backup on schedule / manual / safety if the tree is huge or on flaky UNC.
- One PC holds `gcode_index.lock`. Background Watch/coalesce/safety scans do **not** jump Praca → Indeks; only manual Run scan does.

---

## 7. Client pack — sidecars next to the DB

Copy the **whole database folder** to floor PCs (or point them at the share). Next to `gcode_index.sqlite`:

| File | Why |
|------|-----|
| `folder_colour_aliases.yaml` | **Mandatory** for truthful Flag colours / override roles |
| `folder_tree_map.yaml` | Flag tip path reasons; path tags |
| `aliases.local.yaml`, `machine_folders.yaml` | Machine teaching for the next scan |
| `odbiorcy.yaml` | Recipient catalogue |
| `extra_scan_roots.yaml` | Green/yellow roots |
| `indexer_settings.yaml` | Shared scan/watch defaults (**never** `can_index`) |

**Per PC (not in the pack):** `gcode-index.ini` next to the exe — `can_index`, absolute paths, path remap, language, locks.

Opening a lone `.sqlite` without `folder_colour_aliases.yaml` falls back to seed colours and warns.

---

## 8. Do / don’t checklist

**Do**

- Keep one clear **backup** root; use **green** sparingly for trusted catch folders; **yellow** for everything else searchable.
- Split meaningful names with space / `_` / `-` so aliases are whole tokens.
- Teach repeating spellings in **Folder names…**; fix one-off paths in **Map tree…**.
- Put teachable tags in `(…)` on the **O-number line**.
- Keep the **full pack** beside the DB for every client.
- Leave **Exclude backup** on unless you truly need live Watch on the whole backup tree.
- Use safety **HH:MM** when you want “every night at midnight”-style catch-up.

**Don’t**

- Expect short aliases to match *inside* longer words (`pat` ≠ `pattyn`).
- Put drawing numbers (long digit runs) into teach aliases — the teach list already hides tokens with **>4 digits**.
- Rely on comments **below** the O-line for auto machine / role / odbiorca.
- Confuse **role** colours with **status** green/yellow — roles never rewrite provenance.
- Ship only the sqlite file to the floor.
- Run Watch on two indexer PCs against the same DB.
- Put `can_index=yes` into the shared pack.

---

## Related Help

- **Indexer manual** — folders, Mapowanie, Watch, day-to-day hygiene (full detail).
- **Operator manual** — retrieve / extract; pack hygiene on the floor.
