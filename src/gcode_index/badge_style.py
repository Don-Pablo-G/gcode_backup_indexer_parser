"""Reliable status/role colour indicators for Tk (Windows-safe).

Emoji (🟢🟡🔴) often render as patterned B&W glyphs under Windows tk fonts.
Use a monochrome circle ``●`` (U+25CF) that takes Treeview/Listbox
``foreground=`` hex, or a solid ``tk.Label`` background chip for legends.

**Multi-colour Flag model** (restated 0.2.95):

- Always show **status** 🟢 backup / 🟡 extra, **unless** a role with
  ``can_override_main_state_colour`` replaces it (prototype → single blue).
- Then add **one disc per distinct function colour** from row roles.
- Never two discs of the **same** colour (dedupe by swatch hex).
- True multi-colour needs a composed image (see ``flag_image``) — Treeview
  one-fg would paint every ``⬤`` the same colour (the old double-green bug).
- Row text colour still follows the **primary** disc (status or override) via
  ``flag_tag``; function discs do not recolour the whole row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Optional, Sequence

from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA, ROLE_PROTOTYPE

if TYPE_CHECKING:
    import tkinter as tk

# Solid discs — colour via widget foreground / tag (not emoji glyphs).
# LARGE is slightly bigger for status/role markers in the results table.
DOT = "●"
DOT_LARGE = "⬤"  # U+2B24 BLACK LARGE CIRCLE

STATUS_SWATCH = {
    PROVENANCE_BACKUP: "#1A7F37",  # on machine / green
    PROVENANCE_EXTRA: "#B58900",  # status unknown / yellow (never a role)
}

# Fixed override priority: prototype first, then stable alphabetical order.
_OVERRIDE_PRIORITY_FIRST = (ROLE_PROTOTYPE,)


def status_swatch(prov: Optional[str]) -> str:
    key = (prov or PROVENANCE_BACKUP).strip() or PROVENANCE_BACKUP
    return STATUS_SWATCH.get(key, STATUS_SWATCH[PROVENANCE_BACKUP])


def status_dot(prov: Optional[str] = None) -> str:
    """One status marker character (colour via Treeview tag / Label fg)."""
    return DOT_LARGE


def role_dot(_badge: Optional[str] = None) -> str:
    """Role marker for lists/trees — ignore emoji badge; use colourable disc."""
    return DOT_LARGE


def normalize_swatch_hex(colour: Optional[str]) -> str:
    """Lowercase ``#rrggbb`` for same-colour dedupe (3-digit expanded)."""
    raw = (colour or "").strip() or "#888888"
    if not raw.startswith("#"):
        raw = f"#{raw}"
    h = raw[1:]
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return "#888888"
    try:
        int(h, 16)
    except ValueError:
        return "#888888"
    return f"#{h.casefold()}"


def pick_override_role(
    role_ids: Sequence[str] | None,
    override_role_ids: Sequence[str] | None = None,
) -> Optional[str]:
    """Return the role id that should replace status, or ``None``.

    Only roles listed in ``override_role_ids`` qualify. Among matches:
    prototype first, then stable sorted order. Same-colour / duplicate role
    ids are already collapsed by ``normalize_roles_list``.
    """
    from gcode_index.folder_tree_map import normalize_roles_list

    override = {
        str(x).strip()
        for x in (override_role_ids or ())
        if x is not None and str(x).strip()
    }
    if not override:
        return None
    roles = normalize_roles_list(list(role_ids or []))
    candidates = [r for r in roles if r in override]
    if not candidates:
        return None
    for preferred in _OVERRIDE_PRIORITY_FIRST:
        if preferred in candidates:
            return preferred
    return sorted(candidates)[0]


def flag_discs(
    prov: Optional[str],
    role_ids: Sequence[str] | None = None,
    *,
    override_role_ids: Sequence[str] | None = None,
    role_swatches: Mapping[str, str] | None = None,
) -> list[tuple[str, str]]:
    """Ordered Flag discs as ``(id, hex)`` — status/override then functions.

    Rules:
    - Override match → **only** that role's disc (replaces status).
    - Otherwise → status disc, then one disc per **distinct** role colour
      (skip when the swatch matches a disc already shown).
    """
    from gcode_index.folder_tree_map import normalize_roles_list

    swatches = dict(role_swatches or {})
    roles = normalize_roles_list(list(role_ids or []))
    chosen = pick_override_role(roles, override_role_ids)
    if chosen:
        hx = swatches.get(chosen) or "#888888"
        return [(chosen, hx)]

    status = (prov or PROVENANCE_BACKUP).strip() or PROVENANCE_BACKUP
    status_hex = status_swatch(status)
    discs: list[tuple[str, str]] = [(status, status_hex)]
    seen = {normalize_swatch_hex(status_hex)}
    for rid in roles:
        hx = swatches.get(rid) or "#888888"
        key = normalize_swatch_hex(hx)
        if key in seen:
            continue
        seen.add(key)
        discs.append((rid, hx))
    return discs


