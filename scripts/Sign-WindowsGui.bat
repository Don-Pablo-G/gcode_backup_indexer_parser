@echo off
REM Double-click launcher for Sign-WindowsGui.ps1 (STA + Bypass; cwd = this folder).
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0Sign-WindowsGui.ps1"
set EXITCODE=%ERRORLEVEL%
if %EXITCODE% neq 0 (
  echo.
  echo Sign GUI exited with code %EXITCODE%.
  pause
)
exit /b %EXITCODE%
