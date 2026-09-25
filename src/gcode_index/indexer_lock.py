"""Single-writer lock next to the database folder.

Used so only one Full-mode instance (typically one PC) watches / indexes into
a shared ``gcode_index.sqlite``. Prosty clients never take the lock.
"""

from __future__ import annotations

import os
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LOCK_FILENAME = "gcode_index.lock"
_STALE_HOURS = 12.0


@dataclass
class LockInfo:
    host: str
    pid: int
    started_at: str
    purpose: str = "watch"

    def summary(self) -> str:
        return f"{self.host} (pid {self.pid}, {self.purpose})"


def lock_path_for_target(target: Path | str) -> Path:
    return Path(target) / LOCK_FILENAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _parse_iso(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def is_lock_stale(info: LockInfo, *, max_age_hours: float = _STALE_HOURS) -> bool:
    """True when the lock holder is gone or the lock is older than ``max_age_hours``."""
    if info.host == socket.gethostname() and not _pid_alive(info.pid):
        return True
    started = _parse_iso(info.started_at)
    if started is None:
        return True
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - started).total_seconds() / 3600.0
    if info.host != socket.gethostname() and age_h > max_age_hours:
        return True
    if age_h > max_age_hours * 2:
        return True
    return False


def read_lock(target: Path | str) -> Optional[LockInfo]:
    path = lock_path_for_target(target)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    data: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, val = line.split("=", 1)
        data[key.strip().casefold()] = val.strip()
    try:
        pid = int(data.get("pid") or "0")
    except ValueError:
        pid = 0
    host = data.get("host") or ""
    if not host:
        return None
    return LockInfo(
        host=host,
        pid=pid,
        started_at=data.get("started_at") or "",
        purpose=data.get("purpose") or "watch",
    )


def _write_lock(target: Path | str, *, purpose: str) -> LockInfo:
    path = lock_path_for_target(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    info = LockInfo(
        host=socket.gethostname(),
        pid=os.getpid(),
        started_at=_utc_now_iso(),
        purpose=purpose,
    )
    path.write_text(
        (
            f"host={info.host}\n"
            f"pid={info.pid}\n"
            f"started_at={info.started_at}\n"
            f"purpose={info.purpose}\n"
        ),
        encoding="utf-8",
        newline="\n",
    )
    return info


def we_hold_lock(target: Path | str) -> bool:
    info = read_lock(target)
    if info is None:
        return False
    return info.host == socket.gethostname() and info.pid == os.getpid()


def try_acquire_lock(
    target: Path | str,
    *,
    purpose: str = "watch",
) -> tuple[bool, Optional[LockInfo]]:
    """Try to take the indexer lock.

    Returns ``(True, our_info)`` on success, or ``(False, holder)`` when another
    live instance owns it. Stale locks are replaced.
    """
    dest = Path(target)
    existing = read_lock(dest)
    if existing is not None:
        if existing.host == socket.gethostname() and existing.pid == os.getpid():
            # Refresh purpose / timestamp
            return True, _write_lock(dest, purpose=purpose)
        if not is_lock_stale(existing):
            return False, existing
    return True, _write_lock(dest, purpose=purpose)


def release_lock(target: Path | str) -> None:
    """Remove the lock file only if we own it."""
    dest = Path(target)
    info = read_lock(dest)
    if info is None:
        return
    if info.host != socket.gethostname() or info.pid != os.getpid():
        return
    path = lock_path_for_target(dest)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
