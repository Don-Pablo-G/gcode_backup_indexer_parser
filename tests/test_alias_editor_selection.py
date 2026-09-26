"""Alias editor: machine Listbox selection must follow the clicked row."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.tk_util import require_working_tk

require_working_tk()

import tkinter as tk  # noqa: E402

from gcode_index.aliases import AliasMap  # noqa: E402
from gcode_index.gui import AliasEditorDialog  # noqa: E402


def _click_machine_row(dlg: AliasEditorDialog, idx: int) -> None:
    """Select a Listbox row and run the same handler ``<<ListboxSelect>>`` uses.

    ``event_generate('<<ListboxSelect>>')`` is unreliable under headless/CI Tk,
    so tests drive the bound callback directly after ``selection_set``.
    """
    dlg._machine_list.selection_clear(0, tk.END)
    dlg._machine_list.selection_set(idx)
    dlg._machine_list.activate(idx)
    dlg._on_machine_selected()
    dlg.update_idletasks()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_machine_list_click_selects_clicked_row(tmp_path: Path):
    """Regression: flushing previous machine must not re-pin highlight to old index.

    Before the fix, ``_on_machine_selected`` called ``_apply_machine_details``,
    which reloaded the list and ``selection_set`` the *previous* machine — so
    every click left the highlight stuck (commonly on an earlier row such as
    ``doosan-dnm-400``).
    """
    bundled = Path(__file__).resolve().parents[1] / "aliases.yaml"
    am = AliasMap.load(bundled)
    overview = am.machines_overview()
    assert len(overview) >= 3, "need several machines to exercise selection"

    root = tk.Tk()
    root.withdraw()
    try:
        dlg = AliasEditorDialog(root, aliases=am, save_path=tmp_path / "aliases.local.yaml")
        dlg.update_idletasks()

        order = list(dlg._machine_order)
        assert len(order) >= 3
        assert dlg._machine_list.size() == len(order)

        # Click each row in reverse order — highlight and detail must follow.
        for idx in (2, 0, 1, len(order) - 1, 0):
            _click_machine_row(dlg, idx)

            sel = dlg._machine_list.curselection()
            assert sel == (idx,), f"highlight stuck: want {idx}, got {sel}"
            assert dlg._selected_mid == order[idx]
            assert dlg._mid_var.get() == order[idx]
    finally:
        try:
            dlg.destroy()
        except Exception:
            pass
        root.destroy()


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_machine_list_selection_survives_label_edit_flush(tmp_path: Path):
    """Changing the previous machine's label must not snap selection back."""
    bundled = Path(__file__).resolve().parents[1] / "aliases.yaml"
    am = AliasMap.load(bundled)

    root = tk.Tk()
    root.withdraw()
    try:
        dlg = AliasEditorDialog(root, aliases=am, save_path=tmp_path / "aliases.local.yaml")
        dlg.update_idletasks()
        order = list(dlg._machine_order)
        assert len(order) >= 2

        # Select first, edit its label in the detail pane, then click second.
        _click_machine_row(dlg, 0)
        dlg._label_var.set("ZZZ Edited Label")

        _click_machine_row(dlg, 1)

        # After label change the list re-sorts; clicked machine must stay selected.
        assert dlg._selected_mid == order[1]
        sel = dlg._machine_list.curselection()
        assert len(sel) == 1
        assert dlg._machine_order[int(sel[0])] == order[1]
        assert dlg._mid_var.get() == order[1]
        # Previous machine kept the edited label in draft
        assert dlg._draft[order[0]]["label"] == "ZZZ Edited Label"
    finally:
        try:
            dlg.destroy()
        except Exception:
            pass
        root.destroy()
