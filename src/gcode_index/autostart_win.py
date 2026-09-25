"""Windows logon autostart helpers (Startup folder shortcut + Task Scheduler).

No-op / returns clear errors on non-Windows. Uses PowerShell / ``schtasks`` so
we do not need pywin32.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger("gcode_index.autostart")

AUTOSTART_SHORTCUT_NAME = "G-code Backup Indexer.lnk"
TASK_NAME = "GcodeBackupIndexerGUI"
VIA_STARTUP = "startup"
VIA_TASK = "task"
VIA_CHOICES = (VIA_STARTUP, VIA_TASK)


def is_windows() -> bool:
    return sys.platform == "win32"


def launch_command() -> tuple[str, list[str]]:
    """Return ``(exe_or_python, args)`` for relaunching the GUI."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve()), []
    # Dev: python -m gcode_index.gui
    return sys.executable, ["-m", "gcode_index.gui"]


def launch_command_line() -> str:
    exe, args = launch_command()
    parts = [f'"{exe}"'] + [f'"{a}"' if " " in a else a for a in args]
    return " ".join(parts)


def startup_folder() -> Optional[Path]:
    if not is_windows():
        return None
    appdata = os.environ.get("APPDATA") or ""
    if not appdata:
        return None
    return (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def startup_shortcut_path() -> Optional[Path]:
    folder = startup_folder()
    if folder is None:
        return None
    return folder / AUTOSTART_SHORTCUT_NAME


def is_startup_installed() -> bool:
    path = startup_shortcut_path()
    return bool(path and path.is_file())


def install_startup_shortcut() -> tuple[bool, str]:
    """Create/replace Startup .lnk. Returns ``(ok, message)``."""
    if not is_windows():
        return False, "Autostart is only available on Windows."
    dest = startup_shortcut_path()
    if dest is None:
        return False, "Could not resolve the Windows Startup folder."
    exe, args = launch_command()
    workdir = str(Path(exe).resolve().parent)
    # PowerShell CreateShortcut
    target = exe
    arg_str = " ".join(args)
    # Escape for single-quoted PowerShell strings
    def _ps(s: str) -> str:
        return s.replace("'", "''")

    script = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{_ps(str(dest))}'); "
        f"$s.TargetPath = '{_ps(target)}'; "
        f"$s.Arguments = '{_ps(arg_str)}'; "
        f"$s.WorkingDirectory = '{_ps(workdir)}'; "
        f"$s.WindowStyle = 1; "
        f"$s.Description = 'G-code Backup Indexer'; "
        f"$s.Save()"
    )
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.exception("startup shortcut failed")
        return False, str(exc)
    if proc.returncode != 0 or not dest.is_file():
        err = (proc.stderr or proc.stdout or "shortcut not created").strip()
        return False, err
    return True, str(dest)


def remove_startup_shortcut() -> tuple[bool, str]:
    path = startup_shortcut_path()
    if path is None:
        return False, "Not on Windows."
    if not path.is_file():
        return True, "already removed"
    try:
        path.unlink()
        return True, str(path)
    except OSError as exc:
        return False, str(exc)


def is_task_installed() -> bool:
    if not is_windows():
        return False
    try:
        proc = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def install_logon_task() -> tuple[bool, str]:
    """Create/replace an at-logon Task Scheduler entry (current user)."""
    if not is_windows():
        return False, "Autostart is only available on Windows."
    cmd = launch_command_line()
    # /F force overwrite; /RL LIMITED = standard user
    try:
        proc = subprocess.run(
            [
                "schtasks",
                "/Create",
                "/F",
                "/TN",
                TASK_NAME,
                "/TR",
                cmd,
                "/SC",
                "ONLOGON",
                "/RL",
                "LIMITED",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.exception("schtasks create failed")
        return False, str(exc)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "schtasks failed").strip()
        return False, err
    return True, TASK_NAME


def remove_logon_task() -> tuple[bool, str]:
    if not is_windows():
        return False, "Not on Windows."
    if not is_task_installed():
        return True, "already removed"
    try:
        proc = subprocess.run(
            ["schtasks", "/Delete", "/F", "/TN", TASK_NAME],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "schtasks delete failed").strip()
        return False, err
    return True, TASK_NAME


def sync_autostart(*, enabled: bool, via: str = VIA_STARTUP) -> tuple[bool, str]:
    """Install or remove the chosen autostart mechanism; clean the other."""
    method = (via or VIA_STARTUP).strip().casefold()
    if method not in VIA_CHOICES:
        method = VIA_STARTUP
    if not enabled:
        ok1, msg1 = remove_startup_shortcut()
        ok2, msg2 = remove_logon_task()
        if ok1 and ok2:
            return True, "removed"
        return False, f"startup={msg1}; task={msg2}"
    if method == VIA_TASK:
        # Prefer task; remove Startup shortcut to avoid double launch
        remove_startup_shortcut()
        return install_logon_task()
    remove_logon_task()
    return install_startup_shortcut()


def normalize_autostart_via(value: Optional[str]) -> str:
    raw = (value or VIA_STARTUP).strip().casefold()
    if raw in ("task", "tasks", "scheduler", "schtasks", "harmonogram"):
        return VIA_TASK
    return VIA_STARTUP
