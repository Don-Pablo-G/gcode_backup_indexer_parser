"""Folder watcher for indexer auto incremental index.

Modes
-----
``hybrid`` (Auto)
    OS filesystem events on **local** roots; stamp-poll on **network**/UNC roots.
``poll``
    Stamp-poll (size + mtime) everywhere — safe fallback for all roots.

Changes are debounced before ``on_change`` so a multi-file copy settles before
one incremental scan. OS events use the optional ``watchdog`` package; if it is
missing or fails to start for a root, that root falls back to poll.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

log = logging.getLogger("gcode_index.folder_watch")

ChangeCallback = Callable[[], None]
PollCallback = Callable[[], None]

WATCH_MODE_HYBRID = "hybrid"
WATCH_MODE_POLL = "poll"
DEFAULT_WATCH_MODE = WATCH_MODE_HYBRID

METHOD_EVENTS = "events"
METHOD_POLL = "poll"

# Windows GetDriveTypeW values
_DRIVE_UNKNOWN = 0
_DRIVE_REMOTE = 4
_DRIVE_FIXED = 3
_DRIVE_REMOVABLE = 2
_DRIVE_CDROM = 5
_DRIVE_RAMDISK = 6


def normalize_watch_mode(
    value: Optional[str], *, default: str = DEFAULT_WATCH_MODE
) -> str:
    raw = (value or "").strip().casefold()
    if not raw:
        return default
    if raw in (
        "hybrid",
        "auto",
        "automatic",
        "hybryda",
        "events+poll",
        "mixed",
    ):
        return WATCH_MODE_HYBRID
    if raw in (
        "poll",
        "polling",
        "stamp",
        "stamps",
        "safe",
        "tylko poll",
        "poll only",
        "poll-only",
    ):
        return WATCH_MODE_POLL
    return default


def is_unc_path(path: Path | str) -> bool:
    """True for ``\\\\server\\share\\…`` / ``//server/share/…``."""
    raw = os.fspath(path).replace("/", "\\")
    return raw.startswith("\\\\") and not raw.startswith("\\\\?\\")


def _win_drive_type(letter: str) -> int:
    """Return Windows GetDriveTypeW for ``X:`` (0 on failure / non-Windows)."""
    if os.name != "nt":
        return _DRIVE_UNKNOWN
    try:
        import ctypes

        root = f"{letter.upper()}:\\"
        return int(ctypes.windll.kernel32.GetDriveTypeW(root))  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return _DRIVE_UNKNOWN


def is_network_path(path: Path | str) -> bool:
    """Detect network/UNC paths — UNC prefix + Windows drive type (no feature flags)."""
    raw = os.fspath(path).strip()
    if not raw:
        return False
    if is_unc_path(raw):
        return True
    if raw.startswith("//") and not raw.startswith("//?/"):
        return True
    if len(raw) >= 2 and raw[1] == ":":
        dtype = _win_drive_type(raw[0])
        if dtype == _DRIVE_REMOTE:
            return True
        if dtype in (
            _DRIVE_FIXED,
            _DRIVE_REMOVABLE,
            _DRIVE_CDROM,
            _DRIVE_RAMDISK,
        ):
            return False
        return False
    return False


def watch_method_for_path(
    path: Path | str,
    mode: str,
    *,
    events_available: bool = True,
) -> str:
    """Return ``events`` or ``poll`` for one root under the given mode."""
    code = normalize_watch_mode(mode)
    if code == WATCH_MODE_POLL:
        return METHOD_POLL
    if is_network_path(path):
        return METHOD_POLL
    if events_available:
        return METHOD_EVENTS
    return METHOD_POLL


def short_root_label(path: Path | str, *, maxlen: int = 28) -> str:
    raw = os.fspath(path).strip()
    if not raw:
        return "?"
    if is_unc_path(raw) or raw.startswith("//"):
        norm = raw.replace("/", "\\").rstrip("\\")
        parts = [p for p in norm.split("\\") if p]
        if len(parts) >= 2:
            label = f"\\\\{parts[0]}\\{parts[1]}"
        else:
            label = norm
    else:
        label = raw
    if len(label) <= maxlen:
        return label
    return "…" + label[-(maxlen - 1) :]


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


