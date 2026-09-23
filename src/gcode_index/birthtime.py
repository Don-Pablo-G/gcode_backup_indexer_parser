"""Platform-aware file creation/birth time with mtime fallback.

Date source of truth for the index is birth/creation time of the source file
(.nc or glued dump). Fallback order:

1. ``st_birthtime`` when present (macOS / some BSD / Windows Python builds)
2. Windows: ``st_ctime`` is creation time (not inode change)
3. Linux: try ``os.statx`` birthtime via ctypes when available
4. Else ``st_mtime`` with ``date_source=mtime``
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple


def _to_utc(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def file_birth_or_mtime(path: Path | str) -> Tuple[datetime, str]:
    """Return (timestamp, date_source) where date_source is 'birth' or 'mtime'."""
    p = Path(path)
    st = p.stat()

    birth = getattr(st, "st_birthtime", None)
    if birth is not None and birth > 0:
        return _to_utc(birth), "birth"

    if sys.platform == "win32":
        # On Windows, st_ctime is creation time.
        return _to_utc(st.st_ctime), "birth"

    # Linux: try statx(STATX_BTIME) when supported by kernel + filesystem.
    linux_birth = _linux_birthtime(p)
    if linux_birth is not None:
        return _to_utc(linux_birth), "birth"

    return _to_utc(st.st_mtime), "mtime"


def file_mtime(path: Path | str) -> datetime:
    return _to_utc(Path(path).stat().st_mtime)


def _linux_birthtime(path: Path) -> float | None:
    if sys.platform != "linux":
        return None
    try:
        import ctypes
        import ctypes.util
    except ImportError:
        return None

    libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)

    # Minimal subset of struct statx (glibc).
    class Timespec(ctypes.Structure):
        _fields_ = [("tv_sec", ctypes.c_int64), ("tv_nsec", ctypes.c_int64)]

    class StatxTimestamp(ctypes.Structure):
        _fields_ = [
            ("tv_sec", ctypes.c_int64),
            ("tv_nsec", ctypes.c_uint32),
            ("__reserved", ctypes.c_int32),
        ]

    class Statx(ctypes.Structure):
        _fields_ = [
            ("stx_mask", ctypes.c_uint32),
            ("stx_blksize", ctypes.c_uint32),
            ("stx_attributes", ctypes.c_uint64),
            ("stx_nlink", ctypes.c_uint32),
            ("stx_uid", ctypes.c_uint32),
            ("stx_gid", ctypes.c_uint32),
            ("stx_mode", ctypes.c_uint16),
            ("__spare0", ctypes.c_uint16),
            ("stx_ino", ctypes.c_uint64),
            ("stx_size", ctypes.c_uint64),
            ("stx_blocks", ctypes.c_uint64),
            ("stx_attributes_mask", ctypes.c_uint64),
            ("stx_atime", StatxTimestamp),
            ("stx_btime", StatxTimestamp),
            ("stx_ctime", StatxTimestamp),
            ("stx_mtime", StatxTimestamp),
            ("stx_rdev_major", ctypes.c_uint32),
            ("stx_rdev_minor", ctypes.c_uint32),
            ("stx_dev_major", ctypes.c_uint32),
            ("stx_dev_minor", ctypes.c_uint32),
            ("stx_mnt_id", ctypes.c_uint64),
            ("stx_dio_mem_align", ctypes.c_uint32),
            ("stx_dio_offset_align", ctypes.c_uint32),
            ("__spare2", ctypes.c_uint64 * 12),
        ]

    AT_FDCWD = -100
    AT_SYMLINK_NOFOLLOW = 0x100
    STATX_BTIME = 0x00000800

    try:
        statx = libc.statx
    except AttributeError:
        return None

    statx.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.POINTER(Statx),
    ]
    statx.restype = ctypes.c_int

    buf = Statx()
    path_b = os.fsencode(path)
    rc = statx(AT_FDCWD, path_b, AT_SYMLINK_NOFOLLOW, STATX_BTIME, ctypes.byref(buf))
    if rc != 0:
        return None
    if not (buf.stx_mask & STATX_BTIME):
        return None
    sec = buf.stx_btime.tv_sec
    nsec = buf.stx_btime.tv_nsec
    if sec <= 0:
        return None
    return float(sec) + (nsec / 1_000_000_000.0)
