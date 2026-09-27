"""Flag disc image rendering (Pillow) — no Tk required for PIL path."""

from __future__ import annotations

from gcode_index.flag_image import flag_image_size, render_flag_pil
from gcode_index.badge_style import STATUS_SWATCH
from gcode_index.models import PROVENANCE_BACKUP


def test_flag_image_size_grows_with_discs():
    w1, h1 = flag_image_size(1)
    w3, h3 = flag_image_size(3)
    assert w3 > w1
    assert h1 == h3


def test_render_flag_pil_multi_colour():
    img = render_flag_pil(
        [STATUS_SWATCH[PROVENANCE_BACKUP], "#E67E22", "#C0392B"]
    )
    assert img.mode == "RGBA"
    w, h = flag_image_size(3)
    assert img.size == (w, h)
    # Sample left disc centre ≈ green status
    px = img.getpixel((6, h // 2))
    assert px[1] > px[0]  # greener than red
    # Middle disc ≈ orange
    mid_x = w // 2
    mid = img.getpixel((mid_x, h // 2))
    assert mid[0] > 100 and mid[1] > 80
