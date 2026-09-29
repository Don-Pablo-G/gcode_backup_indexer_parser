@echo off
REM Double-click launcher for Sign-WindowsGui.ps1 (STA + Bypass; cwd = this folder).
REM Prefer the packaged exe when available: download Sign-WindowsGui-* from CI, or
REM build with:  scripts\build-sign-gui.ps1  →  dist\Sign-WindowsGui.exe
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0Sign-WindowsGui.ps1"
set EXITCODE=%ERRORLEVEL%
if %EXITCODE% neq 0 (
  echo.
  echo Sign GUI exited with code %EXITCODE%.
  pause
)
exit /b %EXITCODE%
