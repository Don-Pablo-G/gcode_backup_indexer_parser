"""Multi-colour Flag disc images (Pillow) for Treeview ``#0`` cells.

``ttk.Treeview`` paints one foreground colour per row tag, so several ``⬤``
glyphs in a data column always look the same colour. True green+orange (etc.)
needs a composed image. Photos are attached to the tree column (``#0``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:
    import tkinter as tk
    from PIL.ImageTk import PhotoImage as PhotoImageType

# Disc geometry (CSS-ish pixels at 100% DPI).
DISC_DIAMETER = 12
DISC_GAP = 3
DISC_PAD_X = 2
DISC_PAD_Y = 2


def _parse_hex(colour: str) -> tuple[int, int, int, int]:
    raw = (colour or "").strip() or "#888888"
    if not raw.startswith("#"):
        raw = f"#{raw}"
    h = raw[1:]
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return (136, 136, 136, 255)
    try:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
    except ValueError:
        return (136, 136, 136, 255)
    return (r, g, b, 255)


def flag_image_size(n_discs: int) -> tuple[int, int]:
    """Pixel width × height for ``n_discs`` (at least one disc wide)."""
    n = max(1, int(n_discs))
    w = DISC_PAD_X * 2 + n * DISC_DIAMETER + (n - 1) * DISC_GAP
    h = DISC_PAD_Y * 2 + DISC_DIAMETER
    return w, h


def render_flag_pil(hex_colours: Sequence[str]):
    """Build an RGBA Pillow image with one filled disc per colour (left→right)."""
    from PIL import Image, ImageDraw

    colours = [c for c in hex_colours if c]
    if not colours:
        colours = ["#888888"]
    w, h = flag_image_size(len(colours))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for i, hx in enumerate(colours):
        x0 = DISC_PAD_X + i * (DISC_DIAMETER + DISC_GAP)
        y0 = DISC_PAD_Y
        x1 = x0 + DISC_DIAMETER - 1
        y1 = y0 + DISC_DIAMETER - 1
        draw.ellipse((x0, y0, x1, y1), fill=_parse_hex(hx))
    return img


def flag_photo(
    hex_colours: Sequence[str],
    master: Optional["tk.Misc"] = None,
) -> "PhotoImageType":
    """Return a Tk ``PhotoImage`` for the Flag cell (caller must retain a ref)."""
    from PIL import ImageTk

    img = render_flag_pil(hex_colours)
    if master is not None:
        return ImageTk.PhotoImage(img, master=master)
    return ImageTk.PhotoImage(img)


class FlagPhotoCache:
    """Cache Flag photos by disc-hex tuple; drop all on clear (redraw)."""

    def __init__(self, master: Optional["tk.Misc"] = None) -> None:
        self._master = master
        self._by_key: dict[tuple[str, ...], object] = {}
        # Strong refs so Tk does not GC images still shown in the tree.
        self._alive: list[object] = []

    def clear(self) -> None:
        self._by_key.clear()
        self._alive.clear()

    def photo_for(self, hex_colours: Sequence[str]) -> object:
        key = tuple((c or "#888888").strip().casefold() for c in hex_colours) or (
            "#888888",
        )
        hit = self._by_key.get(key)
        if hit is not None:
            return hit
        photo = flag_photo(key, master=self._master)
        self._by_key[key] = photo
        self._alive.append(photo)
        return photo
