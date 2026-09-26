"""Locate and open bundled user manuals (EN/PL; operator vs indexer).

Kinds ``simple`` / ``full`` are legacy filenames for floor (`can_index=no`) vs
indexer (`can_index=yes`) manuals — not a Prosty/Pełny UI mode.
"""

from __future__ import annotations

from gcode_index.i18n import t as i18n_t

import sys
from pathlib import Path
from typing import Literal, Optional

DocKind = Literal["simple", "full"]
LangCode = Literal["pl", "en"]

_MANUAL_FILES = {
    ("en", "simple"): "manual-simple.md",
    ("en", "full"): "manual-full.md",
    ("pl", "simple"): "manual-simple.md",
    ("pl", "full"): "manual-full.md",
}


def docs_roots() -> list[Path]:
    """Candidate roots that may contain ``en/`` and ``pl/`` manuals."""
    roots: list[Path] = []
    here = Path(__file__).resolve().parent
    # Packaged with the wheel / editable install
    roots.append(here / "docs")
    # Repo checkout: <repo>/docs
    roots.append(here.parents[1] / "docs")
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass) / "docs")
            roots.append(Path(meipass) / "gcode_index" / "docs")
        exe_dir = Path(sys.executable).resolve().parent
        roots.append(exe_dir / "docs")
        roots.append(exe_dir / "_internal" / "docs")
        roots.append(exe_dir / "_internal" / "gcode_index" / "docs")
    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def resolve_manual(lang: str, kind: DocKind) -> Optional[Path]:
    """Return path to a manual markdown file, or None if missing."""
    code = "pl" if str(lang).strip().casefold().startswith("pl") else "en"
    name = _MANUAL_FILES[(code, kind)]
    for root in docs_roots():
        path = root / code / name
        if path.is_file():
            return path
    # Cross-language fallback
    other = "en" if code == "pl" else "pl"
    other_name = _MANUAL_FILES[(other, kind)]
    for root in docs_roots():
        path = root / other / other_name
        if path.is_file():
            return path
    return None


def read_manual(lang: str, kind: DocKind) -> str:
    path = resolve_manual(lang, kind)
    if path is None:
        return i18n_t(lang, "help_manual_missing", lang=lang, kind=kind)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        return i18n_t(lang, "help_manual_read_error", error=f"{path}\n\n{exc}")