def events_backend_available() -> bool:
    try:
        from watchdog.events import FileSystemEventHandler  # noqa: F401
        from watchdog.observers import Observer  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def path_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        try:
            return str(path.resolve()).casefold().startswith(
                str(root.resolve()).casefold()
            )
        except OSError:
            return str(path).casefold().startswith(str(root).casefold())


class FolderWatcher:
    """Hybrid/poll folder watcher with shared debounce → ``on_change``."""

    def __init__(
        self,
        *,
        on_change: ChangeCallback,
        poll_s: float = 5.0,
        debounce_s: float = 3.0,
        on_poll: Optional[PollCallback] = None,
        mode: str = DEFAULT_WATCH_MODE,
    ) -> None:
        self._on_change = on_change
        self._on_poll = on_poll
        self._poll_s = max(1.0, float(poll_s))
        self._debounce_s = max(0.5, float(debounce_s))
        self._mode = normalize_watch_mode(mode)
        self._roots: list[Path] = []
        self._root_methods: dict[str, str] = {}
        self._snapshot: dict[str, tuple[int, int]] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._pending_since: Optional[float] = None
        self._lock = threading.Lock()
        self._last_poll_at: Optional[datetime] = None
        self._last_change_at: Optional[datetime] = None
        self._last_event_at: Optional[datetime] = None
        self._stamp_count: int = 0
        self._observer = None
        self._events_ok = events_backend_available()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_poll_at(self) -> Optional[datetime]:
        with self._lock:
            return self._last_poll_at

    @property
    def last_event_at(self) -> Optional[datetime]:
        with self._lock:
            return self._last_event_at

    @property
    def last_change_at(self) -> Optional[datetime]:
        with self._lock:
            return self._last_change_at

    @property
    def stamp_count(self) -> int:
        with self._lock:
            return int(self._stamp_count)

    def set_mode(self, mode: str) -> None:
        self._mode = normalize_watch_mode(mode)
        self._recompute_methods()

    def set_roots(self, roots: Iterable[Path | str]) -> None:
        cleaned: list[Path] = []
        seen: set[str] = set()
        for raw in roots:
            raw_s = os.fspath(raw).strip()
            if not raw_s:
                continue
            # Do not resolve UNC / //server/share — on non-Windows resolve()
            # turns ``\\server\share`` into a relative local path under cwd.
            if is_unc_path(raw_s) or (
                raw_s.startswith("//") and not raw_s.startswith("//?/")
            ):
                p = Path(raw_s)
            else:
                try:
                    p = Path(raw_s).resolve()
                except OSError:
                    p = Path(raw_s)
            key = str(p).casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(p)
        with self._lock:
            self._roots = cleaned
        self._recompute_methods()

    def _recompute_methods(self) -> None:
        with self._lock:
            roots = list(self._roots)
            mode = self._mode
        methods: dict[str, str] = {}
        for root in roots:
            methods[str(root).casefold()] = watch_method_for_path(
                root, mode, events_available=self._events_ok
            )
        with self._lock:
            self._root_methods = methods

    def root_methods(self) -> list[tuple[str, str]]:
        """Return ``(short_label, method)`` for each root (``events``|``poll``)."""
        with self._lock:
            roots = list(self._roots)
            methods = dict(self._root_methods)
        return [
            (short_root_label(root), methods.get(str(root).casefold(), METHOD_POLL))
            for root in roots
        ]

    def poll_roots(self) -> list[Path]:
        with self._lock:
            roots = list(self._roots)
            methods = dict(self._root_methods)
        return [
            r
            for r in roots
            if methods.get(str(r).casefold(), METHOD_POLL) == METHOD_POLL
        ]

    def event_roots(self) -> list[Path]:
        with self._lock:
            roots = list(self._roots)
            methods = dict(self._root_methods)
        return [
            r
            for r in roots
            if methods.get(str(r).casefold(), METHOD_POLL) == METHOD_EVENTS
        ]

    def seed(self) -> int:
        """Take a baseline snapshot without firing ``on_change``. Returns file count."""
        with self._lock:
            roots = list(self._roots)
        snap = stamp_tree(roots)
        now = datetime.now(timezone.utc)
        with self._lock:
            self._snapshot = snap
            self._pending_since = None
            self._stamp_count = len(snap)
            self._last_poll_at = now
        return len(snap)

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        if not self._snapshot:
            self.seed()
        self._start_event_watchers()
        self._thread = threading.Thread(
            target=self._run, name="gcode-folder-watch", daemon=True
        )
        self._thread.start()

    def stop(self, *, join_timeout: float = 2.0) -> None:
        self._stop.set()
        self._stop_event_watchers()
        thr = self._thread
        self._thread = None
        if thr is not None and thr.is_alive():
            thr.join(timeout=join_timeout)
        with self._lock:
            self._pending_since = None

    def _start_event_watchers(self) -> None:
        self._stop_event_watchers()
        event_roots = self.event_roots()
        if not event_roots or not self._events_ok:
            return
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except Exception:  # noqa: BLE001
            log.warning("watchdog unavailable — event roots fall back to poll")
            self._events_ok = False
            self._recompute_methods()
            return

        watcher = self

        class _Handler(FileSystemEventHandler):
            def on_any_event(self, event) -> None:  # noqa: ANN001
                et = getattr(event, "event_type", "") or ""
                if getattr(event, "is_directory", False) and et in (
                    "opened",
                    "closed",
                    "closed_no_write",
                ):
                    return
                watcher._note_fs_event()

        observer = Observer()
        handler = _Handler()
        scheduled = 0
        for root in event_roots:
            try:
                if not root.is_dir():
                    log.debug("skip event watch; not a dir: %s", root)
                    continue
                observer.schedule(handler, str(root), recursive=True)
                scheduled += 1
            except Exception:  # noqa: BLE001
                log.warning(
                    "event watch failed for %s — will poll that root",
                    root,
                    exc_info=True,
                )
                with self._lock:
                    self._root_methods[str(root).casefold()] = METHOD_POLL
        if scheduled == 0:
            try:
                observer.stop()
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            observer.start()
        except Exception:  # noqa: BLE001
            log.exception("watchdog observer start failed")
            try:
                observer.stop()
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                for root in event_roots:
                    self._root_methods[str(root).casefold()] = METHOD_POLL
            return
        self._observer = observer
        log.info("folder watch events on %s local root(s)", scheduled)

    def _stop_event_watchers(self) -> None:
        obs = self._observer
        self._observer = None
        if obs is None:
            return
        try:
            obs.stop()
            obs.join(timeout=2.0)
        except Exception:  # noqa: BLE001
            log.debug("observer stop failed", exc_info=True)

    def _note_fs_event(self) -> None:
        now_mono = time.monotonic()
        now_wall = datetime.now(timezone.utc)
        with self._lock:
            self._last_event_at = now_wall
            self._last_change_at = now_wall
            if self._pending_since is None:
                self._pending_since = now_mono

    def _run(self) -> None:
        while not self._stop.wait(self._poll_s):
            try:
                self._tick()
            except Exception:  # noqa: BLE001
                log.exception("folder watch tick failed")

    def _tick(self) -> None:
        poll_roots = self.poll_roots()
        event_roots = self.event_roots()
        with self._lock:
            prev = dict(self._snapshot)
            all_roots = list(self._roots)
        now_mono = time.monotonic()
        now_wall = datetime.now(timezone.utc)

        changed = False
        if poll_roots:
            cur_poll = stamp_tree(poll_roots)
            old_poll = {
                k: v
                for k, v in prev.items()
                if any(path_under(Path(k), r) for r in poll_roots)
            }
            changed = cur_poll != old_poll

        # Status strip file count: stamp all roots when any use events
        if event_roots:
            full = stamp_tree(all_roots)
        elif poll_roots:
            full = stamp_tree(poll_roots)
        else:
            full = {}

        with self._lock:
            self._last_poll_at = now_wall
            self._stamp_count = len(full)
            self._snapshot = full
            if changed:
                self._last_change_at = now_wall
                if self._pending_since is None:
                    self._pending_since = now_mono
            pending_since = self._pending_since

        if self._on_poll is not None:
            try:
                self._on_poll()
            except Exception:  # noqa: BLE001
                log.exception("folder watch on_poll failed")

        if pending_since is None:
            return
        if (now_mono - pending_since) < self._debounce_s:
            return
        with self._lock:
            self._pending_since = None
        try:
            self._on_change()
        except Exception:  # noqa: BLE001
            log.exception("folder watch on_change failed")
