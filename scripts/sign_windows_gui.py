#!/usr/bin/env python3
"""Local Authenticode signing GUI (tkinter) for gcode-index-gui.exe.

Browse for an unsigned .exe or unzipped CI artifact folder, pick a .pfx,
enter the password, and Sign — calls signtool directly (no PowerShell required
when packaged as Sign-WindowsGui.exe).

Remembers last target/PFX paths in %LOCALAPPDATA%\\gcode-index\\sign-windows-gui.ini
(paths only — never the password). Same ini as the WinForms Sign-WindowsGui.ps1.
"""

from __future__ import annotations

import configparser
import os
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

APP_TITLE = "G-code Index — local signing"
DEFAULT_TIMESTAMP = "http://timestamp.digicert.com"
TARGET_EXE_NAME = "gcode-index-gui.exe"


def _ini_path() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "gcode-index" / "sign-windows-gui.ini"


def load_remembered_paths() -> tuple[str, str]:
    path = _ini_path()
    if not path.is_file():
        return "", ""
    cfg = configparser.ConfigParser()
    try:
        cfg.read(path, encoding="utf-8")
    except configparser.Error:
        return "", ""
    section = cfg["Paths"] if cfg.has_section("Paths") else {}
    return section.get("LastTarget", "").strip(), section.get("LastPfx", "").strip()


def save_remembered_paths(target: str, pfx: str) -> None:
    path = _ini_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Paths only — do not put passwords here\n"
        "[Paths]\n"
        f"LastTarget={target}\n"
        f"LastPfx={pfx}\n",
        encoding="utf-8",
    )


def resolve_target_exe(input_path: Path) -> Path:
    if not input_path.exists():
        raise FileNotFoundError(f"Path not found: {input_path}")
    if input_path.is_file():
        if input_path.suffix.lower() != ".exe":
            raise ValueError(
                f"Expected a .exe file or an unzipped artifact folder, got: {input_path}"
            )
        return input_path.resolve()

    candidates: list[Path] = [
        input_path / TARGET_EXE_NAME,
        input_path / "gcode-index-gui" / TARGET_EXE_NAME,
    ]
    for found in input_path.rglob(TARGET_EXE_NAME):
        try:
            rel = found.relative_to(input_path)
        except ValueError:
            continue
        if len(rel.parts) <= 3:
            candidates.append(found)
    seen: set[Path] = set()
    for c in candidates:
        key = c.resolve() if c.exists() else c
        if key in seen:
            continue
        seen.add(key)
        if c.is_file():
            return c.resolve()
    raise FileNotFoundError(f"Could not find {TARGET_EXE_NAME} under folder: {input_path}")


def _sdk_version(path: Path) -> tuple[int, ...]:
    m = re.search(r"[\\/]bin[\\/]([\d.]+)[\\/]", str(path))
    if not m:
        return (0,)
    parts: list[int] = []
    for p in m.group(1).split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


def find_signtool(explicit: str | None = None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise FileNotFoundError(f"SignTool path not found: {explicit}")
        return p.resolve()

    which = _which("signtool.exe")
    if which:
        return which

    kit_roots = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Windows Kits"
        / "10"
        / "bin",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Windows Kits"
        / "10"
        / "bin",
    ]
    found: list[Path] = []
    for root in kit_roots:
        if not root.is_dir():
            continue
        for candidate in root.rglob("signtool.exe"):
            if candidate.parent.name.lower() in ("x64", "x86"):
                found.append(candidate)
    if not found:
        raise FileNotFoundError(
            "signtool.exe not found.\n\n"
            "Install the Windows SDK Signing Tools (Desktop Apps) from:\n"
            "  https://developer.microsoft.com/windows/downloads/windows-sdk/\n\n"
            "Typical location after install:\n"
            r"  C:\Program Files (x86)\Windows Kits\10\bin\<version>\x64\signtool.exe"
        )

    # Highest SDK version, then prefer x64 over x86.
    return max(
        found,
        key=lambda p: (_sdk_version(p), 1 if p.parent.name.lower() == "x64" else 0),
    ).resolve()


def _which(name: str) -> Path | None:
    path_env = os.environ.get("PATH", "")
    for folder in path_env.split(os.pathsep):
        if not folder:
            continue
        candidate = Path(folder) / name
        if candidate.is_file():
            return candidate.resolve()
    return None


