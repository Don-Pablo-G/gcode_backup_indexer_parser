"""Folder **roles** catalog + path-segment alias rules.

Sidecar next to the database: ``folder_colour_aliases.yaml`` (filename kept for
compat; content is roles, not green/yellow status).

**Status** (🟢 on-machine / 🟡 status unknown) comes from scan roots only and is
stored on ``program_instances.provenance`` (``backup`` / ``extra``). Folder
aliases never override status. Yellow status must never be labelled as a role
(e.g. fixture).

**Role** is the editable catalogue (prototype, personal, system_programs,
fixture, …) plus path aliases. Schema (v3)::

    colours:   # role definitions (id kept as ``colours`` key for YAML compat)
      - id: prototype
        label_pl: Prototyp
        …
      - id: personal
        …
    rules:
      - alias: Pawel
        colour: personal     # role id, or ``exclude``
      - alias: scrap
        colour: exclude

Legacy files that still list green/yellow (``backup``/``extra``) as colours are
migrated on load: those ids are stripped from the role catalogue; rules that
pointed at status colours are **dropped** (status is not a role — never remap
yellow→fixture). Old seeds (production / wip / test) are kept as non-builtin
customs when present; new seeds are ensured.
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
    ROLE_FIXTURE,
    ROLE_LEGACY_IDS,
    ROLE_PERSONAL,
    ROLE_PRODUCTION,
    ROLE_PROTOTYPE,
    ROLE_SEED_IDS,
    ROLE_SYSTEM_PROGRAMS,
    ROLE_TEST,
    ROLE_WIP,
    STATUS_VALUES,
)

FOLDER_COLOUR_ALIASES_FILENAME = "folder_colour_aliases.yaml"

_MIN_SUBSTRING_ALIAS_LEN = 4
_MIN_PREFIX_ALIAS_LEN = 3

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

# Status colour spellings → status ids (NOT roles). Rules using these are dropped.
_STATUS_LEGACY_NAMES = {
    "green": PROVENANCE_BACKUP,
    "backup": PROVENANCE_BACKUP,
    "machine": PROVENANCE_BACKUP,
    "ran": PROVENANCE_BACKUP,
    "on_machine": PROVENANCE_BACKUP,
    "yellow": PROVENANCE_EXTRA,
    "extra": PROVENANCE_EXTRA,
    "other": PROVENANCE_EXTRA,
    "not_run": PROVENANCE_EXTRA,
    "unknown": PROVENANCE_EXTRA,
    "status_unknown": PROVENANCE_EXTRA,
}

# Colour-name shortcuts → role ids (never map green/yellow here)
_LEGACY_COLOUR_NAMES = {
    "blue": ROLE_PROTOTYPE,
    "prototype": ROLE_PROTOTYPE,
    "proto": ROLE_PROTOTYPE,
    "red": ROLE_PERSONAL,
    "personal": ROLE_PERSONAL,
    "orange": ROLE_SYSTEM_PROGRAMS,
    "system": ROLE_SYSTEM_PROGRAMS,
    "system_programs": ROLE_SYSTEM_PROGRAMS,
    "system_program": ROLE_SYSTEM_PROGRAMS,
    "purple": ROLE_FIXTURE,
    "violet": ROLE_FIXTURE,
    "fixture": ROLE_FIXTURE,
    # Legacy role ids still resolve (optional customs, not auto-seeded)
    "production": ROLE_PRODUCTION,
    "wip": ROLE_WIP,
    "work": ROLE_WIP,
    "test": ROLE_TEST,
    "exclude": COLOUR_EXCLUDE,
    "skip": COLOUR_EXCLUDE,
    "ignore": COLOUR_EXCLUDE,
}

# Old catalogue colour ids that are now status-only (strip from role catalog)
_STATUS_COLOUR_IDS = frozenset(STATUS_VALUES)


def is_status_colour_id(raw: str | None) -> bool:
    """True when ``raw`` names a scan-root status, not a folder role."""
    key = (raw or "").strip().casefold().replace(" ", "_").replace("-", "_")
    if not key:
        return False
    if key in _STATUS_COLOUR_IDS:
        return True
    return key in _STATUS_LEGACY_NAMES


def normalize_colour_id(raw: str | None, *, known_ids: Optional[set[str]] = None) -> str:
    """Map a role label/id to a stable id, or ``exclude``.

    Unknown free-form ids are kept if they look like ids (or are in ``known_ids``);
    otherwise fall back to ``prototype``. Status spellings (green/yellow/…) resolve
    to status ids — callers must not store those as roles.
    """
    key = (raw or "").strip().casefold().replace(" ", "_").replace("-", "_")
    if not key:
        return ROLE_PROTOTYPE
    if key in _STATUS_LEGACY_NAMES:
        return _STATUS_LEGACY_NAMES[key]
    if key in _STATUS_COLOUR_IDS:
        return key
    if key in _LEGACY_COLOUR_NAMES:
        return _LEGACY_COLOUR_NAMES[key]
    if known_ids is not None and key in known_ids:
        return key
    if key == COLOUR_EXCLUDE:
        return COLOUR_EXCLUDE
    if _ID_RE.match(key):
        return key
    return ROLE_PROTOTYPE


# Back-compat alias used by older imports / GUI
def normalize_colour(raw: str | None) -> str:
    return normalize_colour_id(raw)


# Preset chips for the folder-role editor — exclude green/yellow (status only).
COLOUR_PRESET_SWATCHES: tuple[str, ...] = (
    "#2980B9",  # blue — prototype
    "#C0392B",  # red — personal
    "#E67E22",  # orange — system programs
    "#8E44AD",  # purple — fixture
    "#16A085",  # teal
    "#7F8C8D",  # grey
    "#2C3E50",  # dark
)


def normalize_hex_colour(raw: str | None, *, fallback: str = "#888888") -> str:
    """Return ``#RRGGBB`` uppercased, or ``fallback`` when invalid."""
    s = (raw or "").strip()
    if not s:
        return fallback
    if not s.startswith("#"):
        s = "#" + s
    if len(s) == 4 and all(c in "0123456789abcdefABCDEF" for c in s[1:]):
        s = "#" + "".join(ch * 2 for ch in s[1:])
    if len(s) == 7 and all(c in "0123456789abcdefABCDEF" for c in s[1:]):
        return s.upper()
    return fallback


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
        self.swatch = normalize_hex_colour(self.swatch)
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
    """Seed roles (not status). Blue / red / orange / purple — never yellow."""
    return [
        ColourDef(
            id=ROLE_PROTOTYPE,
            label_pl="Prototyp",
            label_en="Prototype",
            swatch="#2980B9",
            meaning_pl="Prototyp / program roboczy",
            meaning_en="Prototype / work-in-progress program",
            badge="●",
            builtin=True,
        ),
        ColourDef(
            id=ROLE_PERSONAL,
            label_pl="Osobisty",
            label_en="Personal",
            swatch="#C0392B",
            meaning_pl="Folder osobisty operatora",
            meaning_en="Operator personal folder",
            badge="●",
            builtin=True,
        ),
        ColourDef(
            id=ROLE_SYSTEM_PROGRAMS,
            label_pl="Programy systemowe",
            label_en="System programs",
            swatch="#E67E22",
            meaning_pl="Programy systemowe / sterowania",
            meaning_en="System / control programs",
            badge="●",
            builtin=True,
        ),
        ColourDef(
            id=ROLE_FIXTURE,
            label_pl="Przyrząd",
            label_en="Fixture",
            swatch="#8E44AD",
            meaning_pl="Przyrząd / uchwyt / pomocniczy",
            meaning_en="Fixture / workholding / helper",
            badge="●",
            builtin=True,
        ),
    ]


