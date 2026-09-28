"""Unassigned header token frequencies (scan-report teach list).

Collects tokens from paren ``(…)`` comments starting at the O-number line,
optionally spanning ``header_scan_depth`` lines (stop at leading ``%``).
Auto-match (role / machine / odbiorca) stays O-line only elsewhere.
Applies teaching exclusions, caches beside the DB, and filters to tokens with
no machine / role / odbiorca alias yet.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence

from gcode_index.aliases import (
    MIN_PREFIX_ALIAS_LEN,
    AliasMap,
    folder_name_tokens,
)
from gcode_index.db import program_digit_core
from gcode_index.folder_colour_aliases import FolderColourAliasMap, FolderNameFreq
from gcode_index.models import ProgramInstance
from gcode_index.odbiorca_aliases import (
    DEFAULT_HEADER_SCAN_DEPTH,
    OdbiorcaAliasMap,
    clamp_header_scan_depth,
    extract_header_paren_comments_for_teach,
)

HEADER_TOKEN_FREQ_FILENAME = "header_token_freq.json"
HEADER_TOKEN_FREQ_VERSION = 1

# Align with alias needle floor (MIN_PREFIX_ALIAS_LEN).
MIN_HEADER_TOKEN_LEN = MIN_PREFIX_ALIAS_LEN
# Part-number filter for teaching only: more than this many digit chars → drop.
MAX_DIGIT_CHARS_FOR_TEACH = 4

_TOKEN_SPELLING_SPLIT = re.compile(r"[^A-Za-z0-9]+")


def header_token_freq_path_for_target(target: Path | str) -> Path:
    return Path(target) / HEADER_TOKEN_FREQ_FILENAME


def digit_char_count(text: str) -> int:
    """Count ``0-9`` characters in ``text``."""
    return sum(1 for ch in text if ch.isdigit())


def is_program_number_echo(token: str, program_number: Optional[str]) -> bool:
    """True when ``token`` is this instance's ``O#####`` / digit core."""
    key = (token or "").strip().lower()
    if not key:
        return True
    p_core = program_digit_core(program_number)
    t_core = program_digit_core(key)
    if t_core is not None and p_core is not None and t_core == p_core:
        return True
    # Bare ``o03232`` style token vs program ``03232`` / ``O03232``.
    if key.startswith("o") and key[1:].isdigit():
        o_core = program_digit_core(key)
        if o_core is not None and p_core is not None and o_core == p_core:
            return True
    return False


def is_excluded_header_token(
    token: str,
    *,
    program_number: Optional[str] = None,
) -> bool:
    """Teaching exclusions: short junk, program-number echo, digit-heavy part ids."""
    key = (token or "").strip().lower()
    if len(key) < MIN_HEADER_TOKEN_LEN:
        return True
    if digit_char_count(key) > MAX_DIGIT_CHARS_FOR_TEACH:
        return True
    if is_program_number_echo(key, program_number):
        return True
    return False


def tokens_with_spellings(comment: str) -> list[tuple[str, str]]:
    """``(normalized_key, representative_spelling)`` from one O-line paren body.

    Keys match ``folder_name_tokens``; spellings keep original casing from the
    comment when possible.
    """
    raw = (comment or "").strip()
    if not raw:
        return []
    keys = folder_name_tokens(raw)
    if not keys:
        return []
    # Map lowercased pieces back to original-cased segments (same split).
    parts = [p for p in _TOKEN_SPELLING_SPLIT.split(raw) if p]
    by_lower: dict[str, str] = {}
    for part in parts:
        low = part.lower()
        if low and low not in by_lower:
            by_lower[low] = part
    out: list[tuple[str, str]] = []
    for key in keys:
        out.append((key, by_lower.get(key, key)))
    return out


def instance_source_file(inst: ProgramInstance) -> Optional[Path]:
    root = (inst.scan_root or "").strip()
    rel = (inst.source_path or "").strip()
    if not root or not rel:
        return None
    try:
        return Path(root) / rel
    except Exception:
        return None


def collect_header_token_frequencies(
    instances: Sequence[ProgramInstance],
    *,
    depth: int = DEFAULT_HEADER_SCAN_DEPTH,
) -> list[FolderNameFreq]:
    """Aggregate header tokens across indexed instances (exclusions applied).

    ``depth`` is lines counting the O-line (default 1 = O-line only); stops
    before the next leading ``%``. Counts **once per instance** per distinct
    token key. Sort: high count first.
    """
    depth_n = clamp_header_scan_depth(depth)
    # key → spelling → count (instance hits)
    groups: dict[str, dict[str, int]] = {}
    for inst in instances:
        path = instance_source_file(inst)
        if path is None or not path.is_file():
            continue
        comments = extract_header_paren_comments_for_teach(
            path, byte_start=inst.byte_start, depth=depth_n
        )
        if not comments:
            continue
        seen_keys: set[str] = set()
        for body in comments:
            for key, spelling in tokens_with_spellings(body):
                if key in seen_keys:
                    continue
                if is_excluded_header_token(
                    key, program_number=inst.program_number
                ):
                    continue
                seen_keys.add(key)
                spellings = groups.setdefault(key, {})
                spellings[spelling] = spellings.get(spelling, 0) + 1
    out: list[FolderNameFreq] = []
    for key, spellings in groups.items():
        name = sorted(
            spellings.items(),
            key=lambda kv: (-kv[1], kv[0].casefold(), kv[0]),
        )[0][0]
        out.append(
            FolderNameFreq(key=key, name=name, count=sum(spellings.values()))
        )
    out.sort(key=lambda e: (-e.count, e.name.casefold(), e.name))
    return out


