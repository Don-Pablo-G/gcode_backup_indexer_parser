"""Poll-based folder watcher for Full-mode auto incremental index.

Uses a lightweight stamp poll (size + mtime) under configured roots so it works
on local disks and typical NAS/SMB shares. Changes are debounced before the
callback fires so a multi-file copy settles before one incremental scan.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Optional

log = logging.getLogger("gcode_index.folder_watch")

ChangeCallback = Callable[[], None]


def is_indexable_path(path: Path) -> bool:
    """Match scanner indexable sources: ``.nc``, ``.nc.copy``, ``.pgm``, ALL-*.TXT."""
    if not path.is_file():
        return False
    name_u = path.name.upper()
    if name_u in ("ALL-FLDR.TXT", "ALL-PROG.TXT"):
        return True
    low = path.name.lower()
    if low.endswith(".nc.copy"):
        return True
    suf = path.suffix.lower()
    return suf in (".nc", ".pgm")


def stamp_tree(roots: Iterable[Path]) -> dict[str, tuple[int, int]]:
    """Map resolved path → (size, mtime_ns) for indexable files under roots."""
    out: dict[str, tuple[int, int]] = {}
    for root in roots:
        try:
            root_p = Path(root)
            if not root_p.is_dir():
                continue
            for path in root_p.rglob("*"):
                try:
                    if not is_indexable_path(path):
                        continue
                    st = path.stat()
                    out[str(path.resolve())] = (int(st.st_size), int(st.st_mtime_ns))
                except OSError:
                    continue
        except OSError:
            log.debug("watch stamp failed for %s", root, exc_info=True)
    return out


class FolderWatcher:
    """Background poller; calls ``on_change`` after debounce when stamps differ."""

    def __init__(
        self,
        *,
        on_change: ChangeCallback,
        poll_s: float = 5.0,
        debounce_s: float = 3.0,
    ) -> None:
        self._on_change = on_change
        self._poll_s = max(1.0, float(poll_s))
        self._debounce_s = max(0.5, float(debounce_s))
        self._roots: list[Path] = []
        self._snapshot: dict[str, tuple[int, int]] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._pending_since: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_roots(self, roots: Iterable[Path | str]) -> None:
        cleaned: list[Path] = []
        seen: set[str] = set()
        for raw in roots:
            try:
                p = Path(raw).resolve()
            except OSError:
                p = Path(raw)
            key = str(p).casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(p)
        with self._lock:
            self._roots = cleaned

    def seed(self) -> int:
        """Take a baseline snapshot without firing ``on_change``. Returns file count."""
        with self._lock:
            roots = list(self._roots)
        snap = stamp_tree(roots)
        with self._lock:
            self._snapshot = snap
            self._pending_since = None
        return len(snap)

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        if not self._snapshot:
            self.seed()
        self._thread = threading.Thread(
            target=self._run, name="gcode-folder-watch", daemon=True
        )
        self._thread.start()

    def stop(self, *, join_timeout: float = 2.0) -> None:
        self._stop.set()
        thr = self._thread
        self._thread = None
        if thr is not None and thr.is_alive():
            thr.join(timeout=join_timeout)
        with self._lock:
            self._pending_since = None

    def _run(self) -> None:
        while not self._stop.wait(self._poll_s):
            try:
                self._tick()
            except Exception:  # noqa: BLE001
                log.exception("folder watch tick failed")

    def _tick(self) -> None:
        with self._lock:
            roots = list(self._roots)
            prev = dict(self._snapshot)
        if not roots:
            return
        cur = stamp_tree(roots)
        changed = cur != prev
        now = time.monotonic()
        with self._lock:
            if changed:
                self._snapshot = cur
                if self._pending_since is None:
                    self._pending_since = now
            pending_since = self._pending_since
        if pending_since is None:
            return
        if (now - pending_since) < self._debounce_s:
            return
        with self._lock:
            self._pending_since = None
        try:
            self._on_change()
        except Exception:  # noqa: BLE001
            log.exception("folder watch on_change failed")
