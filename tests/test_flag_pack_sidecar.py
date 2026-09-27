"""Client Flag pack: folder_colour_aliases.yaml mandatory beside DB."""

from __future__ import annotations

from pathlib import Path

from gcode_index.folder_colour_aliases import (
    FOLDER_COLOUR_ALIASES_FILENAME,
    colour_aliases_sidecar_present,
    folder_colour_aliases_path_for_target,
    load_colour_catalog,
    save_colour_catalog,
    ColourCatalog,
)


def test_colour_aliases_sidecar_present(tmp_path: Path):
    assert colour_aliases_sidecar_present(tmp_path) is False
    path = folder_colour_aliases_path_for_target(tmp_path)
    assert path.name == FOLDER_COLOUR_ALIASES_FILENAME
    save_colour_catalog(path, ColourCatalog())
    assert colour_aliases_sidecar_present(tmp_path) is True


def test_load_colour_catalog_seeds_when_missing(tmp_path: Path):
    cat = load_colour_catalog(tmp_path / "nope.yaml")
    assert cat.colours  # seed defaults
    assert colour_aliases_sidecar_present(tmp_path) is False
