@echo off
REM Build a standalone Windows GUI (onedir) with PyInstaller.
REM From the repo root (after: python -m pip install -e ".[dev,build]"):
REM
REM   scripts\build_windows.bat
REM
REM Output:
REM   dist\gcode-index-gui\gcode-index-gui.exe
REM   dist\gcode-index-gui\   (folder — keep together; do not ship only the .exe)

setlocal EnableExtensions
cd /d "%~dp0.."

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: python not found on PATH. Install Python 3.11+ from python.org
  echo        and ensure "Add python.exe to PATH" is checked.
  exit /b 1
)

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
  echo PyInstaller missing — installing build extra...
  python -m pip install -e ".[build]"
  if errorlevel 1 exit /b 1
)

echo.
echo === Building gcode-index-gui (onedir) ===
python -m PyInstaller --noconfirm --clean gcode-index-gui.spec
if errorlevel 1 (
  echo ERROR: PyInstaller failed.
  exit /b 1
)

set "OUT_DIR=dist\gcode-index-gui"
set "OUT_EXE=%OUT_DIR%\gcode-index-gui.exe"
if not exist "%OUT_EXE%" (
  echo ERROR: expected output not found: %OUT_EXE%
  exit /b 1
)

echo.
echo === Build OK ===
echo Run:  %OUT_EXE%
echo Zip the whole "%OUT_DIR%" folder to distribute (onedir needs companion DLLs).
echo.
dir /b "%OUT_DIR%"
exit /b 0
