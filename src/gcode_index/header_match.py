"""O-number-line paren-comment matching for odbiorca / role / machine.

Reuses the same extract as odbiorca: paren comments on the program-number
(``O#####``) line only (glued dumps: seek ``byte_start``, then find that
line). Needles are existing folder-alias spellings only — not catalogue
labels. Comments on any other line are never scanned.

Match rule (same as folder names / machines): token-boundary — exact full
normalize / exact token or consecutive tokens, then fuzzy only within one
token (substring ≥4 / prefix ≥3 residual ≤2). Role/odbiorca ``exact``
flags are ignored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from gcode_index.aliases import AliasMap, match_tier_in_raw
from gcode_index.folder_colour_aliases import (
    FolderColourAliasMap,
    canonical_role_id,
)
from gcode_index.models import COLOUR_EXCLUDE
from gcode_index.odbiorca_aliases import (
    DEFAULT_HEADER_SCAN_DEPTH,
    HEADER_ODBIORCA_SCAN_LINES,
    MAX_HEADER_SCAN_DEPTH,
    MIN_HEADER_ODBIORCA_NEEDLE,
    MIN_HEADER_SCAN_DEPTH,
    clamp_header_scan_depth,
    extract_header_paren_comments,
    extract_header_paren_comments_for_teach,
)

# Shared constants (same guards as odbiorca O-line header)
MIN_HEADER_NEEDLE = MIN_HEADER_ODBIORCA_NEEDLE
# Search limit when locating the O-number line (not a multi-line comment window).
HEADER_SCAN_LINES = HEADER_ODBIORCA_SCAN_LINES

# Re-export extract for callers that want one import site
__all__ = [
    "DEFAULT_HEADER_SCAN_DEPTH",
    "HEADER_SCAN_LINES",
    "MAX_HEADER_SCAN_DEPTH",
    "MIN_HEADER_NEEDLE",
    "MIN_HEADER_SCAN_DEPTH",
    "clamp_header_scan_depth",
    "extract_header_paren_comments",
    "extract_header_paren_comments_for_teach",
    "match_roles_in_comments",
    "match_roles_from_header",
    "match_machine_in_comments",
    "match_machine_from_header",
]


def match_roles_in_comments(
    comments: Sequence[str],
    colour_map: FolderColourAliasMap,
    *,
    min_needle: int = MIN_HEADER_NEEDLE,
) -> dict[str, str]:
    """Role id → alias spelling for every colour-alias needle hit in comments.

    Accumulates **all** matching role ids (union). Skips ``exclude`` and status
    colours. Token-boundary exact-then-fuzzy on each ``(…)`` body; longer /
    higher-tier needles preferred when attributing a spelling, but every role
    that hits is kept. Rule ``exact`` flags are ignored.
    """
    if not comments or colour_map is None or len(colour_map) == 0:
        return {}
    needles: list[tuple[str, int, str, str]] = []  # key, len, role_id, alias
    seen_keys: set[str] = set()
    for rule in colour_map.rules:
        key = rule.key
        if not key or len(key) < min_needle:
            continue
        if key in seen_keys:
            continue
        colour = (rule.colour or "").strip()
        if not colour or colour == COLOUR_EXCLUDE:
            continue
        rid = canonical_role_id(colour) or colour
        if not rid or rid == COLOUR_EXCLUDE:
            continue
        seen_keys.add(key)
        needles.append((key, len(key), rid, rule.alias))
    if not needles:
        return {}
    needles.sort(key=lambda t: (-t[1], t[0]))

    # role_id → (tier, length, alias) — best spelling wins per role
    best: dict[str, tuple[int, int, str]] = {}
    for raw in comments:
        if not (raw or "").strip():
            continue
        for key, length, rid, alias in needles:
            tier = match_tier_in_raw(key, raw)
            if tier is None:
                continue
            cand = (tier, length, alias)
            prior = best.get(rid)
            if prior is None or cand > prior:
                best[rid] = cand
    return {rid: trip[2] for rid, trip in best.items()}


def match_roles_from_header(
    path: Path | str,
    colour_map: FolderColourAliasMap,
    *,
    byte_start: Optional[int] = None,
    min_needle: int = MIN_HEADER_NEEDLE,
    max_lines: int = HEADER_SCAN_LINES,
) -> dict[str, str]:
    """Role id → alias spelling from O-number-line paren comments."""
    comments = extract_header_paren_comments(
        path, byte_start=byte_start, max_lines=max_lines
    )
    return match_roles_in_comments(comments, colour_map, min_needle=min_needle)


def match_machine_in_comments(
    comments: Sequence[str],
    alias_map: AliasMap,
    *,
    min_needle: int = MIN_HEADER_NEEDLE,
) -> Optional[tuple[str, str, Optional[str], Optional[str]]]:
    """Best single machine from alias needles in comment texts.

    Returns ``(machine_id, matched_alias_key, label, control_family)`` or None.
    Same token-boundary exact-then-fuzzy as folder resolve; longest /
    higher-tier needle wins. Skips entries whose ``machine_id`` is empty /
    ``unknown`` / ``unmapped:…``.
    """
    if not comments or alias_map is None:
        return None
    machines = getattr(alias_map, "_machines", None) or {}
    if not machines:
        return None
    needles: list[tuple[str, int, str, Optional[str], Optional[str]]] = []
    # key, len, machine_id, label, control_family
    for key, entry in machines.items():
        if not key or len(key) < min_needle:
            continue
        mid = str((entry or {}).get("machine_id") or "").strip()
        if not mid or mid.casefold() == "unknown" or mid.startswith("unmapped:"):
            continue
        label = str((entry or {}).get("label") or "").strip() or None
        cf = str((entry or {}).get("control_family") or "").strip() or None
        needles.append((key, len(key), mid, label, cf))
    if not needles:
        return None
    needles.sort(key=lambda t: (-t[1], t[0]))

    best: Optional[tuple[int, int, str, str, Optional[str], Optional[str]]] = None
    # (tier, length, machine_id, key, label, control_family)
    for raw in comments:
        if not (raw or "").strip():
            continue
        for key, length, mid, label, cf in needles:
            tier = match_tier_in_raw(key, raw)
            if tier is None:
                continue
            cand = (tier, length, mid, key, label, cf)
            if best is None or cand[:2] > best[:2]:
                best = cand
            elif cand[:2] == best[:2] and cand[3] < best[3]:
                # Stable tie-break on key
                best = cand
    if best is None:
        return None
    return best[2], best[3], best[4], best[5]


def match_machine_from_header(
    path: Path | str,
    alias_map: AliasMap,
    *,
    byte_start: Optional[int] = None,
    min_needle: int = MIN_HEADER_NEEDLE,
    max_lines: int = HEADER_SCAN_LINES,
) -> Optional[tuple[str, str, Optional[str], Optional[str]]]:
    """Resolve one machine from O-number-line paren comments, or None."""
    comments = extract_header_paren_comments(
        path, byte_start=byte_start, max_lines=max_lines
    )
    return match_machine_in_comments(comments, alias_map, min_needle=min_needle)
