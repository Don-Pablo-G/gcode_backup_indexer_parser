"""Client path-prefix remaps for extract when drive letters differ.

Indexer may store absolute ``scan_root`` as ``C:\\Share\\…`` while a client
sees the same tree as ``Z:\\Share\\…``. Remaps rewrite matching prefixes
(case-insensitive, ``/`` and ``\\`` normalized) before opening sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Iterable, Optional, Sequence, Union

RemapInput = Union["PathRemap", tuple[str, str], list[str], dict[str, str]]


@dataclass(frozen=True)
class PathRemap:
    """One ``from_prefix → to_prefix`` rewrite rule."""

    from_prefix: str
    to_prefix: str

    def __post_init__(self) -> None:
        fr = (self.from_prefix or "").strip()
        to = (self.to_prefix or "").strip()
        object.__setattr__(self, "from_prefix", fr)
        object.__setattr__(self, "to_prefix", to)


def normalize_path_key(path: str | Path) -> str:
    """Casefold + backslash form for prefix compares (Windows-oriented)."""
    raw = str(path or "").strip()
    if not raw:
        return ""
    # PureWindowsPath accepts / and \ ; as_posix then swap → stable \\
    try:
        win = PureWindowsPath(raw)
        s = str(win).replace("/", "\\")
    except Exception:  # noqa: BLE001
        s = raw.replace("/", "\\")
    # Collapse duplicate separators (keep \\server leading UNC)
    while "\\\\" in s[2:]:
        s = s[:2] + s[2:].replace("\\\\", "\\")
    if len(s) > 1 and s.endswith("\\") and not s.endswith(":\\"):
        s = s.rstrip("\\")
    return s.casefold()


def _coerce_remap(item: RemapInput | None) -> Optional[PathRemap]:
    if item is None:
        return None
    if isinstance(item, PathRemap):
        if item.from_prefix and item.to_prefix:
            return item
        return None
    if isinstance(item, dict):
        fr = str(item.get("from") or item.get("from_prefix") or item.get("src") or "").strip()
        to = str(item.get("to") or item.get("to_prefix") or item.get("dst") or "").strip()
        if fr and to:
            return PathRemap(fr, to)
        return None
    if isinstance(item, (tuple, list)) and len(item) >= 2:
        fr = str(item[0] or "").strip()
        to = str(item[1] or "").strip()
        if fr and to:
            return PathRemap(fr, to)
        return None
    return None


def normalize_remaps(items: Optional[Iterable[RemapInput]] = None) -> list[PathRemap]:
    out: list[PathRemap] = []
    seen: set[str] = set()
    for raw in items or []:
        rule = _coerce_remap(raw)
        if rule is None:
            continue
        key = normalize_path_key(rule.from_prefix)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(rule)
    return out


def parse_remap_rules_block(block: str) -> list[PathRemap]:
    """Parse multiline ``FROM => TO`` (also ``->``, ``|``, tab) rules."""
    items: list[PathRemap] = []
    for line in (block or "").splitlines():
        s = line.strip()
        if not s or s.startswith(";") or s.startswith("#"):
            continue
        fr = to = ""
        for sep in ("=>", "->", "|", "\t"):
            if sep in s:
                left, right = s.split(sep, 1)
                fr, to = left.strip(), right.strip()
                break
        if not fr or not to:
            continue
        items.append(PathRemap(fr, to))
    return normalize_remaps(items)


def format_remap_rules_block(remaps: Sequence[PathRemap | tuple[str, str]]) -> str:
    rules = normalize_remaps(remaps)
    if not rules:
        return ""
    return "\n" + "\n".join(f"    {r.from_prefix} => {r.to_prefix}" for r in rules)


def apply_path_remaps(
    path: str | Path | None,
    remaps: Optional[Sequence[RemapInput]] = None,
) -> str:
    """Rewrite ``path`` if it starts with a configured from-prefix.

    Longest matching ``from_prefix`` wins. Empty path / no remaps → unchanged string.
    """
    raw = "" if path is None else str(path)
    if not raw.strip():
        return raw
    rules = normalize_remaps(remaps)
    if not rules:
        return raw

    key = normalize_path_key(raw)
    # Longest from-prefix first
    ranked = sorted(
        rules,
        key=lambda r: len(normalize_path_key(r.from_prefix)),
        reverse=True,
    )
    for rule in ranked:
        fr_key = normalize_path_key(rule.from_prefix)
        if not fr_key:
            continue
        if key == fr_key:
            return rule.to_prefix.rstrip("\\/")
        # Prefix match: from + separator (or drive-root like C:)
        if key.startswith(fr_key):
            rest = key[len(fr_key) :]
            if rest and not rest.startswith("\\"):
                # Avoid matching C:\ShareX when from is C:\Share
                continue
            # Rebuild using original casing from to_prefix + remainder from raw
            raw_norm = str(PureWindowsPath(raw)).replace("/", "\\")
            # Find cut point in original using same length as fr_key on normalized form
            # Walk original with normalized compare length
            cut = _prefix_cut_len(raw_norm, fr_key)
            if cut is None:
                remainder = raw_norm[len(fr_key) :] if len(raw_norm) >= len(fr_key) else rest
            else:
                remainder = raw_norm[cut:]
            to = rule.to_prefix.rstrip("\\/")
            if remainder.startswith(("\\", "/")):
                return to + remainder.replace("/", "\\")
            if remainder:
                return to + "\\" + remainder.replace("/", "\\")
            return to
    return raw


def _prefix_cut_len(raw_norm: str, fr_key: str) -> Optional[int]:
    """Return character index in ``raw_norm`` after a casefold-equal prefix of ``fr_key``."""
    i = 0
    j = 0
    rn = raw_norm.replace("/", "\\")
    fk = fr_key
    while j < len(fk) and i < len(rn):
        a = rn[i]
        b = fk[j]
        if a.casefold() == b.casefold():
            i += 1
            j += 1
            continue
        # Skip extra separators asymmetrically
        if a == "\\":
            i += 1
            continue
        if b == "\\":
            j += 1
            continue
        return None
    if j < len(fk):
        return None
    return i


def remap_root(
    root: str | Path | None,
    remaps: Optional[Sequence[RemapInput]] = None,
) -> Optional[str]:
    """Apply remaps to a scan/backup root; ``None``/blank stays ``None``."""
    if root is None:
        return None
    s = str(root).strip()
    if not s:
        return None
    return apply_path_remaps(s, remaps)