default_roles = default_colours


@dataclass(frozen=True)
class FolderColourRule:
    """One folder-name alias → role id or exclude."""

    alias: str
    colour: str = ROLE_PROTOTYPE

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
            # Status ids are never roles — drop legacy green/yellow rules
            # (previously yellow was wrongly remapped to fixture).
            if colour in _STATUS_COLOUR_IDS or is_status_colour_id(rule.colour):
                continue
            cleaned.append(FolderColourRule(alias=rule.alias, colour=colour))
        self.rules = cleaned

    @property
    def colour_ids(self) -> set[str]:
        return {c.id for c in self.colours}

    def get(self, colour_id: str) -> Optional[ColourDef]:
        cid = normalize_colour_id(colour_id, known_ids=self.colour_ids)
        if cid in _STATUS_COLOUR_IDS:
            return None
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
        return colour_id or ROLE_PROTOTYPE

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
    """Ensure role seeds exist; strip status ids; demote old seeds to customs.

    - New seeds (prototype / personal / system_programs / fixture) are builtins
      with the canonical swatches (blue / red / orange / purple).
    - User label/meaning edits on seeds are preserved; seed swatches are refreshed
      so yellow never remains a role colour and fixture is purple.
    - Legacy seeds (production / wip / test) are kept when present but not
      auto-added and not builtin — user customs are never wiped.
    """
    defaults = {c.id: c for c in default_colours()}
    by_id: dict[str, ColourDef] = {}
    order: list[str] = []
    for c in colours or []:
        if not c.id or c.id == COLOUR_EXCLUDE or c.id in by_id:
            continue
        # green/yellow were status — do not keep them as roles
        if c.id in _STATUS_COLOUR_IDS or is_status_colour_id(c.id):
            continue
        if c.id in defaults:
            d = defaults[c.id]
            by_id[c.id] = ColourDef(
                id=c.id,
                label_pl=c.label_pl or d.label_pl,
                label_en=c.label_en or d.label_en,
                # Canonical seed swatch (blue/red/orange/purple)
                swatch=d.swatch,
                meaning_pl=c.meaning_pl if c.meaning_pl else d.meaning_pl,
                meaning_en=c.meaning_en if c.meaning_en else d.meaning_en,
                badge=c.badge or d.badge,
                builtin=True,
            )
        elif c.id in ROLE_LEGACY_IDS:
            # Former builtins — keep data, no longer locked seeds
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
    seed_order = list(ROLE_SEED_IDS)
    builtins = [by_id[i] for i in seed_order if i in by_id]
    custom = [by_id[i] for i in order if i not in seed_order]
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
        if not item.alias:
            return None
        if item.colour in _STATUS_COLOUR_IDS or is_status_colour_id(item.colour):
            return None
        return item
    if isinstance(item, str):
        alias = item.strip()
        return FolderColourRule(alias=alias, colour=ROLE_PROTOTYPE) if alias else None
    if isinstance(item, dict):
        alias = str(item.get("alias") or item.get("name") or item.get("folder") or "").strip()
        if not alias:
            return None
        colour = (
            item.get("colour")
            or item.get("color")
            or item.get("role")
            or item.get("provenance")
            or item.get("flag")
        )
        cid = normalize_colour_id(str(colour or ROLE_PROTOTYPE), known_ids=known_ids)
        if cid in _STATUS_COLOUR_IDS:
            return None
        return FolderColourRule(alias=alias, colour=cid)
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
            "Folder roles + path aliases (v3). "
            "Status (🟢 on-machine / 🟡 status unknown) comes from scan roots, not these rules. "
            "Seed roles: prototype (blue), personal (red), system_programs (orange), fixture (purple). "
            "Yellow/green are status only — never role labels (yellow ≠ fixture). "
            "rules: folder-name alias → role id or exclude; deepest segment wins."
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
        self._known = set(known_ids or ()) | set(ROLE_SEED_IDS) | set(ROLE_LEGACY_IDS) | {
            COLOUR_EXCLUDE,
            PROVENANCE_WIP,  # legacy role id still accepted
        }
        self._rules: list[FolderColourRule] = []
        self._by_key: dict[str, FolderColourRule] = {}
        for rule in rules or []:
            if not rule.alias or not rule.key:
                continue
            colour = normalize_colour_id(rule.colour, known_ids=self._known)
            if colour in _STATUS_COLOUR_IDS or is_status_colour_id(rule.colour):
                continue
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
