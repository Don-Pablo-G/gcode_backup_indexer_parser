"""Folder-name → colour / exclude rules for path provenance overrides.

Sidecar next to the database: ``folder_colour_aliases.yaml``.

Each rule maps a folder-name alias (fuzzy like machine aliases) to:
- ``backup`` / green — on-machine
- ``extra`` / yellow — not from backup
- ``wip`` / red — WIP / not production-ready
- ``exclude`` — do not index that folder branch

Matching walks path segments under the owning scan root (folders only).
The **deepest** matching segment wins (same spirit as nested-root ownership).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import yaml

from gcode_index.aliases import normalize_folder_name
from gcode_index.models import (
    COLOUR_EXCLUDE,
    PROVENANCE_BACKUP,
    PROVENANCE_EXTRA,
    PROVENANCE_VALUES,
    PROVENANCE_WIP,
)

FOLDER_COLOUR_ALIASES_FILENAME = "folder_colour_aliases.yaml"

_MIN_SUBSTRING_ALIAS_LEN = 4
_MIN_PREFIX_ALIAS_LEN = 3

_COLOUR_ALIASES = {
    "green": PROVENANCE_BACKUP,
    "backup": PROVENANCE_BACKUP,
    "machine": PROVENANCE_BACKUP,
    "ran": PROVENANCE_BACKUP,
    "yellow": PROVENANCE_EXTRA,
    "extra": PROVENANCE_EXTRA,
    "other": PROVENANCE_EXTRA,
    "red": PROVENANCE_WIP,
    "wip": PROVENANCE_WIP,
    "work": PROVENANCE_WIP,
    "exclude": COLOUR_EXCLUDE,
    "skip": COLOUR_EXCLUDE,
    "ignore": COLOUR_EXCLUDE,
}

COLOUR_RULE_VALUES = (*PROVENANCE_VALUES, COLOUR_EXCLUDE)


def normalize_colour(raw: str | None) -> str:
    """Coerce a colour label to backup/extra/wip/exclude (default extra)."""
    key = (raw or "").strip().casefold()
    if key in _COLOUR_ALIASES:
        return _COLOUR_ALIASES[key]
    if key in COLOUR_RULE_VALUES:
        return key
    return PROVENANCE_EXTRA


@dataclass(frozen=True)
class FolderColourRule:
    """One folder-name alias → colour or exclude."""

    alias: str
    colour: str = PROVENANCE_EXTRA

    def __post_init__(self) -> None:
        object.__setattr__(self, "alias", (self.alias or "").strip())
        object.__setattr__(self, "colour", normalize_colour(self.colour))

    @property
    def key(self) -> str:
        return normalize_folder_name(self.alias)


def folder_colour_aliases_path_for_target(target: Path | str) -> Path:
    return Path(target) / FOLDER_COLOUR_ALIASES_FILENAME


def _parse_rule(item: Any) -> Optional[FolderColourRule]:
    if isinstance(item, FolderColourRule):
        return item if item.alias else None
    if isinstance(item, str):
        # Bare string → yellow override (legacy-friendly)
        alias = item.strip()
        return FolderColourRule(alias=alias, colour=PROVENANCE_EXTRA) if alias else None
    if isinstance(item, dict):
        alias = str(item.get("alias") or item.get("name") or item.get("folder") or "").strip()
        if not alias:
            return None
        colour = item.get("colour") or item.get("color") or item.get("provenance") or item.get("flag")
        return FolderColourRule(alias=alias, colour=str(colour or PROVENANCE_EXTRA))
    return None


def load_folder_colour_rules(path: Path | str) -> list[FolderColourRule]:
    p = Path(path)
    if not p.is_file():
        return []
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    raw_items: list[Any] = []
    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        raw_items = list(data.get("rules") or data.get("aliases") or [])
    out: list[FolderColourRule] = []
    seen: set[str] = set()
    for item in raw_items:
        rule = _parse_rule(item)
        if rule is None or not rule.alias:
            continue
        nk = rule.key
        if not nk or nk in seen:
            continue
        seen.add(nk)
        out.append(rule)
    return out


def save_folder_colour_rules(path: Path | str, rules: Iterable[FolderColourRule]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for rule in rules:
        r = rule if isinstance(rule, FolderColourRule) else _parse_rule(rule)
        if r is None or not r.alias:
            continue
        nk = r.key
        if not nk or nk in seen:
            continue
        seen.add(nk)
        cleaned.append({"alias": r.alias, "colour": r.colour})
    payload = {
        "_comment": (
            "Folder-name aliases → colour override or exclude. "
            "Deepest matching path segment wins. "
            "colour=backup|green, extra|yellow, wip|red, or exclude."
        ),
        "rules": cleaned,
    }
    p.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return p


class FolderColourAliasMap:
    """Match folder path segments against colour / exclude rules."""

    def __init__(self, rules: Sequence[FolderColourRule] | None = None) -> None:
        self._rules: list[FolderColourRule] = []
        self._by_key: dict[str, FolderColourRule] = {}
        for rule in rules or []:
            if not rule.alias or not rule.key:
                continue
            self._rules.append(rule)
            self._by_key[rule.key] = rule

    @classmethod
    def load(cls, path: Path | str) -> "FolderColourAliasMap":
        return cls(load_folder_colour_rules(path))

    @classmethod
    def empty(cls) -> "FolderColourAliasMap":
        return cls([])

    @property
    def rules(self) -> list[FolderColourRule]:
        return list(self._rules)

    def __len__(self) -> int:
        return len(self._rules)

    def match_segment(self, folder_raw: str) -> Optional[str]:
        """Return colour/exclude for one folder name, or None if no rule matches."""
        key = normalize_folder_name(folder_raw)
        if not key:
            return None
        exact = self._by_key.get(key)
        if exact is not None:
            return exact.colour
        fuzzy = self._lookup_fuzzy(key)
        return fuzzy.colour if fuzzy is not None else None

    def _lookup_fuzzy(self, key: str) -> Optional[FolderColourRule]:
        best: Optional[FolderColourRule] = None
        best_len = -1
        for rule in self._rules:
            ak = rule.key
            if len(ak) < _MIN_SUBSTRING_ALIAS_LEN:
                continue
            if ak in key and len(ak) > best_len:
                best = rule
                best_len = len(ak)
        if best is not None:
            return best
        best = None
        best_len = -1
        for rule in self._rules:
            ak = rule.key
            if len(ak) < _MIN_PREFIX_ALIAS_LEN:
                continue
            if key.startswith(ak) and len(ak) > best_len:
                best = rule
                best_len = len(ak)
        return best

    def resolve_path_parts(self, parts: Sequence[str]) -> Optional[str]:
        """Deepest matching folder segment wins. ``parts`` = folders under scan root (no file)."""
        if not self._rules or not parts:
            return None
        best_colour: Optional[str] = None
        best_idx = -1
        for i, part in enumerate(parts):
            colour = self.match_segment(part)
            if colour is not None and i >= best_idx:
                best_idx = i
                best_colour = colour
        return best_colour

    def resolve_source_path(self, source_path: str) -> Optional[str]:
        """Match against posix-ish relative ``source_path`` (folders only)."""
        raw = (source_path or "").replace("\\", "/").strip("/")
        if not raw:
            return None
        parts = [p for p in raw.split("/") if p]
        if not parts:
            return None
        # Drop filename if last segment looks like a file
        last = parts[-1]
        if "." in last:
            parts = parts[:-1]
        return self.resolve_path_parts(parts)