def flag_text(
    prov: Optional[str],
    role_ids: Sequence[str] | None = None,
    *,
    override_role_ids: Sequence[str] | None = None,
) -> str:
    """Plain-text Flag fallback: one ``⬤`` only (never multi-glyph).

    GUI Work/floor results use ``flag_image`` for true multi-colour discs.
    Do **not** put several ``⬤`` here — Treeview one-fg would reintroduce
    same-colour doubles.
    """
    _ = (prov, role_ids, override_role_ids)
    return DOT_LARGE


def flag_tag(
    prov: Optional[str],
    role_ids: Sequence[str] | None = None,
    *,
    override_role_ids: Sequence[str] | None = None,
) -> str:
    """Treeview tag name for **row text** colour (primary disc only).

    Default: **status** (green backup / yellow extra). When a matching role
    has override enabled, that role colours the row instead.
    """
    chosen = pick_override_role(role_ids, override_role_ids)
    if chosen:
        return f"flag_{chosen}"
    status = (prov or PROVENANCE_BACKUP).strip() or PROVENANCE_BACKUP
    return f"flag_{status}"


def is_flag_green(
    prov: Optional[str],
    role_ids: Sequence[str] | None = None,
    *,
    override_role_ids: Sequence[str] | None = None,
) -> bool:
    """True when the primary Flag disc is backup/trusted green.

    Yellow (extra) and overriding function colours (e.g. prototype blue) are
    not green — used by the Work GUI **Only green** filter. Additive function
    discs beside green status do not change this.
    """
    return (
        flag_tag(prov, role_ids, override_role_ids=override_role_ids)
        == f"flag_{PROVENANCE_BACKUP}"
    )


def make_swatch(
    parent: "tk.Misc",
    hex_colour: str,
    *,
    width: int = 3,
    height: int = 1,
    padx: int = 4,
    pady: int = 2,
) -> "tk.Label":
    """Solid RGB chip (background), reliable on Windows tk."""
    import tkinter as tk

    colour = (hex_colour or "#888888").strip() or "#888888"
    if not colour.startswith("#"):
        colour = f"#{colour}"
    return tk.Label(
        parent,
        text="  ",
        width=width,
        background=colour,
        relief=tk.SOLID,
        borderwidth=1,
        padx=padx,
        pady=pady,
    )


def pack_status_legend(
    parent: "tk.Misc",
    *,
    on_machine_text: str,
    not_run_text: str,
    explain_text: str,
    wraplength: int = 720,
) -> "tk.Frame":
    """Status legend with real green/yellow chips + plain-language note."""
    import tkinter as tk

    frame = tk.Frame(parent)
    row = tk.Frame(frame)
    row.pack(anchor=tk.W, fill=tk.X)
    make_swatch(row, STATUS_SWATCH[PROVENANCE_BACKUP], width=4, height=1).pack(
        side=tk.LEFT, padx=(0, 4)
    )
    tk.Label(row, text=on_machine_text).pack(side=tk.LEFT, padx=(0, 12))
    make_swatch(row, STATUS_SWATCH[PROVENANCE_EXTRA], width=4, height=1).pack(
        side=tk.LEFT, padx=(0, 4)
    )
    tk.Label(row, text=not_run_text).pack(side=tk.LEFT)
    tk.Label(frame, text=explain_text, wraplength=wraplength, justify=tk.LEFT).pack(
        anchor=tk.W, fill=tk.X, pady=(6, 0)
    )
    return frame


def pack_compact_colour_legend(
    parent: "tk.Misc",
    *,
    on_machine_text: str,
    not_run_text: str,
    role_items: Sequence[tuple[str, str]] | None = None,
    roles_caption: str = "",
) -> "tk.Frame":
    """One-line status (+ optional role) legend for the results toolbar."""
    import tkinter as tk

    frame = tk.Frame(parent)
    make_swatch(frame, STATUS_SWATCH[PROVENANCE_BACKUP], width=3, height=1, padx=3, pady=1).pack(
        side=tk.LEFT, padx=(0, 3)
    )
    tk.Label(frame, text=on_machine_text).pack(side=tk.LEFT, padx=(0, 10))
    make_swatch(frame, STATUS_SWATCH[PROVENANCE_EXTRA], width=3, height=1, padx=3, pady=1).pack(
        side=tk.LEFT, padx=(0, 3)
    )
    tk.Label(frame, text=not_run_text).pack(side=tk.LEFT, padx=(0, 10))
    if role_items:
        if roles_caption:
            tk.Label(frame, text=roles_caption).pack(side=tk.LEFT, padx=(4, 6))
        for colour, label in list(role_items)[:6]:
            make_swatch(frame, colour, width=3, height=1, padx=3, pady=1).pack(
                side=tk.LEFT, padx=(0, 2)
            )
            tk.Label(frame, text=label).pack(side=tk.LEFT, padx=(0, 8))
    return frame
