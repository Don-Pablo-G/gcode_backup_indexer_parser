"""Results-table column width layout: fill frame + adjacent-absorb resize."""

from __future__ import annotations

from typing import Iterable, Mapping, Optional, Sequence

# Default widths match the GUI headings (pixels).
DEFAULT_COLUMN_WIDTHS: dict[str, int] = {
    "flag": 88,
    "src": 64,
    "program": 90,
    "part": 130,
    "programmer": 56,
    "machine": 110,
    "odbiorca": 110,
    "date": 100,
    "size": 70,
    "type": 100,
    "control": 70,
    "path": 280,
    "location": 120,
}

MIN_COLUMN_WIDTH = 40
# Prefer giving leftover / taking slack from these (leftmost wins if present).
FILL_PRIORITY: tuple[str, ...] = ("path", "part", "machine", "odbiorca", "location")


def default_widths(columns: Iterable[str] | None = None) -> dict[str, int]:
    cols = list(columns) if columns is not None else list(DEFAULT_COLUMN_WIDTHS)
    out: dict[str, int] = {}
    for c in cols:
        out[c] = int(DEFAULT_COLUMN_WIDTHS.get(c, 100))
    return out


def clamp_width(width: int, *, min_width: int = MIN_COLUMN_WIDTH) -> int:
    try:
        w = int(width)
    except (TypeError, ValueError):
        w = min_width
    return max(min_width, w)


def merge_widths(
    stored: Optional[Mapping[str, int]],
    columns: Sequence[str],
) -> dict[str, int]:
    """Combine saved widths with defaults for known columns."""
    base = default_widths(columns)
    if not stored:
        return base
    for key, val in stored.items():
        if key in base:
            base[key] = clamp_width(val)
    return base


def parse_column_widths(raw: str) -> dict[str, int]:
    """Parse ``flag=88,src=64`` or indented ``flag=88`` lines."""
    out: dict[str, int] = {}
    text = (raw or "").replace(";", ",").replace("\n", ",")
    for part in text.split(","):
        bit = part.strip()
        if not bit or "=" not in bit:
            continue
        key, _, val = bit.partition("=")
        key = key.strip()
        val = val.strip()
        if not key:
            continue
        try:
            out[key] = clamp_width(int(val))
        except ValueError:
            continue
    return out


def format_column_widths(widths: Mapping[str, int], columns: Sequence[str]) -> str:
    bits: list[str] = []
    for col in columns:
        if col not in widths:
            continue
        bits.append(f"{col}={clamp_width(widths[col])}")
    return ",".join(bits)


def _fill_column(visible: Sequence[str]) -> Optional[str]:
    if not visible:
        return None
    for pref in FILL_PRIORITY:
        if pref in visible:
            return pref
    return visible[-1]


def redistribute_to_width(
    widths: Mapping[str, int],
    visible: Sequence[str],
    total_width: int,
    *,
    min_width: int = MIN_COLUMN_WIDTH,
) -> dict[str, int]:
    """Return widths for ``visible`` columns that sum to ``total_width``.

    Extra space goes to the fill column (path preferred). When too wide,
    shrink from the fill column first, then from the right.
    """
    vis = [c for c in visible if c]
    if not vis:
        return {}
    total = max(0, int(total_width))
    floor = min_width * len(vis)
    if total < floor:
        # Not enough room — everyone at min; caller may still scroll.
        return {c: min_width for c in vis}

    out = {c: clamp_width(widths.get(c, DEFAULT_COLUMN_WIDTHS.get(c, 100)), min_width=min_width) for c in vis}
    fill = _fill_column(vis) or vis[-1]
    current = sum(out.values())
    delta = total - current
    if delta == 0:
        return out
    if delta > 0:
        out[fill] = out[fill] + delta
        return out

    # Shrink: take from fill first, then right-to-left.
    need = -delta
    order = [fill] + [c for c in reversed(vis) if c != fill]
    for col in order:
        if need <= 0:
            break
        spare = out[col] - min_width
        if spare <= 0:
            continue
        take = min(spare, need)
        out[col] -= take
        need -= take
    return out


def resize_adjacent(
    widths: Mapping[str, int],
    left: str,
    right: str,
    delta: int,
    *,
    min_width: int = MIN_COLUMN_WIDTH,
) -> dict[str, int]:
    """Grow ``left`` by ``delta`` and shrink ``right`` by the same amount.

    Total of the two columns stays constant (Excel-style separator drag).
    """
    out = dict(widths)
    if left not in out or right not in out:
        return out
    if left == right or delta == 0:
        return out
    lw = clamp_width(out[left], min_width=min_width)
    rw = clamp_width(out[right], min_width=min_width)
    if delta > 0:
        # Grow left, shrink right
        take = min(delta, rw - min_width)
        out[left] = lw + take
        out[right] = rw - take
    else:
        # Shrink left, grow right
        give = min(-delta, lw - min_width)
        out[left] = lw - give
        out[right] = rw + give
    return out


def display_index_to_id(displaycolumns: Sequence[str], index_1based: int) -> Optional[str]:
    """Map Treeview ``#N`` (1-based) to a column id in ``displaycolumns``."""
    if index_1based < 1 or index_1based > len(displaycolumns):
        return None
    return displaycolumns[index_1based - 1]