def run_signtool(
    exe: Path,
    pfx: Path,
    password: str,
    *,
    timestamp_url: str | None = DEFAULT_TIMESTAMP,
    signtool: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> None:
    def _log(msg: str) -> None:
        if log:
            log(msg)

    tool = signtool or find_signtool()
    _log(f"Target: {exe}")
    _log(f"PFX:    {pfx}")
    _log(f"Tool:   {tool}")

    args = [
        str(tool),
        "sign",
        "/fd",
        "SHA256",
        "/f",
        str(pfx),
        "/p",
        password,
    ]
    if timestamp_url:
        _log(f"Stamp:  {timestamp_url}")
        args.extend(["/tr", timestamp_url, "/td", "SHA256"])
    else:
        _log("Stamp:  (skipped)")
    args.append(str(exe))

    _log("Signing…")
    # Do not log the full argv (contains /p password).
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if out:
        _log(out)
    if err:
        _log(err)
    if proc.returncode != 0:
        raise RuntimeError(
            f"signtool failed with exit code {proc.returncode}. "
            "Check PFX password, cert purpose (Code Signing), and that the exe is not locked."
        )

    _log("Verifying signature…")
    verify = subprocess.run(
        [str(tool), "verify", "/pa", "/v", str(exe)],
        capture_output=True,
        text=True,
        check=False,
    )
    vout = (verify.stdout or "").strip()
    verr = (verify.stderr or "").strip()
    if vout:
        _log(vout)
    if verr:
        _log(verr)
    if verify.returncode != 0:
        raise RuntimeError(
            f"signtool verify failed (exit {verify.returncode}). "
            "Signing may have partially succeeded — inspect the exe."
        )
    _log(f"OK — signed: {exe}")
    _log(
        "Remember: shop PCs must trust the signing certificate (or its CA) "
        "or SmartScreen/UAC warnings remain."
    )


class SignWindowsGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(520, 360)
        self.geometry("640x420")

        last_target, last_pfx = load_remembered_paths()

        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Target (.exe or unzipped artifact folder)").grid(
            row=0, column=0, columnspan=4, sticky="w", **pad
        )
        self.target_var = tk.StringVar(value=last_target)
        ttk.Entry(frm, textvariable=self.target_var).grid(
            row=1, column=0, columnspan=2, sticky="ew", **pad
        )
        ttk.Button(frm, text="Exe…", command=self._browse_exe, width=10).grid(
            row=1, column=2, **pad
        )
        ttk.Button(frm, text="Folder…", command=self._browse_folder, width=10).grid(
            row=1, column=3, **pad
        )

        ttk.Label(frm, text="Certificate (.pfx)").grid(
            row=2, column=0, columnspan=4, sticky="w", **pad
        )
        self.pfx_var = tk.StringVar(value=last_pfx)
        ttk.Entry(frm, textvariable=self.pfx_var).grid(
            row=3, column=0, columnspan=3, sticky="ew", **pad
        )
        ttk.Button(frm, text="Browse…", command=self._browse_pfx, width=10).grid(
            row=3, column=3, **pad
        )

        ttk.Label(frm, text="PFX password (leave blank to be prompted)").grid(
            row=4, column=0, columnspan=4, sticky="w", **pad
        )
        self.pwd_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.pwd_var, show="*").grid(
            row=5, column=0, columnspan=4, sticky="ew", **pad
        )

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=6, column=0, columnspan=4, sticky="ew", **pad)
        self.sign_btn = ttk.Button(btn_row, text="Sign", command=self._on_sign, width=12)
        self.sign_btn.pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="Ready — pick a target and .pfx, then Sign.")
        ttk.Label(btn_row, textvariable=self.status_var).pack(side=tk.LEFT, padx=12)

        self.log = tk.Text(frm, height=10, wrap=tk.WORD, state=tk.DISABLED)
        self.log.grid(row=7, column=0, columnspan=4, sticky="nsew", **pad)
        scroll = ttk.Scrollbar(frm, command=self.log.yview)
        scroll.grid(row=7, column=4, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(7, weight=1)

    def _append_log(self, text: str) -> None:
        if not text:
            return
        self.log.configure(state=tk.NORMAL)
        if self.log.index("end-1c") != "1.0":
            self.log.insert(tk.END, "\n")
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)
        self.update_idletasks()

    def _browse_exe(self) -> None:
        initial = self.target_var.get().strip()
        init_dir = ""
        if initial:
            p = Path(initial)
            init_dir = str(p.parent if p.is_file() else p) if p.exists() else ""
        path = filedialog.askopenfilename(
            title="Select gcode-index-gui.exe",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
            initialdir=init_dir or None,
        )
        if path:
            self.target_var.set(path)

    def _browse_folder(self) -> None:
        initial = self.target_var.get().strip()
        init_dir = ""
        if initial:
            p = Path(initial)
            if p.exists():
                init_dir = str(p if p.is_dir() else p.parent)
        path = filedialog.askdirectory(
            title="Select unzipped artifact folder containing gcode-index-gui.exe",
            initialdir=init_dir or None,
        )
        if path:
            self.target_var.set(path)

    def _browse_pfx(self) -> None:
        initial = self.pfx_var.get().strip()
        init_dir = ""
        if initial:
            p = Path(initial)
            if p.exists():
                init_dir = str(p.parent)
        path = filedialog.askopenfilename(
            title="Select code-signing .pfx",
            filetypes=[
                ("PFX certificate", "*.pfx *.p12"),
                ("All files", "*.*"),
            ],
            initialdir=init_dir or None,
        )
        if path:
            self.pfx_var.set(path)

    def _prompt_password(self) -> str | None:
        current = self.pwd_var.get()
        if current:
            return current
        pwd = simpledialog.askstring(
            "PFX password",
            "Enter the .pfx password:",
            show="*",
            parent=self,
        )
        return pwd  # None = cancelled

    def _on_sign(self) -> None:
        target_raw = self.target_var.get().strip()
        pfx_raw = self.pfx_var.get().strip()
        if not target_raw:
            messagebox.showwarning(APP_TITLE, "Choose a target .exe or unzipped folder first.")
            return
        if not Path(target_raw).exists():
            messagebox.showwarning(APP_TITLE, f"Target path not found:\n{target_raw}")
            return
        if not pfx_raw:
            messagebox.showwarning(APP_TITLE, "Choose a .pfx certificate file first.")
            return
        if not Path(pfx_raw).is_file():
            messagebox.showwarning(APP_TITLE, f"PFX file not found:\n{pfx_raw}")
            return

        pwd = self._prompt_password()
        if pwd is None:
            self.status_var.set("Cancelled — no password.")
            return
        if not pwd:
            messagebox.showwarning(APP_TITLE, "PFX password is required.")
            return

        target_full = str(Path(target_raw).resolve())
        pfx_full = str(Path(pfx_raw).resolve())
        save_remembered_paths(target_full, pfx_full)

        self.status_var.set("Signing…")
        self.sign_btn.configure(state=tk.DISABLED)
        self._append_log("---- signing ----")
        self._append_log(f"Target: {target_full}")
        self._append_log(f"PFX:    {pfx_full}")
        self.update_idletasks()

        stamp = os.environ.get("GCODE_SIGN_TIMESTAMP_URL", DEFAULT_TIMESTAMP)
        try:
            exe = resolve_target_exe(Path(target_full))
            run_signtool(
                exe,
                Path(pfx_full),
                pwd,
                timestamp_url=stamp if stamp else None,
                log=self._append_log,
            )
            self.status_var.set("OK — signed successfully.")
            messagebox.showinfo(
                APP_TITLE,
                f"Signed successfully.\n\n{exe}\n\n"
                "Shop PCs must trust this certificate (or its CA) or SmartScreen warnings remain.",
            )
        except Exception as exc:  # noqa: BLE001 — surface any signing failure in the GUI
            self.status_var.set("FAILED — see log.")
            self._append_log(f"ERROR: {exc}")
            messagebox.showerror(
                APP_TITLE,
                f"Signing failed.\n\n{exc}\n\n"
                "Check the log for details (missing signtool, wrong password, bad path, etc.).",
            )
        finally:
            self.pwd_var.set("")
            self.sign_btn.configure(state=tk.NORMAL)


def main() -> int:
    if sys.platform != "win32":
        print(
            "This signing GUI is intended for Windows (needs signtool). "
            f"Current platform: {sys.platform}",
            file=sys.stderr,
        )
        # Still allow the window to open for layout smoke-tests on Linux if DISPLAY is set.
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            return 1
    app = SignWindowsGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