def token_has_alias(
    name: str,
    *,
    aliases: Optional[AliasMap] = None,
    colour_map: Optional[FolderColourAliasMap] = None,
    odbiorca_map: Optional[OdbiorcaAliasMap] = None,
) -> bool:
    """True when any machine / role / odbiorca matcher binds ``name``."""
    raw = (name or "").strip()
    if not raw:
        return False
    if aliases is not None:
        info = aliases.resolve(raw)
        if info.mapped:
            return True
    if colour_map is not None and len(colour_map) > 0:
        if colour_map.rule_for_name(raw) is not None:
            return True
    if odbiorca_map is not None and len(odbiorca_map) > 0:
        if odbiorca_map.rule_for_name(raw) is not None:
            return True
    return False


def filter_unassigned_header_tokens(
    entries: Sequence[FolderNameFreq],
    *,
    aliases: Optional[AliasMap] = None,
    colour_map: Optional[FolderColourAliasMap] = None,
    odbiorca_map: Optional[OdbiorcaAliasMap] = None,
) -> list[FolderNameFreq]:
    """Keep tokens with no machine / role / odbiorca alias yet."""
    out: list[FolderNameFreq] = []
    for e in entries:
        if token_has_alias(
            e.name,
            aliases=aliases,
            colour_map=colour_map,
            odbiorca_map=odbiorca_map,
        ):
            continue
        # Also try key in case spelling differs
        if e.key != e.name.casefold() and token_has_alias(
            e.key,
            aliases=aliases,
            colour_map=colour_map,
            odbiorca_map=odbiorca_map,
        ):
            continue
        out.append(e)
    return out


@dataclass
class HeaderTokenFreqCache:
    """Sidecar snapshot written at end of scan."""

    tokens: list[FolderNameFreq]
    run_id: Optional[str] = None
    built_at: Optional[str] = None
    full_scan: bool = True
    version: int = HEADER_TOKEN_FREQ_VERSION


def save_header_token_freq(
    path: Path | str,
    entries: Sequence[FolderNameFreq],
    *,
    run_id: Optional[str] = None,
    full_scan: bool = True,
) -> Path:
    """Write frequency cache beside the DB (JSON)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": HEADER_TOKEN_FREQ_VERSION,
        "run_id": run_id,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "full_scan": bool(full_scan),
        "tokens": [
            {"key": e.key, "name": e.name, "count": int(e.count)} for e in entries
        ],
    }
    p.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def load_header_token_freq(path: Path | str) -> Optional[HeaderTokenFreqCache]:
    """Load cache; ``None`` if missing or unreadable."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    raw_tokens = data.get("tokens") or []
    tokens: list[FolderNameFreq] = []
    if isinstance(raw_tokens, list):
        for item in raw_tokens:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            name = str(item.get("name") or key).strip()
            try:
                count = int(item.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            if not key or count < 1:
                continue
            tokens.append(FolderNameFreq(key=key, name=name or key, count=count))
    tokens.sort(key=lambda e: (-e.count, e.name.casefold(), e.name))
    return HeaderTokenFreqCache(
        tokens=tokens,
        run_id=str(data["run_id"]) if data.get("run_id") else None,
        built_at=str(data["built_at"]) if data.get("built_at") else None,
        full_scan=bool(data.get("full_scan", True)),
        version=int(data.get("version") or HEADER_TOKEN_FREQ_VERSION),
    )


def build_and_save_header_token_freq(
    target: Path | str,
    instances: Sequence[ProgramInstance],
    *,
    run_id: Optional[str] = None,
    full_scan: bool = True,
    depth: int = DEFAULT_HEADER_SCAN_DEPTH,
) -> list[FolderNameFreq]:
    """Collect from instances and write ``header_token_freq.json`` beside the DB."""
    entries = collect_header_token_frequencies(instances, depth=depth)
    save_header_token_freq(
        header_token_freq_path_for_target(target),
        entries,
        run_id=run_id,
        full_scan=full_scan,
    )
    return entries


def load_or_rebuild_header_token_freq(
    target: Path | str,
    instances: Iterable[ProgramInstance],
    *,
    run_id: Optional[str] = None,
    force: bool = False,
    depth: int = DEFAULT_HEADER_SCAN_DEPTH,
) -> list[FolderNameFreq]:
    """Prefer cache; rebuild from ``instances`` when missing or ``force``."""
    path = header_token_freq_path_for_target(target)
    if not force:
        cached = load_header_token_freq(path)
        if cached is not None:
            return list(cached.tokens)
    return build_and_save_header_token_freq(
        target,
        list(instances),
        run_id=run_id,
        full_scan=True,
        depth=depth,
    )
