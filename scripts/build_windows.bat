@echo off
REM Build a standalone Windows GUI (onedir) with PyInstaller.
REM From the repo root (after: python -m pip install -e ".[dev,build]"):
REM
REM   scripts\build_windows.bat
REM
REM Output (versioned):
REM   dist\gcode-index-gui-<ver>\gcode-index-gui.exe
REM   dist\gcode-index-gui-windows-<ver>-<build>.zip

setlocal EnableExtensions EnableDelayedExpansion
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

for /f "usebackq delims=" %%V in (`python -c "from gcode_index import __version__; print(__version__)"`) do set "APP_VER=%%V"
if not defined APP_VER (
  echo ERROR: could not read gcode_index.__version__
  exit /b 1
)

REM Build id: CI run number > git short SHA > local timestamp
if defined GITHUB_RUN_NUMBER (
  set "APP_BUILD=b%GITHUB_RUN_NUMBER%"
) else (
  for /f "usebackq delims=" %%G in (`git rev-parse --short HEAD 2^>nul`) do set "APP_BUILD=%%G"
)
if not defined APP_BUILD (
  for /f "usebackq delims=" %%T in (`python -c "from datetime import datetime; print(datetime.now().strftime('%%Y%%m%%d%%H%%M'))"`) do set "APP_BUILD=%%T"
)

set "BUNDLE_DIR=gcode-index-gui-%APP_VER%"
set "ZIP_NAME=gcode-index-gui-windows-%APP_VER%-%APP_BUILD%.zip"

echo.
echo === Building gcode-index-gui (onedir) v%APP_VER% build %APP_BUILD% ===
python -m PyInstaller --noconfirm --clean gcode-index-gui.spec
if errorlevel 1 (
  echo ERROR: PyInstaller failed.
  exit /b 1
)

set "PYI_DIR=dist\gcode-index-gui"
set "OUT_DIR=dist\%BUNDLE_DIR%"
if not exist "%PYI_DIR%\gcode-index-gui.exe" (
  echo ERROR: expected output not found: %PYI_DIR%\gcode-index-gui.exe
  exit /b 1
)

if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%"
move "%PYI_DIR%" "%OUT_DIR%" >nul
if errorlevel 1 (
  echo ERROR: could not rename dist folder to %OUT_DIR%
  exit /b 1
)

REM Write version stamp next to the exe
(
  echo version=%APP_VER%
  echo build=%APP_BUILD%
) > "%OUT_DIR%\VERSION.txt"

echo.
echo === Zipping %ZIP_NAME% ===
python scripts\zip_onedir.py "%OUT_DIR%" "dist\%ZIP_NAME%"
if errorlevel 1 (
  echo ERROR: zip failed
  exit /b 1
)

echo.
echo === Build OK ===
echo Version: %APP_VER%
echo Build:   %APP_BUILD%
echo Run:     %OUT_DIR%\gcode-index-gui.exe
echo Zip:     dist\%ZIP_NAME%
echo.
dir /b "%OUT_DIR%"
exit /b 0
