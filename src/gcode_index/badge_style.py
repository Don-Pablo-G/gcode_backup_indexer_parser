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

# Solid disc — colour comes from widget foreground / tag, not from the font emoji.
DOT = "●"

STATUS_SWATCH = {
    PROVENANCE_BACKUP: "#1A7F37",  # on machine / green
    PROVENANCE_EXTRA: "#B58900",  # not run / yellow
}


def status_swatch(prov: Optional[str]) -> str:
    key = (prov or PROVENANCE_BACKUP).strip() or PROVENANCE_BACKUP
    return STATUS_SWATCH.get(key, STATUS_SWATCH[PROVENANCE_BACKUP])


def status_dot(prov: Optional[str] = None) -> str:
    """One status marker character (colour via Treeview tag / Label fg)."""
    return DOT


def role_dot(_badge: Optional[str] = None) -> str:
    """Role marker for lists/trees — ignore emoji badge; use colourable disc."""
    return DOT


def flag_text(prov: Optional[str], role_ids: Sequence[str] | None = None) -> str:
    """Flag-column text: status disc + one disc per role (all take row tag colour)."""
    parts = [DOT]
    for _rid in role_ids or []:
        parts.append(DOT)
    return "".join(parts)


def flag_tag(prov: Optional[str], role_ids: Sequence[str] | None = None) -> str:
    """Treeview tag name: prefer first role id, else status."""
    roles = [r for r in (role_ids or []) if r]
    if roles:
        return f"flag_{roles[0]}"
    status = (prov or PROVENANCE_BACKUP).strip() or PROVENANCE_BACKUP
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
    make_swatch(row, STATUS_SWATCH[PROVENANCE_BACKUP]).pack(side=tk.LEFT, padx=(0, 4))
    tk.Label(row, text=on_machine_text).pack(side=tk.LEFT, padx=(0, 12))
    make_swatch(row, STATUS_SWATCH[PROVENANCE_EXTRA]).pack(side=tk.LEFT, padx=(0, 4))
    tk.Label(row, text=not_run_text).pack(side=tk.LEFT)
    tk.Label(frame, text=explain_text, wraplength=wraplength, justify=tk.LEFT).pack(
        anchor=tk.W, fill=tk.X, pady=(6, 0)
    )
    return frame
