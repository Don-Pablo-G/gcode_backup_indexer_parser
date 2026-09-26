"""Folder colours catalog + path-segment alias rules.

Sidecar next to the database: ``folder_colour_aliases.yaml``.

Schema (v2)::

    colours:
      - id: backup
        label_pl: Zielona
        label_en: Green
        swatch: "#1a7f37"
        meaning_pl: …
        meaning_en: …
        badge: "🟢"
      - id: quarantine
        label_pl: Kwarantanna
        swatch: "#e67e22"
        …
    rules:
      - alias: Pawel
        colour: wip          # colour id, or ``exclude``
      - alias: scrap
        colour: exclude

Legacy v1 files with only ``rules:`` (hard-coded green/yellow/red) still load:
default colours are seeded and rule colour names are normalized to ids.

Matching walks path segments under the owning scan root (folders only).
The **deepest** matching segment wins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import yaml

from gcode_index.aliases import normalize_folder_name
from gcode_index.models import (
    COLOUR_EXCLUDE,
    PROVENANCE_BACKUP,
    PROVENANCE_EXTRA,
    PROVENANCE_WIP,
)

FOLDER_COLOUR_ALIASES_FILENAME = "folder_colour_aliases.yaml"

_MIN_SUBSTRING_ALIAS_LEN = 4
_MIN_PREFIX_ALIAS_LEN = 3

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

# Legacy colour name → colour id (also used when parsing rules without a catalog)
_LEGACY_COLOUR_NAMES = {
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


def normalize_colour_id(raw: str | None, *, known_ids: Optional[set[str]] = None) -> str:
    """Map a colour label/id to a stable id, or ``exclude``.

    Unknown free-form ids are kept if they look like ids (or are in ``known_ids``);
    otherwise fall back to ``extra``.
    """
    key = (raw or "").strip().casefold().replace(" ", "_").replace("-", "_")
    if not key:
        return PROVENANCE_EXTRA
    if key in _LEGACY_COLOUR_NAMES:
        return _LEGACY_COLOUR_NAMES[key]
    if known_ids is not None and key in known_ids:
        return key
    if key == COLOUR_EXCLUDE:
        return COLOUR_EXCLUDE
    if _ID_RE.match(key):
        return key
    return PROVENANCE_EXTRA


# Back-compat alias used by older imports / GUI
def normalize_colour(raw: str | None) -> str:
    return normalize_colour_id(raw)


@dataclass
class ColourDef:
    """One user-visible provenance colour."""

    id: str
    label_pl: str = ""
    label_en: str = ""
    swatch: str = "#888888"
    meaning_pl: str = ""
    meaning_en: str = ""
    badge: str = "●"
    builtin: bool = False

    def __post_init__(self) -> None:
        raw_id = (self.id or "").strip()
        cid = normalize_colour_id(raw_id) if raw_id else "custom"
        if cid == COLOUR_EXCLUDE:
            cid = "custom"
        if not _ID_RE.match(cid):
            cid = re.sub(r"[^a-z0-9_]", "", raw_id.casefold()) or "custom"
            if cid[0].isdigit():
                cid = "c_" + cid
        self.id = cid
        self.label_pl = (self.label_pl or self.label_en or cid).strip()
        self.label_en = (self.label_en or self.label_pl or cid).strip()
        sw = (self.swatch or "#888888").strip()
        if not re.match(r"^#[0-9A-Fa-f]{6}$", sw):
            sw = "#888888"
        self.swatch = sw
        self.meaning_pl = (self.meaning_pl or "").strip()
        self.meaning_en = (self.meaning_en or "").strip()
        self.badge = (self.badge or "●").strip() or "●"

    def label(self, lang: str = "pl") -> str:
        if str(lang).casefold().startswith("en"):
            return self.label_en or self.label_pl or self.id
        return self.label_pl or self.label_en or self.id

    def meaning(self, lang: str = "pl") -> str:
        if str(lang).casefold().startswith("en"):
            return self.meaning_en or self.meaning_pl
        return self.meaning_pl or self.meaning_en

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label_pl": self.label_pl,
            "label_en": self.label_en,
            "swatch": self.swatch,
            "meaning_pl": self.meaning_pl,
            "meaning_en": self.meaning_en,
            "badge": self.badge,
            "builtin": bool(self.builtin),
        }


def default_colours() -> list[ColourDef]:
    """Seed: green / yellow / red — ids stay backup / extra / wip for DB compat."""
    return [
        ColourDef(
            id=PROVENANCE_BACKUP,
            label_pl="Zielona",
            label_en="Green",
            swatch="#1a7f37",
            meaning_pl="Kopia / z maszyny (była na maszynie)",
            meaning_en="Backup / on-machine (ran on the machine)",
            badge="🟢",
            builtin=True,
        ),
        ColourDef(
            id=PROVENANCE_EXTRA,
            label_pl="Żółta",
            label_en="Yellow",
            swatch="#b58900",
            meaning_pl="Dodatkowa — nie z kopii maszyny",
            meaning_en="Extra — not from the machine backup",
            badge="🟡",
            builtin=True,
        ),
        ColourDef(
            id=PROVENANCE_WIP,
            label_pl="Czerwona (WIP)",
            label_en="Red (WIP)",
            swatch="#c0392b",
            meaning_pl="WIP / nie produkcja",
            meaning_en="WIP / not production-ready",
            badge="🔴",
            builtin=True,
        ),
    ]


@dataclass(frozen=True)
class FolderColourRule:
    """One folder-name alias → colour id or exclude."""

    alias: str
    colour: str = PROVENANCE_EXTRA

    def __post_init__(self) -> None:
        object.__setattr__(self, "alias", (self.alias or "").strip())
        object.__setattr__(self, "colour", normalize_colour_id(self.colour))

    @property
    def key(self) -> str:
        return normalize_folder_name(self.alias)

    def to_dict(self) -> dict[str, str]:
        return {"alias": self.alias, "colour": self.colour}


@dataclass
class ColourCatalog:
    """Colours + folder alias rules for one database folder."""

    colours: list[ColourDef] = field(default_factory=default_colours)
    rules: list[FolderColourRule] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.colours = _merge_with_defaults(self.colours)
        seen: set[str] = set()
        cleaned: list[FolderColourRule] = []
        known = {c.id for c in self.colours}
        for rule in self.rules:
            if not rule.alias or not rule.key or rule.key in seen:
                continue
            seen.add(rule.key)
            colour = normalize_colour_id(rule.colour, known_ids=known)
            cleaned.append(FolderColourRule(alias=rule.alias, colour=colour))
        self.rules = cleaned

    @property
    def colour_ids(self) -> set[str]:
        return {c.id for c in self.colours}

    def get(self, colour_id: str) -> Optional[ColourDef]:
        cid = normalize_colour_id(colour_id, known_ids=self.colour_ids)
        for c in self.colours:
            if c.id == cid:
                return c
        return None

    def label_for(self, colour_id: str, lang: str = "pl") -> str:
        c = self.get(colour_id)
        if c is not None:
            return c.label(lang)
        if colour_id == COLOUR_EXCLUDE:
            return "exclude"
        return colour_id or PROVENANCE_BACKUP

    def badge_for(self, colour_id: str) -> str:
        c = self.get(colour_id)
        return c.badge if c is not None else "●"

    def swatch_for(self, colour_id: str) -> str:
        c = self.get(colour_id)
        return c.swatch if c is not None else "#888888"

    def meaning_for(self, colour_id: str, lang: str = "pl") -> str:
        c = self.get(colour_id)
        return c.meaning(lang) if c is not None else ""

    def alias_map(self) -> "FolderColourAliasMap":
        return FolderColourAliasMap(self.rules, known_ids=self.colour_ids)


def _merge_with_defaults(colours: Sequence[ColourDef] | None) -> list[ColourDef]:
    """Ensure seed colours exist; user edits to labels/meanings/swatches win."""
    defaults = {c.id: c for c in default_colours()}
    by_id: dict[str, ColourDef] = {}
    order: list[str] = []
    for c in colours or []:
        if not c.id or c.id == COLOUR_EXCLUDE or c.id in by_id:
            continue
        if c.id in defaults:
            d = defaults[c.id]
            by_id[c.id] = ColourDef(
                id=c.id,
                label_pl=c.label_pl or d.label_pl,
                label_en=c.label_en or d.label_en,
                swatch=c.swatch or d.swatch,
                meaning_pl=c.meaning_pl,  # allow empty override
                meaning_en=c.meaning_en,
                badge=c.badge or d.badge,
                builtin=True,
            )
        else:
            by_id[c.id] = ColourDef(
                id=c.id,
                label_pl=c.label_pl,
                label_en=c.label_en,
                swatch=c.swatch,
                meaning_pl=c.meaning_pl,
                meaning_en=c.meaning_en,
                badge=c.badge,
                builtin=False,
            )
        order.append(c.id)
    for did, d in defaults.items():
        if did not in by_id:
            by_id[did] = d
            order.append(did)
    seed_order = [PROVENANCE_BACKUP, PROVENANCE_EXTRA, PROVENANCE_WIP]
    builtins = [by_id[i] for i in seed_order if i in by_id]
    custom = [by_id[i] for i in order if i not in seed_order]
    # also any leftover
    seen = {c.id for c in builtins + custom}
    for i, c in by_id.items():
        if i not in seen:
            custom.append(c)
    return builtins + custom


def folder_colour_aliases_path_for_target(target: Path | str) -> Path:
    return Path(target) / FOLDER_COLOUR_ALIASES_FILENAME


def _parse_colour_def(item: Any) -> Optional[ColourDef]:
    if isinstance(item, ColourDef):
        return item
    if not isinstance(item, dict):
        return None
    cid = str(item.get("id") or item.get("colour") or item.get("color") or "").strip()
    if not cid:
        return None
    label = str(item.get("label") or "").strip()
    return ColourDef(
        id=cid,
        label_pl=str(item.get("label_pl") or label or ""),
        label_en=str(item.get("label_en") or label or ""),
        swatch=str(item.get("swatch") or item.get("hex") or "#888888"),
        meaning_pl=str(item.get("meaning_pl") or item.get("meaning") or item.get("description_pl") or ""),
        meaning_en=str(item.get("meaning_en") or item.get("description_en") or item.get("description") or ""),
        badge=str(item.get("badge") or item.get("emoji") or "●"),
        builtin=bool(item.get("builtin", False)),
    )


def _parse_rule(item: Any, *, known_ids: Optional[set[str]] = None) -> Optional[FolderColourRule]:
    if isinstance(item, FolderColourRule):
        return item if item.alias else None
    if isinstance(item, str):
        alias = item.strip()
        return FolderColourRule(alias=alias, colour=PROVENANCE_EXTRA) if alias else None
    if isinstance(item, dict):
        alias = str(item.get("alias") or item.get("name") or item.get("folder") or "").strip()
        if not alias:
            return None
        colour = item.get("colour") or item.get("color") or item.get("provenance") or item.get("flag")
        return FolderColourRule(
            alias=alias,
            colour=normalize_colour_id(str(colour or PROVENANCE_EXTRA), known_ids=known_ids),
        )
    return None


def load_colour_catalog(path: Path | str) -> ColourCatalog:
    """Load colours + rules; seed defaults when missing. Migrates v1 (rules-only)."""
    p = Path(path)
    if not p.is_file():
        return ColourCatalog()
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ColourCatalog()

    raw_colours: list[Any] = []
    raw_rules: list[Any] = []
    if isinstance(data, list):
        # Ambiguous legacy list — treat as rules
        raw_rules = data
    elif isinstance(data, dict):
        raw_colours = list(data.get("colours") or data.get("colors") or [])
        raw_rules = list(data.get("rules") or data.get("aliases") or [])

    colours: list[ColourDef] = []
    for item in raw_colours:
        c = _parse_colour_def(item)
        if c is not None:
            colours.append(c)

    known = {c.id for c in _merge_with_defaults(colours)}
    rules: list[FolderColourRule] = []
    seen: set[str] = set()
    for item in raw_rules:
        rule = _parse_rule(item, known_ids=known)
        if rule is None or not rule.alias or rule.key in seen:
            continue
        seen.add(rule.key)
        rules.append(rule)
    return ColourCatalog(colours=colours, rules=rules)


def save_colour_catalog(path: Path | str, catalog: ColourCatalog) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cat = catalog if isinstance(catalog, ColourCatalog) else ColourCatalog()
    payload = {
        "_comment": (
            "Folder colours + path aliases. "
            "colours: id, labels, swatch, meaning, badge. "
            "rules: folder-name alias → colour id or exclude; deepest segment wins."
        ),
        "colours": [c.to_dict() for c in cat.colours],
        "rules": [r.to_dict() for r in cat.rules],
    }
    p.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return p


# --- Back-compat wrappers -------------------------------------------------------


def load_folder_colour_rules(path: Path | str) -> list[FolderColourRule]:
    return load_colour_catalog(path).rules


def save_folder_colour_rules(path: Path | str, rules: Iterable[FolderColourRule]) -> Path:
    """Save rules while preserving any colours already in the file."""
    existing = load_colour_catalog(path)
    return save_colour_catalog(
        path,
        ColourCatalog(colours=list(existing.colours), rules=list(rules)),
    )


class FolderColourAliasMap:
    """Match folder path segments against colour / exclude rules."""

    def __init__(
        self,
        rules: Sequence[FolderColourRule] | None = None,
        *,
        known_ids: Optional[set[str]] = None,
    ) -> None:
        self._known = set(known_ids or ()) | {
            PROVENANCE_BACKUP,
            PROVENANCE_EXTRA,
            PROVENANCE_WIP,
            COLOUR_EXCLUDE,
        }
        self._rules: list[FolderColourRule] = []
        self._by_key: dict[str, FolderColourRule] = {}
        for rule in rules or []:
            if not rule.alias or not rule.key:
                continue
            colour = normalize_colour_id(rule.colour, known_ids=self._known)
            r = FolderColourRule(alias=rule.alias, colour=colour)
            self._rules.append(r)
            self._by_key[r.key] = r

    @classmethod
    def load(cls, path: Path | str) -> "FolderColourAliasMap":
        cat = load_colour_catalog(path)
        return cat.alias_map()

    @classmethod
    def empty(cls) -> "FolderColourAliasMap":
        return cls([])

    @property
    def rules(self) -> list[FolderColourRule]:
        return list(self._rules)

    def __len__(self) -> int:
        return len(self._rules)

    def match_segment(self, folder_raw: str) -> Optional[str]:
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
        raw = (source_path or "").replace("\\", "/").strip("/")
        if not raw:
            return None
        parts = [p for p in raw.split("/") if p]
        if not parts:
            return None
        last = parts[-1]
        if "." in last:
            parts = parts[:-1]
        return self.resolve_path_parts(parts)
