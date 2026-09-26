"""Reliable status/role colour indicators for Tk (Windows-safe).

Emoji (🟢🟡🔴) often render as patterned B&W glyphs under Windows tk fonts.
Use a monochrome circle ``●`` (U+25CF) that takes Treeview/Listbox
``foreground=`` hex, or a solid ``tk.Label`` background chip for legends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Sequence

from gcode_index.models import PROVENANCE_BACKUP, PROVENANCE_EXTRA

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


def status_swatch(prov: Optional[str]) -> str:
    key = (prov or PROVENANCE_BACKUP).strip() or PROVENANCE_BACKUP
    return STATUS_SWATCH.get(key, STATUS_SWATCH[PROVENANCE_BACKUP])


def status_dot(prov: Optional[str] = None) -> str:
    """One status marker character (colour via Treeview tag / Label fg)."""
    return DOT_LARGE


def role_dot(_badge: Optional[str] = None) -> str:
    """Role marker for lists/trees — ignore emoji badge; use colourable disc."""
    return DOT_LARGE


def flag_text(prov: Optional[str], role_ids: Sequence[str] | None = None) -> str:
    """Flag-column text: status disc + one disc per unique role (alongside).

    Roles are a set — duplicate ids never produce extra chips. Status is always
    present as the first disc; role discs are extras, not a replacement.
    """
    from gcode_index.folder_tree_map import normalize_roles_list

    roles = normalize_roles_list(list(role_ids or []))
    parts = [DOT_LARGE]  # status
    parts.extend(DOT_LARGE for _ in roles)
    return "".join(parts)


def flag_tag(
    prov: Optional[str],
    role_ids: Sequence[str] | None = None,
    *,
    role_overshadow_status: bool = False,
) -> str:
    """Treeview tag name for row/flag colour.

    Default: **status** wins (green backup / yellow extra). When
    ``role_overshadow_status`` is True and roles exist, the first role id
    colours the row instead.
    """
    from gcode_index.folder_tree_map import normalize_roles_list

    status = (prov or PROVENANCE_BACKUP).strip() or PROVENANCE_BACKUP
    if role_overshadow_status:
        roles = normalize_roles_list(list(role_ids or []))
        if roles:
            return f"flag_{roles[0]}"
    return f"flag_{status}"


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
