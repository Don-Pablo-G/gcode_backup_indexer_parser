"""Windows Explorer reveal helpers (Open folder / Otwórz folder)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from gcode_index import path_util
from gcode_index.path_util import (
    open_path_in_file_manager,
    windows_explorer_select_params,
)


def test_windows_explorer_select_params_quotes_spaces() -> None:
    params = windows_explorer_select_params(r"C:\Machine Backups\HAAS VF-2\dump.pgm")
    assert params == r'/select,"C:\Machine Backups\HAAS VF-2\dump.pgm"'


def test_windows_explorer_select_params_no_spaces() -> None:
    assert windows_explorer_select_params(r"C:\bak\file.nc") == r'/select,"C:\bak\file.nc"'


def test_windows_explorer_select_params_forward_slashes() -> None:
    params = windows_explorer_select_params("C:/Machine Backups/file.nc")
    assert params == r'/select,"C:\Machine Backups\file.nc"'


def test_windows_explorer_select_params_strips_trailing_backslash() -> None:
    params = windows_explorer_select_params(r"C:\Machine Backups\HAAS\\")
    assert params == r'/select,"C:\Machine Backups\HAAS"'


def test_open_path_win32_shellexecute_params(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """On win32, ShellExecute must get /select,\"…\" so spaces survive."""
    target = tmp_path / "Machine Backups" / "prog.nc"
    target.parent.mkdir(parents=True)
    target.write_text("O1\n", encoding="utf-8")

    seen: list[str] = []

    def _fake_shell(params: str) -> None:
        seen.append(params)

    monkeypatch.setattr(path_util.sys, "platform", "win32")
    monkeypatch.setattr(path_util, "_windows_shell_execute_explorer", _fake_shell)
    open_path_in_file_manager(target)

    assert seen == [windows_explorer_select_params(target.resolve())]
    assert "Machine Backups" in seen[0]
    assert seen[0].startswith('/select,"') and seen[0].endswith('"')


def test_open_path_win32_fallback_opens_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "Machine Backups" / "prog.nc"
    target.parent.mkdir(parents=True)
    target.write_text("O1\n", encoding="utf-8")

    def _boom(_params: str) -> None:
        raise OSError("shell failed")

    monkeypatch.setattr(path_util.sys, "platform", "win32")
    monkeypatch.setattr(path_util, "_windows_shell_execute_explorer", _boom)
    with mock.patch.object(path_util.subprocess, "Popen") as popen:
        open_path_in_file_manager(target)

    popen.assert_called_once()
    args = popen.call_args[0][0]
    assert args[0] == "explorer"
    assert Path(args[1]) == target.parent.resolve()
