"""Preview truncation and compare/diff helpers for program instances (#5 / #12)."""

from __future__ import annotations

import difflib
from typing import Optional, Sequence

from gcode_index.db import format_display_date
from gcode_index.extract import ExtractError, RowLike, extract_text
from gcode_index.path_remap import RemapInput

# Soft caps so huge glued dumps / .nc files do not freeze the GUI
DEFAULT_PREVIEW_MAX_CHARS = 120_000
DEFAULT_PREVIEW_MAX_LINES = 2_500


def instance_label(row: RowLike) -> str:
    """Short label for a result row (program · machine · date)."""
    prog = str(row["program_number"] or "?")
    keys = row.keys() if hasattr(row, "keys") else ()
    machine = ""
    if "machine_label" in keys and row["machine_label"]:
        machine = str(row["machine_label"])
    elif "machine_id" in keys:
        machine = str(row["machine_id"] or "")
    date = ""
    if "backup_date" in keys:
        date = format_display_date(row["backup_date"])  # type: ignore[arg-type]
    bits = [prog]
    if machine:
        bits.append(machine)
    if date:
        bits.append(date)
    return " · ".join(bits)


def truncate_preview(
    text: str,
    *,
    max_chars: int = DEFAULT_PREVIEW_MAX_CHARS,
    max_lines: int = DEFAULT_PREVIEW_MAX_LINES,
) -> tuple[str, bool]:
    """Return ``(display_text, was_truncated)``."""
    if text is None:
        return "", False
    lines = text.splitlines(keepends=True)
    truncated = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    body = "".join(lines)
    if len(body) > max_chars:
        body = body[:max_chars]
        truncated = True
        # Avoid cutting mid-line awkwardly when possible
        nl = body.rfind("\n")
        if nl > max_chars // 2:
            body = body[: nl + 1]
    return body, truncated


def preview_text(
    row: RowLike,
    *,
    backup_root: str | None = None,
    max_chars: int = DEFAULT_PREVIEW_MAX_CHARS,
    max_lines: int = DEFAULT_PREVIEW_MAX_LINES,
    skip_integrity: bool = False,
    path_remaps: Optional[Sequence[RemapInput]] = None,
) -> tuple[str, Optional[str]]:
    """Extract body for preview.

    Returns ``(body_or_empty, error_message)``. On success error is ``None``.
    Truncation note is appended to the body when caps apply.
    """
    try:
        raw = extract_text(
            row,
            backup_root=backup_root,
            skip_integrity=skip_integrity,
            path_remaps=path_remaps,
        )
    except ExtractError as exc:
        return "", str(exc)
    except OSError as exc:
        return "", str(exc)
    body, truncated = truncate_preview(raw, max_chars=max_chars, max_lines=max_lines)
    if truncated:
        body = (
            body
            + f"\n\n… [preview truncated — full extract writes the complete program "
            f"({len(raw)} characters)]\n"
        )
    return body, None


def unified_diff_programs(
    row_a: RowLike,
    row_b: RowLike,
    *,
    backup_root: str | None = None,
    context: int = 3,
    skip_integrity: bool = False,
    path_remaps: Optional[Sequence[RemapInput]] = None,
) -> tuple[str, Optional[str]]:
    """Unified diff of two extracted program bodies.

    Returns ``(diff_text, error_message)``. Empty diff with no error means identical.
    """
    try:
        text_a = extract_text(
            row_a,
            backup_root=backup_root,
            skip_integrity=skip_integrity,
            path_remaps=path_remaps,
        )
        text_b = extract_text(
            row_b,
            backup_root=backup_root,
            skip_integrity=skip_integrity,
            path_remaps=path_remaps,
        )
    except ExtractError as exc:
        return "", str(exc)
    except OSError as exc:
        return "", str(exc)

    label_a = instance_label(row_a)
    label_b = instance_label(row_b)
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)
    if not lines_a and text_a:
        lines_a = [text_a]
    if not lines_b and text_b:
        lines_b = [text_b]
    # Ensure trailing newline for difflib friendliness
    if lines_a and not lines_a[-1].endswith(("\n", "\r")):
        lines_a[-1] = lines_a[-1] + "\n"
    if lines_b and not lines_b[-1].endswith(("\n", "\r")):
        lines_b[-1] = lines_b[-1] + "\n"

    diff = difflib.unified_diff(
        lines_a,
        lines_b,
        fromfile=label_a,
        tofile=label_b,
        n=context,
        lineterm="\n",
    )
    out = "".join(diff)
    if not out:
        return (
            f"No differences — bodies are identical.\n"
            f"A: {label_a}\n"
            f"B: {label_b}\n",
            None,
        )
    return out, None
