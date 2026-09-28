"""Reconstruct per-role reasons for Work Flag-column hover tips.

Scan persists only the final role-id set on each instance. Hover tips rebuild
truthful reasons from the live path + YAML (name aliases / Mapuj drzewo /
O-number-line paren comments / O9000–O9099), mirroring scanner order: name
union → tree-path replace → header accumulate → O9 accumulate. No DB schema
change.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from gcode_index.badge_style import DOT, pick_override_role
from gcode_index.folder_colour_aliases import (
    ColourCatalog,
    FolderColourAliasMap,
    FolderColourRule,
    canonical_role_id,
)
from gcode_index.folder_tree_map import FolderTreeMap, roles_from_db
from gcode_index.header_match import match_roles_from_header
from gcode_index.i18n import t
from gcode_index.models import (
    COLOUR_EXCLUDE,
    PROVENANCE_BACKUP,
    PROVENANCE_EXTRA,
    ROLE_SYSTEM_PROGRAMS,
    is_o9_system_program,
)

# Reason kinds returned by ``explain_row_roles``
REASON_ALIAS = "alias"
REASON_ALIAS_FUZZY = "alias_fuzzy"
REASON_PATH = "path"
REASON_HEADER = "header"
REASON_O9 = "o9"
REASON_ALIAS_O9 = "alias_o9"
REASON_ALIAS_FUZZY_O9 = "alias_fuzzy_o9"
REASON_UNAVAILABLE = "unavailable"

_PATH_TAIL_SEGMENTS = 3


@dataclass(frozen=True)
class RoleReason:
    """One role on a results row plus how it was attributed."""

    role_id: str
    reason_kind: str
    detail: str = ""
    o9_number: str = ""


def _folder_parts_from_source(source_path: str) -> list[str]:
    """Folder segments under the scan root (drop filename), same as colour map."""
    raw = (source_path or "").replace("\\", "/").strip("/")
    if not raw:
        return []
    parts = [p for p in raw.split("/") if p]
    if not parts:
        return []
    last = parts[-1]
    if "." in last:
        parts = parts[:-1]
    return parts


def path_tail(path: str, *, segments: int = _PATH_TAIL_SEGMENTS) -> str:
    """Readable tail of a path (last N segments, ``…/`` when truncated)."""
    parts = [p for p in (path or "").replace("\\", "/").strip("/").split("/") if p]
    if not parts:
        return ""
    n = max(1, int(segments))
    if len(parts) <= n:
        return "/".join(parts)
    return "…/" + "/".join(parts[-n:])


def format_o9_display(program_number: Optional[str]) -> str:
    """Normalize a program number to ``O####`` for tip text."""
    raw = (program_number or "").strip()
    if not raw:
        return "O9xxx"
    body = raw[1:].lstrip() if raw[0] in "Oo" else raw
    digits: list[str] = []
    for ch in body:
        if ch.isdigit():
            digits.append(ch)
        else:
            break
    if not digits:
        return raw if raw[0] in "Oo" else f"O{raw}"
    try:
        n = int("".join(digits))
    except ValueError:
        return f"O{''.join(digits)}"
    return f"O{n}"


def _name_attributions(
    source_path: str,
    colour_map: FolderColourAliasMap,
) -> dict[str, tuple[FolderColourRule, bool]]:
    """First path-segment match per role id → (rule, fuzzy)."""
    found: dict[str, tuple[FolderColourRule, bool]] = {}
    if len(colour_map) == 0:
        return found
    for part in _folder_parts_from_source(source_path):
        rule = colour_map.match_segment_rule(part)
        if rule is None:
            continue
        if rule.colour == COLOUR_EXCLUDE:
            continue
        rid = canonical_role_id(rule.colour) or rule.colour
        if not rid or rid in found:
            continue
        from gcode_index.aliases import normalize_folder_name

        part_key = normalize_folder_name(part)
        # Exact full-normalize equality → alias; token / within-token → fuzzy.
        fuzzy = bool(part_key) and part_key != rule.key
        found[rid] = (rule, fuzzy)
    return found


