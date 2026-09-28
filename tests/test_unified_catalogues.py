"""Unified catalogues: roles + recipients nest aliases under the selected entity."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.tk_util import skip_without_display_or_working_tk


@pytest.fixture
def tk():
    return skip_without_display_or_working_tk()


def _click_colour_row(dlg, idx: int, tk) -> None:
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


def test_roles_no_notebook_nested_aliases_and_exclude(tmp_path: Path, tk, monkeypatch):
    """Roles dialog: machine layout — aliases scoped to selection + exclude strip."""
    from gcode_index.folder_colour_aliases import (
        COLOUR_EXCLUDE,
        ColourCatalog,
        FolderColourRule,
        save_colour_catalog,
    )
    from gcode_index.gui import FolderColourAliasDialog
    from gcode_index.models import ROLE_PERSONAL, ROLE_PROTOTYPE

    path = tmp_path / "folder_colour_aliases.yaml"
    cat = ColourCatalog(
        rules=[
            FolderColourRule(alias="ProtoFolder", colour=ROLE_PROTOTYPE),
            FolderColourRule(alias="PersonalFolder", colour=ROLE_PERSONAL),
            FolderColourRule(alias="SkipMe", colour=COLOUR_EXCLUDE),
        ]
    )
    save_colour_catalog(path, cat)

    root = tk.Tk()
    root.withdraw()
    try:
        dlg = FolderColourAliasDialog(root, save_path=path)
        dlg.update_idletasks()

        assert not hasattr(dlg, "_tab_aliases")
        assert dlg._exclude_list.size() == 1
        assert dlg._exclude_list.get(0) == "SkipMe"

        # Help cleanup: no Status legend strip; Status & Flag opens manual
        assert callable(getattr(dlg, "_open_status_flag_help", None))
        assert "pack_status_legend" not in type(dlg).__dict__
        from gcode_index.i18n import STRINGS

        for lang in ("pl", "en"):
            intro = STRINGS[lang]["folder_colours_intro"]
            assert "Flaga" not in intro and "Flag =" not in intro
            assert "folder_colour_aliases.yaml" in intro
            assert "folder_colours_status_flag_help" in STRINGS[lang]
        assert "folder_colour_status_explain" not in STRINGS["pl"]
        assert "folder_colour_status_explain" not in STRINGS["en"]

        opened: list[object] = []

        class _FakeManual:
            def __init__(self, *a, **k):
                opened.append(k)

        monkeypatch.setattr("gcode_index.gui.ManualViewerDialog", _FakeManual)
        dlg._open_status_flag_help()
        assert len(opened) == 1
        assert isinstance(opened[0].get("body"), str) and opened[0]["body"]
        assert opened[0].get("title")

        # Select prototype → only its alias
        _click_colour_row(dlg, _index_for_id(dlg, ROLE_PROTOTYPE), tk)
        assert list(dlg._alias_list.get(0, tk.END)) == ["ProtoFolder"]

        # Select personal → only its alias
        _click_colour_row(dlg, _index_for_id(dlg, ROLE_PERSONAL), tk)
        assert list(dlg._alias_list.get(0, tk.END)) == ["PersonalFolder"]

        # Add alias for personal via askstring
        monkeypatch.setattr(
            "gcode_index.gui.simpledialog.askstring",
            lambda *a, **k: "PersonalAlt",
        )
        dlg._add_role_alias()
        assert "PersonalAlt" in list(dlg._alias_list.get(0, tk.END))
        assert all(
            r.colour == ROLE_PERSONAL
            for r in dlg._catalog.rules
            if r.alias in ("PersonalFolder", "PersonalAlt")
        )

        # Exclude CRUD
        monkeypatch.setattr(
            "gcode_index.gui.simpledialog.askstring",
            lambda *a, **k: "AlsoSkip",
        )
        dlg._add_exclude_alias()
        assert set(dlg._exclude_list.get(0, tk.END)) == {"SkipMe", "AlsoSkip"}
        dlg._exclude_list.selection_set(0)
        dlg._remove_exclude_alias()
        remaining = set(dlg._exclude_list.get(0, tk.END))
        assert remaining == {"AlsoSkip"} or remaining == {"SkipMe"}

        # Builtin lock still works
        proto_idx = _index_for_id(dlg, ROLE_PROTOTYPE)
        dlg._colour_list.selection_clear(0, tk.END)
        dlg._colour_list.selection_set(proto_idx)
        dlg._selected_colour_id = ROLE_PROTOTYPE
        shown = []

        def _info(*a, **k):
            shown.append(True)

        monkeypatch.setattr("gcode_index.gui.messagebox.showinfo", _info)
        dlg._remove_colour()
        assert shown
        assert any(c.id == ROLE_PROTOTYPE for c in dlg._catalog.colours)

        dlg._save()
        assert dlg.saved
        disk = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "colours" in disk or "roles" in disk or "version" in disk
        aliases = {r["alias"]: r["colour"] for r in disk.get("rules") or []}
        assert aliases.get("PersonalAlt") == ROLE_PERSONAL
        assert "AlsoSkip" in aliases or "SkipMe" in aliases
        assert COLOUR_EXCLUDE in aliases.values() or any(
            v == COLOUR_EXCLUDE for v in aliases.values()
        )
    finally:
        try:
            dlg.destroy()
        except Exception:
            pass
        root.destroy()


def test_odbiorca_nested_aliases_rename_and_roundtrip(tmp_path: Path, tk, monkeypatch):
    from gcode_index.gui import OdbiorcaCatalogDialog
    from gcode_index.odbiorca_aliases import (
        OdbiorcaCatalog,
        OdbiorcaDef,
        OdbiorcaRule,
        load_odbiorca_catalog,
        save_odbiorca_catalog,
    )

    path = tmp_path / "odbiorcy.yaml"
    save_odbiorca_catalog(
        path,
        OdbiorcaCatalog(
            odbiorcy=[
                OdbiorcaDef(id="acme", label_pl="Acme", label_en="Acme"),
                OdbiorcaDef(id="beta", label_pl="Beta", label_en="Beta"),
            ],
            rules=[
                OdbiorcaRule(alias="AcmeFolder", odbiorca_id="acme", exact=True),
            ],
        ),
    )

    root = tk.Tk()
    root.withdraw()
    try:
        dlg = OdbiorcaCatalogDialog(root, save_path=path)
        dlg.update_idletasks()
        assert dlg._list.size() == 2
        assert list(dlg._alias_list.get(0, tk.END)) == ["AcmeFolder"]

        # Switch to beta → empty aliases
        dlg._list.selection_clear(0, tk.END)
        dlg._list.selection_set(1)
        dlg._on_select()
        dlg.update_idletasks()
        assert dlg._selected_oid == "beta"
        assert dlg._alias_list.size() == 0

        monkeypatch.setattr(
            "gcode_index.gui.simpledialog.askstring",
            lambda *a, **k: "BetaFolder",
        )
        dlg._add_alias()
        assert list(dlg._alias_list.get(0, tk.END)) == ["BetaFolder"]

        # Back to acme, rename id → rules rewrite
        dlg._list.selection_clear(0, tk.END)
        dlg._list.selection_set(0)
        dlg._on_select()
        dlg.update_idletasks()
        assert dlg._selected_oid == "acme"
        dlg._id_var.set("acme_renamed")
        dlg._apply()
        assert dlg._selected_oid == "acme_renamed"
        assert any(r.odbiorca_id == "acme_renamed" for r in dlg.catalog.rules)
        assert not any(r.odbiorca_id == "acme" for r in dlg.catalog.rules)

        # Remove beta alias
        dlg._list.selection_clear(0, tk.END)
        # find beta index
        for i, o in enumerate(dlg.catalog.odbiorcy):
            if o.id == "beta":
                dlg._list.selection_set(i)
                break
        dlg._on_select()
        dlg.update_idletasks()
        dlg._alias_list.selection_set(0)
        dlg._remove_alias()
        assert dlg._alias_list.size() == 0

        dlg._save()
        assert dlg.saved
        loaded = load_odbiorca_catalog(path)
        assert {o.id for o in loaded.odbiorcy} == {"acme_renamed", "beta"}
        assert any(
            r.alias == "AcmeFolder" and r.odbiorca_id == "acme_renamed"
            for r in loaded.rules
        )
        assert not any(r.alias == "BetaFolder" for r in loaded.rules)
    finally:
        try:
            dlg.destroy()
        except Exception:
            pass
        root.destroy()
