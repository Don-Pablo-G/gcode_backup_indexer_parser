# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows GUI (onedir — more reliable with tkinter).

Build on Windows::

    python -m pip install -e ".[dev,build]"
    scripts\\build_windows.bat

Or::

    pyinstaller --noconfirm gcode-index-gui.spec
"""

from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

ROOT = Path(SPECPATH).resolve()

# Package data (aliases) + manuals + openpyxl / PyYAML runtime bits
datas = [
    (str(ROOT / "src" / "gcode_index" / "data" / "aliases.yaml"), "gcode_index/data"),
    (str(ROOT / "aliases.yaml"), "."),
    (str(ROOT / "docs"), "docs"),
    (str(ROOT / "src" / "gcode_index" / "docs"), "gcode_index/docs"),
]
binaries: list = []
hiddenimports = [
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.ttk",
    "yaml",
    "openpyxl",
    "gcode_index",
    "gcode_index.gui",
    "gcode_index.cli",
    "gcode_index.help_docs",
    "gcode_index.folder_watch",
    "gcode_index.indexer_lock",
    "gcode_index.autostart_win",
    "gcode_index.tray_ui",
    "gcode_index.scanner",
    "gcode_index.extract",
    "gcode_index.db",
    "gcode_index.aliases",
    "gcode_index.excel_export",
    "gcode_index.locators",
    "gcode_index.locators.haas_pgm",
    "gcode_index.locators.fanuc_all_fldr",
    "gcode_index.locators.fanuc_all_prog",
    "gcode_index.locators.whole_file_nc",
    "pystray",
    "pystray._win32",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
]

for pkg in ("openpyxl", "yaml", "pystray", "PIL"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    except Exception:
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Ensure package data files are collected even if package layout varies
datas += collect_data_files("gcode_index")

a = Analysis(
    [str(ROOT / "src" / "gcode_index" / "gui.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gcode-index-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="gcode-index-gui",
)