def explain_row_roles(
    *,
    source_path: str,
    scan_root: Optional[str],
    program_number: Optional[str],
    role_csv: Optional[str],
    colour_map: Optional[FolderColourAliasMap] = None,
    tree_map: Optional[FolderTreeMap] = None,
    o9_enabled: bool = True,
    role_from_header: bool = True,
    byte_start: Optional[int] = None,
) -> list[RoleReason]:
    """Reconstruct per-role reasons for roles still present on the row.

    Mirrors scan: tree-map tags with a non-empty list **replace** name union;
    header role aliases accumulate; O9 may still accumulate ``system_programs``.
    Roles on the row that no live rule explains → ``unavailable`` (stale index
    vs YAML, or missing source file for a header-only role).
    """
    roles = roles_from_db(role_csv)
    if not roles:
        return []

    cmap = colour_map if colour_map is not None else FolderColourAliasMap.empty()
    tmap = tree_map if tree_map is not None else FolderTreeMap()

    tree_rule = tmap.resolve_for_source(
        scan_root=scan_root,
        source_path=source_path or "",
    )
    path_replaced = tree_rule is not None and bool(tree_rule.tags)
    tree_tag_set = set(tree_rule.tags) if path_replaced else set()

    name_attr = (
        {}
        if path_replaced
        else _name_attributions(source_path or "", cmap)
    )

    header_attr: dict[str, str] = {}
    if role_from_header and cmap is not None and len(cmap) > 0:
        root = (scan_root or "").strip()
        rel = (source_path or "").strip()
        if root and rel:
            try:
                fpath = Path(root) / rel
            except Exception:
                fpath = None
            if fpath is not None and fpath.is_file():
                header_attr = match_roles_from_header(
                    fpath,
                    cmap,
                    byte_start=byte_start,
                )

    o9_hit = bool(
        o9_enabled
        and ROLE_SYSTEM_PROGRAMS in roles
        and is_o9_system_program(program_number)
    )
    o9_disp = format_o9_display(program_number) if o9_hit else ""

    out: list[RoleReason] = []
    for rid in roles:
        if path_replaced and rid in tree_tag_set:
            detail = tree_rule.path if tree_rule is not None else ""
            if rid == ROLE_SYSTEM_PROGRAMS and o9_hit:
                # Path put it there; O9 would also accumulate — mention both.
                out.append(
                    RoleReason(
                        role_id=rid,
                        reason_kind=REASON_PATH,
                        detail=detail,
                        o9_number=o9_disp,
                    )
                )
            else:
                out.append(
                    RoleReason(role_id=rid, reason_kind=REASON_PATH, detail=detail)
                )
            continue

        if rid == ROLE_SYSTEM_PROGRAMS and o9_hit:
            if rid in name_attr:
                rule, fuzzy = name_attr[rid]
                kind = REASON_ALIAS_FUZZY_O9 if fuzzy else REASON_ALIAS_O9
                out.append(
                    RoleReason(
                        role_id=rid,
                        reason_kind=kind,
                        detail=rule.alias,
                        o9_number=o9_disp,
                    )
                )
            else:
                out.append(
                    RoleReason(
                        role_id=rid,
                        reason_kind=REASON_O9,
                        detail=o9_disp,
                        o9_number=o9_disp,
                    )
                )
            continue

        if rid in name_attr:
            rule, fuzzy = name_attr[rid]
            kind = REASON_ALIAS_FUZZY if fuzzy else REASON_ALIAS
            out.append(
                RoleReason(role_id=rid, reason_kind=kind, detail=rule.alias)
            )
            continue

        if rid in header_attr:
            out.append(
                RoleReason(
                    role_id=rid,
                    reason_kind=REASON_HEADER,
                    detail=header_attr[rid],
                )
            )
            continue

        out.append(
            RoleReason(role_id=rid, reason_kind=REASON_UNAVAILABLE, detail="")
        )
    return out


