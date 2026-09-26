"""Deploy-time operator lock — floor PCs stay retrieve-only.

Mechanisms (either forces retrieve-only / locks dangerous settings):

1. Lock file next to ``gcode-index.ini`` / the exe:
   ``operator.lock`` or ``can_index.lock`` (empty file is enough).
2. INI flag ``[capabilities] settings_locked = yes``.

When locked, ``can_index`` is forced to **no** regardless of the ini value, so a
shop PC cannot become an indexer by editing ``can_index=yes`` alone. Remove the
lock file (and set ``settings_locked=no``) only on the indexer PC.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

OPERATOR_LOCK_NAMES = ("operator.lock", "can_index.lock")


def lock_file_beside(ini_path: Path | str) -> Optional[Path]:
    """Return the first existing lock file next to the ini (or None)."""
    parent = Path(ini_path).expanduser().resolve().parent
    for name in OPERATOR_LOCK_NAMES:
        candidate = parent / name
        if candidate.is_file():
            return candidate
    return None


def settings_locked_from_ini_value(value: Optional[str]) -> bool:
    raw = (value or "").strip().casefold()
    if not raw:
        return False
    return raw in ("1", "true", "yes", "y", "on", "tak", "locked", "lock")


def is_settings_locked(
    *,
    ini_path: Path | str | None = None,
    settings_locked_flag: bool = False,
) -> bool:
    """True when a lock file exists and/or the ini flag is set."""
    if settings_locked_flag:
        return True
    if ini_path is not None and lock_file_beside(ini_path) is not None:
        return True
    # Env override for tests / packaging
    env = (os.environ.get("GCODE_INDEX_SETTINGS_LOCKED") or "").strip().casefold()
    if env in ("1", "true", "yes", "y", "on"):
        return True
    return False
