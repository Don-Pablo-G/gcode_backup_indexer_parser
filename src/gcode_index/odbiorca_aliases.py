"""Odbiorca (recipient/customer) catalogue + name-wide folder aliases.

Third name-wide alias axis (alongside machine and role). **One** odbiorca per
program — never overrides status, machine, or roles.

Sidecar next to the database: ``odbiorcy.yaml``::

    version: 1
    odbiorcy:
      - id: acme
        label_pl: Acme Sp. z o.o.
        label_en: Acme Ltd
    rules:
      - alias: Acme
        odbiorca_id: acme
        exact: true

Tree / Nazwy folderów create **exact** name rules (same safety as machine/role).
Path tree map may override with ``odbiorca_id`` on a prefix (like ``machine_id``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import yaml

from gcode_index.aliases import normalize_folder_name

ODBIORCY_FILENAME = "odbiorcy.yaml"

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def odbiorcy_path_for_target(target: Path | str) -> Path:
    return Path(target) / ODBIORCY_FILENAME


def normalize_odbiorca_id(raw: str | None) -> str:
    s = (raw or "").strip().casefold().replace(" ", "_").replace("-", "_")
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s


def is_valid_odbiorca_id(raw: str | None) -> bool:
    return bool(_ID_RE.fullmatch(normalize_odbiorca_id(raw) or ""))


@dataclass
class OdbiorcaDef:
    id: str
    label_pl: str = ""
    label_en: str = ""

    def __post_init__(self) -> None:
        self.id = normalize_odbiorca_id(self.id)
        self.label_pl = (self.label_pl or "").strip() or self.id
        self.label_en = (self.label_en or "").strip() or self.label_pl

    def label(self, lang: str = "pl") -> str:
        if (lang or "pl").lower().startswith("en"):
            return self.label_en or self.label_pl
        return self.label_pl or self.label_en

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label_pl": self.label_pl,
            "label_en": self.label_en,
        }


@dataclass
class OdbiorcaRule:
    alias: str
    odbiorca_id: str
    exact: bool = True

    def __post_init__(self) -> None:
        self.alias = (self.alias or "").strip()
        self.odbiorca_id = normalize_odbiorca_id(self.odbiorca_id)
        self.exact = bool(self.exact)

    @property
    def key(self) -> str:
        return normalize_folder_name(self.alias)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "alias": self.alias,
            "odbiorca_id": self.odbiorca_id,
        }
        if self.exact:
            d["exact"] = True
        return d


@dataclass
class OdbiorcaCatalog:
    odbiorcy: list[OdbiorcaDef] = field(default_factory=list)
    rules: list[OdbiorcaRule] = field(default_factory=list)

    def get(self, oid: str) -> Optional[OdbiorcaDef]:
        key = normalize_odbiorca_id(oid)
        for o in self.odbiorcy:
            if o.id == key:
                return o
        return None

    @property
    def ids(self) -> set[str]:
        return {o.id for o in self.odbiorcy if o.id}

    def label_for(self, oid: str | None, lang: str = "pl") -> str:
        if not oid:
            return ""
        o = self.get(oid)
        return o.label(lang) if o else str(oid)

    def displays(self, lang: str = "pl") -> list[str]:
        return [f"{o.label(lang)} ({o.id})" for o in self.odbiorcy]

    def alias_map(self) -> "OdbiorcaAliasMap":
        return OdbiorcaAliasMap(self.rules, known_ids=self.ids)


def _parse_odbiorca(item: Any) -> Optional[OdbiorcaDef]:
    if not isinstance(item, dict):
        return None
    oid = normalize_odbiorca_id(str(item.get("id") or ""))
    if not oid:
        return None
    return OdbiorcaDef(
        id=oid,
        label_pl=str(item.get("label_pl") or item.get("label") or oid),
        label_en=str(item.get("label_en") or item.get("label") or ""),
    )


def _parse_rule(item: Any) -> Optional[OdbiorcaRule]:
    if not isinstance(item, dict):
        return None
    alias = str(item.get("alias") or item.get("folder") or item.get("name") or "").strip()
    oid = normalize_odbiorca_id(
        str(item.get("odbiorca_id") or item.get("odbiorca") or item.get("id") or "")
    )
    if not alias or not oid:
        return None
    exact = item.get("exact")
    if exact is None:
        exact = True
    return OdbiorcaRule(alias=alias, odbiorca_id=oid, exact=bool(exact))


def load_odbiorca_catalog(path: Path | str | None) -> OdbiorcaCatalog:
    if path is None:
        return OdbiorcaCatalog()
    p = Path(path)
    if not p.is_file():
        return OdbiorcaCatalog()
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return OdbiorcaCatalog()
    if not isinstance(data, dict):
        return OdbiorcaCatalog()
    odbiorcy: list[OdbiorcaDef] = []
    seen: set[str] = set()
    for item in data.get("odbiorcy") or data.get("recipients") or []:
        o = _parse_odbiorca(item)
        if o is None or o.id in seen:
            continue
        seen.add(o.id)
        odbiorcy.append(o)
    rules: list[OdbiorcaRule] = []
    known = {o.id for o in odbiorcy}
    for item in data.get("rules") or []:
        r = _parse_rule(item)
        if r is None:
            continue
        # Keep rules even if catalogue id missing (user may re-add)
        if known and r.odbiorca_id not in known:
            # still keep — orphan rule until catalogue restored
            pass
        rules.append(r)
    return OdbiorcaCatalog(odbiorcy=odbiorcy, rules=rules)


def save_odbiorca_catalog(path: Path | str, catalog: OdbiorcaCatalog) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "odbiorcy": [o.to_dict() for o in catalog.odbiorcy],
        "rules": [r.to_dict() for r in catalog.rules],
    }
    p.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return p


class OdbiorcaAliasMap:
    """Name → odbiorca_id rules. Exact rules preferred; deepest path segment wins."""

    def __init__(
        self,
        rules: Iterable[OdbiorcaRule] | None = None,
        *,
        known_ids: Iterable[str] | None = None,
    ) -> None:
        self._rules = list(rules or [])
        self._known = set(known_ids or ())
        self._by_key: dict[str, OdbiorcaRule] = {}
        for r in self._rules:
            if r.key:
                self._by_key[r.key] = r

    def __len__(self) -> int:
        return len(self._rules)

    @property
    def rules(self) -> list[OdbiorcaRule]:
        return list(self._rules)

    @classmethod
    def empty(cls) -> "OdbiorcaAliasMap":
        return cls([])

    @classmethod
    def load(cls, path: Path | str | None) -> "OdbiorcaAliasMap":
        cat = load_odbiorca_catalog(path)
        return cat.alias_map()

    def rule_for_name(self, folder_raw: str) -> Optional[OdbiorcaRule]:
        key = normalize_folder_name(folder_raw)
        return self._by_key.get(key) if key else None

    def match_segment(self, folder_raw: str) -> Optional[str]:
        rule = self.rule_for_name(folder_raw)
        if rule is None:
            return None
        return rule.odbiorca_id or None

    def resolve_path_parts(self, parts: Sequence[str]) -> Optional[str]:
        """Deepest matching segment wins (one odbiorca)."""
        hit: Optional[str] = None
        for part in parts:
            oid = self.match_segment(part)
            if oid:
                hit = oid
        return hit

    def resolve_source_path(self, source_path: str) -> Optional[str]:
        try:
            parts = Path(source_path).parts
        except Exception:
            parts = ()
        # Drop filename
        if parts and "." in Path(parts[-1]).name:
            parts = parts[:-1]
        return self.resolve_path_parts([str(p) for p in parts])

    def upsert_exact(self, alias: str, odbiorca_id: str) -> OdbiorcaRule:
        new = OdbiorcaRule(
            alias=alias,
            odbiorca_id=normalize_odbiorca_id(odbiorca_id),
            exact=True,
        )
        key = new.key
        self._rules = [r for r in self._rules if r.key != key]
        self._rules.append(new)
        self._by_key[key] = new
        return new


def display_for_odbiorca(oid: str, label: Optional[str] = None) -> str:
    mid = (oid or "").strip()
    lab = (label or "").strip()
    if lab and lab != mid:
        return f"{lab} ({mid})"
    return mid or "—"


def parse_odbiorca_display(raw: str) -> tuple[str, str]:
    """Parse ``Label (id)`` → (id, label)."""
    s = (raw or "").strip()
    if not s or s == "—":
        return "", ""
    if s.endswith(")") and "(" in s:
        label, _, rest = s.rpartition("(")
        oid = rest[:-1].strip()
        return normalize_odbiorca_id(oid), label.strip()
    return normalize_odbiorca_id(s), s


# --- Header-window odbiorca match (fill-if-empty at scan) -------------------

# Same spirit as other alias mins; short tokens (LP1, OK, …) are skipped.
MIN_HEADER_ODBIORCA_NEEDLE = 3
# Align with whole-file .nc O-header scan window.
HEADER_ODBIORCA_SCAN_LINES = 40

_ALL_PARENS = re.compile(r"\(([^)]*)\)")


def extract_header_paren_comments(
    path: Path | str,
    *,
    byte_start: Optional[int] = None,
    max_lines: int = HEADER_ODBIORCA_SCAN_LINES,
) -> list[str]:
    """Paren comment texts from the header window (not the full body).

    For whole-file programs ``byte_start`` is None → first ``max_lines`` lines.
    For glued dumps, seek to ``byte_start`` and read ``max_lines`` from there.
    """
    p = Path(path)
    if not p.is_file():
        return []
    comments: list[str] = []
    try:
        with open(p, "rb") as f:
            if byte_start is not None and byte_start > 0:
                try:
                    f.seek(int(byte_start))
                except OSError:
                    f.seek(0)
            for _ in range(max(1, int(max_lines))):
                raw = f.readline()
                if not raw:
                    break
                try:
                    line = raw.decode("ascii", errors="replace").rstrip("\r\n")
                except Exception:
                    continue
                for m in _ALL_PARENS.finditer(line):
                    text = (m.group(1) or "").strip()
                    if text:
                        comments.append(text)
    except OSError:
        return []
    return comments


def match_odbiorca_in_comments(
    comments: Sequence[str],
    odbiorca_map: "OdbiorcaAliasMap",
    *,
    min_needle: int = MIN_HEADER_ODBIORCA_NEEDLE,
) -> Optional[str]:
    """Best single odbiorca_id from alias needles in comment texts.

    Uses ``normalize_folder_name`` on both sides. Exact normalized equality beats
    substring; longest needle wins. Aliases only (not catalogue labels).
    """
    if not comments or odbiorca_map is None or len(odbiorca_map) == 0:
        return None
    needles: list[tuple[str, int, str]] = []
    seen_keys: set[str] = set()
    for rule in odbiorca_map.rules:
        key = rule.key
        if not key or len(key) < min_needle:
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        oid = (rule.odbiorca_id or "").strip()
        if not oid:
            continue
        needles.append((key, len(key), oid))
    if not needles:
        return None
    # Longer first so first exact/substring hit among equal scores is stable
    needles.sort(key=lambda t: (-t[1], t[0]))

    best: Optional[tuple[int, int, str]] = None  # (exact, length, oid)
    for raw in comments:
        norm = normalize_folder_name(raw)
        if not norm or len(norm) < min_needle:
            continue
        for key, length, oid in needles:
            if key == norm:
                cand = (1, length, oid)
            elif key in norm:
                cand = (0, length, oid)
            else:
                continue
            if best is None or cand > best:
                best = cand
    return best[2] if best else None


def match_odbiorca_from_header(
    path: Path | str,
    odbiorca_map: "OdbiorcaAliasMap",
    *,
    byte_start: Optional[int] = None,
    min_needle: int = MIN_HEADER_ODBIORCA_NEEDLE,
    max_lines: int = HEADER_ODBIORCA_SCAN_LINES,
) -> Optional[str]:
    """Resolve one odbiorca_id from header-window paren comments, or None."""
    comments = extract_header_paren_comments(
        path, byte_start=byte_start, max_lines=max_lines
    )
    return match_odbiorca_in_comments(
        comments, odbiorca_map, min_needle=min_needle
    )