def format_reason_phrase(reason: RoleReason, lang: str = "pl") -> str:
    """i18n phrase for the reason half of a tip bullet (no role label)."""
    kind = reason.reason_kind
    if kind == REASON_ALIAS:
        return t(lang, "flag_tip_alias", spelling=reason.detail)
    if kind == REASON_ALIAS_FUZZY:
        return t(lang, "flag_tip_alias_partial", spelling=reason.detail)
    if kind == REASON_PATH:
        tail = path_tail(reason.detail)
        phrase = t(lang, "flag_tip_path", tail=tail)
        if reason.o9_number:
            o9 = t(lang, "flag_tip_o9", number=reason.o9_number)
            return f"{phrase} + {o9}"
        return phrase
    if kind == REASON_HEADER:
        return t(lang, "flag_tip_header", spelling=reason.detail)
    if kind == REASON_O9:
        return t(lang, "flag_tip_o9", number=reason.o9_number or reason.detail)
    if kind == REASON_ALIAS_O9:
        return t(
            lang,
            "flag_tip_alias_o9",
            spelling=reason.detail,
            number=reason.o9_number or reason.detail,
        )
    if kind == REASON_ALIAS_FUZZY_O9:
        return t(
            lang,
            "flag_tip_alias_partial_o9",
            spelling=reason.detail,
            number=reason.o9_number or reason.detail,
        )
    return t(lang, "flag_tip_unavailable")


def format_flag_header(
    *,
    provenance: Optional[str],
    role_ids: Sequence[str] | None,
    override_role_ids: Sequence[str] | None,
    catalog: ColourCatalog,
    lang: str = "pl",
) -> str:
    """First tip line: status disc meaning, or overriding role."""
    chosen = pick_override_role(role_ids, override_role_ids)
    if chosen:
        label = catalog.label_for(chosen, lang)
        return t(lang, "flag_tip_override", role=label, disc=DOT)
    status = (provenance or PROVENANCE_BACKUP).strip() or PROVENANCE_BACKUP
    if status == PROVENANCE_EXTRA:
        label = t(lang, "status_unknown")
    else:
        label = t(lang, "status_on_machine")
    return t(lang, "flag_tip_status", label=label, disc=DOT)


def format_flag_tooltip(
    *,
    provenance: Optional[str],
    source_path: str,
    scan_root: Optional[str],
    program_number: Optional[str],
    role_csv: Optional[str],
    catalog: ColourCatalog,
    colour_map: Optional[FolderColourAliasMap] = None,
    tree_map: Optional[FolderTreeMap] = None,
    o9_enabled: bool = True,
    role_from_header: bool = True,
    byte_start: Optional[int] = None,
    lang: str = "pl",
) -> str:
    """Full Flag-cell tip text (header + Funkcje list)."""
    roles = roles_from_db(role_csv)
    override_ids = catalog.override_role_ids()
    header = format_flag_header(
        provenance=provenance,
        role_ids=roles,
        override_role_ids=override_ids,
        catalog=catalog,
        lang=lang,
    )
    lines = [header, t(lang, "flag_tip_functions")]
    if not roles:
        lines.append(f"  {t(lang, 'flag_tip_empty')}")
        return "\n".join(lines)

    cmap = colour_map if colour_map is not None else catalog.alias_map()
    reasons = explain_row_roles(
        source_path=source_path,
        scan_root=scan_root,
        program_number=program_number,
        role_csv=role_csv,
        colour_map=cmap,
        tree_map=tree_map,
        o9_enabled=o9_enabled,
        role_from_header=role_from_header,
        byte_start=byte_start,
    )
    for reason in reasons:
        label = catalog.label_for(reason.role_id, lang)
        phrase = format_reason_phrase(reason, lang)
        lines.append(
            t(lang, "flag_tip_bullet", label=label, reason=phrase)
        )
    return "\n".join(lines)
