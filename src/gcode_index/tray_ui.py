"""System-tray helper for the tkinter GUI (Windows-first via pystray).

Tray support is optional: if ``pystray`` / Pillow are missing, callers get
``tray_available() == False`` and should fall back to normal window close.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

log = logging.getLogger("gcode_index.tray")

RestoreCallback = Callable[[], None]
QuitCallback = Callable[[], None]


def tray_available() -> bool:
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def _make_icon_image():
    """Packaged product mark for the tray (16/32 PNG), with procedural fallback."""
    from PIL import Image

    from gcode_index.app_icon import resolve_app_ico, resolve_best_png

    png = resolve_best_png(32, 16, 64)
    if png is not None:
        try:
            return Image.open(png).convert("RGBA")
        except OSError:
            pass

    ico = resolve_app_ico()
    if ico is not None:
        try:
            im = Image.open(ico)
            # Prefer an embedded 32×32 (or nearest) for tray sharpness.
            try:
                sizes = sorted(im.ico.sizes())  # type: ignore[attr-defined]
                prefer = (32, 32)
                target = prefer if prefer in sizes else min(
                    sizes, key=lambda s: abs(s[0] - 32)
                )
                im = im.ico.getimage(target)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
            return im.convert("RGBA")
        except OSError:
            pass

    # Last resort: simple green disc (no packaged asset available).
    from PIL import ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, size - 5, size - 5), fill=(46, 125, 50, 255))
    draw.rectangle((20, 28, 44, 36), fill=(255, 255, 255, 255))
    return img


class TrayController:
    """Background pystray icon with Restore / Quit."""

    def __init__(
        self,
        *,
        title: str,
        on_restore: RestoreCallback,
        on_quit: QuitCallback,
        restore_label: str = "Restore",
        quit_label: str = "Quit",
    ) -> None:
        self._title = title
        self._on_restore = on_restore
        self._on_quit = on_quit
        self._restore_label = restore_label
        self._quit_label = quit_label
        self._icon = None
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if not tray_available():
            return False
        if self.running:
            return True
        import pystray
        from pystray import MenuItem as Item

        image = _make_icon_image()
        menu = pystray.Menu(
            Item(self._restore_label, self._handle_restore, default=True),
            Item(self._quit_label, self._handle_quit),
        )
        self._icon = pystray.Icon(
            "gcode_index_gui",
            image,
            self._title,
            menu,
        )
        self._thread = threading.Thread(
            target=self._run_icon, name="gcode-tray", daemon=True
        )
        self._thread.start()
        return True

    def _run_icon(self) -> None:
        try:
            assert self._icon is not None
            self._icon.run()
        except Exception:  # noqa: BLE001
            log.exception("tray icon failed")

    def stop(self) -> None:
        icon = self._icon
        self._icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:  # noqa: BLE001
                log.debug("tray stop failed", exc_info=True)
        thr = self._thread
        self._thread = None
        if thr is not None and thr.is_alive():
            thr.join(timeout=2.0)

    def _handle_restore(self, _icon=None, _item=None) -> None:
        try:
            self._on_restore()
        except Exception:  # noqa: BLE001
            log.exception("tray restore failed")

    def _handle_quit(self, _icon=None, _item=None) -> None:
        try:
            self._on_quit()
        except Exception:  # noqa: BLE001
            log.exception("tray quit failed")
