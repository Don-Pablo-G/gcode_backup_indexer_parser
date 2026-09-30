"""Client export pack builder + mtime sync helpers."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from gcode_index.client_pack import (
    CLIENT_PACK_ZIP_NAME,
    DEFAULT_DB_NAME,
    FOLDER_COLOUR_ALIASES_FILENAME,
    NEVER_PACK_FILES,
    PACK_MANIFEST_FILENAME,
    collect_pack_files,
    export_client_pack_folder,
    export_client_pack_zip,
    pack_mtimes_changed,
    snapshot_pack_mtimes,
    validate_pack_source,
)
from gcode_index.folder_colour_aliases import (
    ColourCatalog,
    save_colour_catalog,
)
from gcode_index.odbiorca_aliases import (
    OdbiorcaCatalog,
    OdbiorcaDef,
    save_odbiorca_catalog,
)


def _seed_db_folder(tmp: Path, *, with_colours: bool = True) -> Path:
    (tmp / DEFAULT_DB_NAME).write_bytes(b"SQLite fake")
    if with_colours:
        save_colour_catalog(tmp / FOLDER_COLOUR_ALIASES_FILENAME, ColourCatalog())
    save_odbiorca_catalog(
        tmp / "odbiorcy.yaml",
        OdbiorcaCatalog(
            odbiorcy=[OdbiorcaDef(id="acme", label_pl="Acme", label_en="Acme")]
        ),
    )
    (tmp / "aliases.local.yaml").write_text("machines: {}\n", encoding="utf-8")
    (tmp / "gcode-index.ini").write_text("[capabilities]\ncan_index = yes\n", encoding="utf-8")
    (tmp / "gcode_index.lock").write_text("lock\n", encoding="utf-8")
    (tmp / "header_token_freq.json").write_text("{}", encoding="utf-8")
    (tmp / "scan_history.json").write_text("[]", encoding="utf-8")
    return tmp


def test_validate_requires_sqlite_and_colours(tmp_path: Path):
    v = validate_pack_source(tmp_path)
    assert v.ok is False
    assert any("gcode_index.sqlite" in e for e in v.errors)
    (tmp_path / DEFAULT_DB_NAME).write_bytes(b"x")
    v2 = validate_pack_source(tmp_path)
    assert v2.ok is False
    assert any("folder_colour" in e for e in v2.errors)


def test_collect_excludes_ini_locks_and_teach_caches(tmp_path: Path):
    _seed_db_folder(tmp_path)
    files, validation = collect_pack_files(tmp_path)
    assert validation.ok
    names = {f.name for f in files}
    assert DEFAULT_DB_NAME in names
    assert FOLDER_COLOUR_ALIASES_FILENAME in names
    assert "odbiorcy.yaml" in names
    assert "aliases.local.yaml" in names
    for banned in (
        "gcode-index.ini",
        "gcode_index.lock",
        "header_token_freq.json",
        "scan_history.json",
        "operator.lock",
        "can_index.lock",
    ):
        assert banned in NEVER_PACK_FILES
        assert banned not in names


def test_export_zip_atomic_and_manifest(tmp_path: Path):
    _seed_db_folder(tmp_path)
    result = export_client_pack_zip(tmp_path)
    assert result.ok, result.errors
    assert result.zip_path is not None
    assert result.zip_path.name == CLIENT_PACK_ZIP_NAME
    assert result.zip_path.is_file()
    assert (tmp_path / PACK_MANIFEST_FILENAME).is_file()
    with zipfile.ZipFile(result.zip_path, "r") as zf:
        names = set(zf.namelist())
    assert DEFAULT_DB_NAME in names
    assert FOLDER_COLOUR_ALIASES_FILENAME in names
    assert PACK_MANIFEST_FILENAME in names
    assert "gcode-index.ini" not in names
    assert "gcode_index.lock" not in names
    man = json.loads((tmp_path / PACK_MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert man["kind"] == "gcode-index-client-pack"
    assert "can_index" not in man
    assert man["files"]


def test_export_folder_manual(tmp_path: Path):
    _seed_db_folder(tmp_path)
    out = tmp_path / "usb-drop"
    result = export_client_pack_folder(tmp_path, out)
    assert result.ok, result.errors
    assert (out / DEFAULT_DB_NAME).is_file()
    assert (out / FOLDER_COLOUR_ALIASES_FILENAME).is_file()
    assert (out / PACK_MANIFEST_FILENAME).is_file()
    assert not (out / "gcode-index.ini").exists()


def test_export_fails_without_colours(tmp_path: Path):
    _seed_db_folder(tmp_path, with_colours=False)
    result = export_client_pack_zip(tmp_path)
    assert result.ok is False
    assert result.zip_path is None
    assert not (tmp_path / CLIENT_PACK_ZIP_NAME).exists()


def test_pack_mtimes_changed_detects_sidecar(tmp_path: Path):
    import os

    _seed_db_folder(tmp_path)
    snap1 = snapshot_pack_mtimes(tmp_path)
    any_c, db_c, side_c = pack_mtimes_changed(snap1, snap1)
    assert any_c is False
    colour = tmp_path / FOLDER_COLOUR_ALIASES_FILENAME
    colour.write_text(colour.read_text(encoding="utf-8") + "\n# touch\n", encoding="utf-8")
    # Ensure mtime advances even on coarse filesystems / same-second writes.
    os.utime(colour, (snap1[FOLDER_COLOUR_ALIASES_FILENAME] + 2, snap1[FOLDER_COLOUR_ALIASES_FILENAME] + 2))
    snap2 = snapshot_pack_mtimes(tmp_path)
    any_c, db_c, side_c = pack_mtimes_changed(snap1, snap2)
    assert any_c is True
    assert db_c is False
    assert side_c is True
