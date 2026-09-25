"""Single-instance guard for the Windows GUI (PyInstaller-friendly).

On Windows: named mutex blocks a second process; a named event asks the
running instance (including tray-only) to restore/activate its window.

On other platforms: advisory lock file (best-effort) so local testing
behaves similarly; activation signal is a small sidecar file the first
instance can poll.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("gcode_index.single_instance")

# Local\ = current session only (correct for interactive GUI / RDP).
MUTEX_NAME = "Local\\GcodeBackupIndexerGUI_SingleInstance"
EVENT_NAME = "Local\\GcodeBackupIndexerGUI_Activate"
LOCK_FILENAME = "gcode-index-gui.single.lock"
ACTIVATE_FILENAME = "gcode-index-gui.activate"

ActivateCallback = Callable[[], None]


def _lock_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TMP") or tempfile.gettempdir()
    path = Path(base) / "gcode-index"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path(tempfile.gettempdir())
    return path


class SingleInstanceGuard:
    """Holds the single-instance lock for the lifetime of the GUI process."""

    def __init__(self) -> None:
        self._mutex = None
        self._event = None
        self._lock_file = None
        self._stop = threading.Event()
        self._watcher: Optional[threading.Thread] = None
        self._owned = False

    @property
    def owned(self) -> bool:
        return self._owned

    def release(self) -> None:
        self._stop.set()
        thr = self._watcher
        self._watcher = None
        if thr is not None and thr.is_alive():
            thr.join(timeout=2.0)
        if sys.platform == "win32":
            self._release_win()
        else:
            self._release_posix()
        self._owned = False

    def watch_activation(self, on_activate: ActivateCallback) -> None:
        """Background wait: when a second launch signals, call ``on_activate``."""
        if not self._owned:
            return
        if self._watcher is not None and self._watcher.is_alive():
            return
        self._stop.clear()
        self._watcher = threading.Thread(
            target=self._watch_loop,
            args=(on_activate,),
            name="gcode-single-instance",
            daemon=True,
        )
        self._watcher.start()

    def _watch_loop(self, on_activate: ActivateCallback) -> None:
        if sys.platform == "win32":
            self._watch_loop_win(on_activate)
        else:
            self._watch_loop_posix(on_activate)

    # --- Windows --------------------------------------------------------------

    def _acquire_win(self) -> bool:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetLastError(0)
        handle = kernel32.CreateMutexW(None, wintypes.BOOL(False), MUTEX_NAME)
        if not handle:
            log.warning("CreateMutexW failed; allowing this instance")
            return True
        err = kernel32.GetLastError()
        ERROR_ALREADY_EXISTS = 183
        if err == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        self._mutex = handle
        # Auto-reset event for activate requests
        event = kernel32.CreateEventW(None, wintypes.BOOL(False), wintypes.BOOL(False), EVENT_NAME)
        if event:
            self._event = event
        else:
            log.warning("CreateEventW failed; second launch cannot restore window")
        return True

    def _release_win(self) -> None:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        if self._event:
            try:
                kernel32.CloseHandle(self._event)
            except Exception:  # noqa: BLE001
                pass
            self._event = None
        if self._mutex:
            try:
                kernel32.ReleaseMutex(self._mutex)
            except Exception:  # noqa: BLE001
                pass
            try:
                kernel32.CloseHandle(self._mutex)
            except Exception:  # noqa: BLE001
                pass
            self._mutex = None

    def _watch_loop_win(self, on_activate: ActivateCallback) -> None:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        WAIT_OBJECT_0 = 0
        event = self._event
        if not event:
            return
        while not self._stop.is_set():
            # 400ms poll so shutdown can join quickly
            rc = kernel32.WaitForSingleObject(event, 400)
            if rc == WAIT_OBJECT_0:
                try:
                    on_activate()
                except Exception:  # noqa: BLE001
                    log.exception("activation callback failed")

    # --- POSIX / fallback -----------------------------------------------------

    def _acquire_posix(self) -> bool:
        path = _lock_dir() / LOCK_FILENAME
        try:
            fh = open(path, "a+", encoding="utf-8")
        except OSError:
            return True
        try:
            if sys.platform != "win32":
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.close()
            return False
        except OSError:
            fh.close()
            return True
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(str(os.getpid()))
            fh.flush()
        except OSError:
            pass
        self._lock_file = fh
        return True

    def _release_posix(self) -> None:
        fh = self._lock_file
        self._lock_file = None
        if fh is None:
            return
        try:
            if sys.platform != "win32":
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            fh.close()
        except OSError:
            pass

    def _watch_loop_posix(self, on_activate: ActivateCallback) -> None:
        path = _lock_dir() / ACTIVATE_FILENAME
        while not self._stop.wait(0.4):
            try:
                if path.is_file():
                    try:
                        path.unlink()
                    except OSError:
                        pass
                    try:
                        on_activate()
                    except Exception:  # noqa: BLE001
                        log.exception("activation callback failed")
            except OSError:
                continue


def try_acquire() -> Optional[SingleInstanceGuard]:
    """Return a held guard, or ``None`` if another instance already owns it."""
    guard = SingleInstanceGuard()
    ok = guard._acquire_win() if sys.platform == "win32" else guard._acquire_posix()
    if not ok:
        return None
    guard._owned = True
    return guard


def signal_existing_instance() -> bool:
    """Ask the running instance to restore/activate. Returns True if signaled."""
    if sys.platform == "win32":
        return _signal_existing_win()
    return _signal_existing_posix()


def _signal_existing_win() -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    SYNCHRONIZE = 0x00100000
    EVENT_MODIFY_STATE = 0x0002
    handle = kernel32.OpenEventW(EVENT_MODIFY_STATE | SYNCHRONIZE, wintypes.BOOL(False), EVENT_NAME)
    if not handle:
        log.info("No running instance event to signal")
        return False
    try:
        kernel32.SetEvent(handle)
        return True
    finally:
        kernel32.CloseHandle(handle)


def _signal_existing_posix() -> bool:
    path = _lock_dir() / ACTIVATE_FILENAME
    try:
        path.write_text(str(time.time()), encoding="utf-8")
        return True
    except OSError:
        return False


def try_activate_existing_window(*, title_substrings: Optional[list[str]] = None) -> bool:
    """Best-effort foreground restore via EnumWindows (Windows, incl. tray)."""
    if sys.platform != "win32":
        return False
    needles = [s.casefold() for s in (title_substrings or []) if s]
    if not needles:
        needles = [
            "g-code backup indexer",
            "indeksator kopii g-code",
        ]
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lparam):  # type: ignore[misc]
        if not user32.IsWindow(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.casefold()
        if any(n in title for n in needles):
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(_enum, 0)
    if not found:
        return False
    hwnd = found[0]
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return True
