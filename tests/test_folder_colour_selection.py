"""Folder roles Listbox selection must follow the clicked row."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.tk_util import skip_without_display_or_working_tk


@pytest.fixture
def tk():
    """Working Tk module, or skip (broken Tcl on some Windows CI Pythons)."""
    return skip_without_display_or_working_tk()


def _click_colour_row(dlg, idx: int, tk) -> None:
    """Select a Listbox row and run the bound <<ListboxSelect>> handler."""
    dlg._colour_list.selection_clear(0, tk.END)
    dlg._colour_list.selection_set(idx)
    dlg._colour_list.activate(idx)
    dlg._on_colour_select()
    dlg.update_idletasks()


def _index_for_id(dlg, colour_id: str) -> int:
    for i, c in enumerate(dlg._catalog.colours):
        if c.id == colour_id:
            return i
    raise AssertionError(f"colour id {colour_id!r} not in catalogue")


def test_role_list_click_selects_clicked_row(tmp_path: Path, tk):
    """Regression: flushing previous role must not re-pin highlight to old index.

    Before the fix, ``_on_colour_select`` called ``_apply_colour_fields``, which
    reloaded the list and ``selection_set`` the *previous* role — so every click
    left the highlight stuck.
    """
    from gcode_index.folder_colour_aliases import ColourCatalog, save_colour_catalog
    from gcode_index.gui import FolderColourAliasDialog

    path = tmp_path / "folder_colour_aliases.yaml"
    # Empty save → defaults load; enough rows to exercise selection.
    save_colour_catalog(path, ColourCatalog())

    root = tk.Tk()
    root.withdraw()
    try:
        dlg = FolderColourAliasDialog(root, save_path=path)
        dlg.update_idletasks()
        n = dlg._colour_list.size()
        assert n >= 3

        for idx in (2, 0, 1, n - 1, 0):
            _click_colour_row(dlg, idx, tk)
            sel = dlg._colour_list.curselection()
            assert sel == (idx,), f"highlight stuck: want {idx}, got {sel}"
            assert dlg._selected_colour_id == dlg._catalog.colours[idx].id
            assert dlg._cid_var.get() == dlg._catalog.colours[idx].id
    finally:
        try:
            dlg.destroy()
        except Exception:
            pass
        root.destroy()


def test_role_list_selection_survives_label_edit_flush(tmp_path: Path, tk):
    from gcode_index.folder_colour_aliases import ColourCatalog, save_colour_catalog
    from gcode_index.gui import FolderColourAliasDialog

    path = tmp_path / "folder_colour_aliases.yaml"
    save_colour_catalog(path, ColourCatalog())

    root = tk.Tk()
    root.withdraw()
    try:
        dlg = FolderColourAliasDialog(root, save_path=path)
        dlg.update_idletasks()
        assert len(dlg._catalog.colours) >= 2
        first_id = dlg._catalog.colours[0].id
        second_id = dlg._catalog.colours[1].id

        _click_colour_row(dlg, _index_for_id(dlg, first_id), tk)
        dlg._label_pl_var.set("ZZZ Edited")

        _click_colour_row(dlg, _index_for_id(dlg, second_id), tk)

        assert dlg._selected_colour_id == second_id
        sel = dlg._colour_list.curselection()
        assert len(sel) == 1
        assert dlg._catalog.colours[int(sel[0])].id == second_id
        assert dlg._cid_var.get() == second_id
        assert dlg._catalog.get(first_id).label_pl == "ZZZ Edited"
    finally:
        try:
            dlg.destroy()
        except Exception:
            pass
        root.destroy()


def test_name_hub_role_form_uses_palette_not_bare_hex(tk):
    """Hub 'new function' must offer swatch + presets like Role folderów."""
    from gcode_index.folder_colour_aliases import COLOUR_PRESET_SWATCHES
    from gcode_index.gui import _NameHubRoleForm

    root = tk.Tk()
    root.withdraw()
    try:
        form = _NameHubRoleForm(
            root,
            title="test",
            prefill_id="uchwyty",
            prefill_label="Uchwyty",
            alias="Uchwyty",
        )
        form.update_idletasks()
        # Palette chips present (one Label per preset with that background)
        chip_bgs = []
        for w in form.winfo_children():
            for child in w.winfo_children():
                # walk colour_box → palette
                stack = [child]
                while stack:
                    n = stack.pop()
                    stack.extend(list(n.winfo_children()))
                    if isinstance(n, tk.Label):
                        try:
                            bg = str(n.cget("background")).upper()
                        except tk.TclError:
                            continue
                        if bg.startswith("#") and len(bg) == 7:
                            chip_bgs.append(bg)
        for preset in COLOUR_PRESET_SWATCHES:
            assert preset.upper() in chip_bgs, f"missing palette chip {preset}"
        # Primary colour control is not a lone Entry as the only colour widget:
        # swatch_var still backs the optional hex readout under the palette.
        assert form.swatch_var.get() == "#888888"
        form.swatch_var.set("#1A7F37")
        assert form.swatch_var.get() == "#1A7F37"
    finally:
        try:
            form.destroy()
        except Exception:
            pass
        root.destroy()
