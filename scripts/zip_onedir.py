"""Zip a PyInstaller onedir folder for distribution."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src_dir", type=Path, help="onedir folder to zip")
    ap.add_argument("zip_path", type=Path, help="output .zip path")
    args = ap.parse_args()
    src: Path = args.src_dir
    zpath: Path = args.zip_path
    if not src.is_dir():
        raise SystemExit(f"missing onedir folder: {src}")
    zpath.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(src).as_posix())
    print(f"{zpath.resolve()} ({zpath.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
