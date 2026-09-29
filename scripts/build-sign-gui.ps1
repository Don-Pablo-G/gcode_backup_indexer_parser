#Requires -Version 5.1
<#
.SYNOPSIS
  Build standalone Sign-WindowsGui.exe (PyInstaller onefile) for local Authenticode signing.

.DESCRIPTION
  Run on a Windows PC with Python 3.11+ (tkinter included with the official
  python.org installer). From the repo root:

    .\scripts\build-sign-gui.ps1

  Output:
    dist\Sign-WindowsGui.exe

  This is the small signing picker — not the main gcode-index-gui indexer build
  (that remains scripts\build_windows.bat / the Windows GUI build workflow).

.NOTES
  Requires: pip install pyinstaller  (or  python -m pip install -e ".[build]")
#>
[CmdletBinding()]
param(
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
Set-Location -LiteralPath $RepoRoot

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    throw "python not found on PATH. Install Python 3.11+ from python.org and check 'Add python.exe to PATH'."
}

Write-Host "=== Building Sign-WindowsGui.exe (onefile) ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"

# Ensure PyInstaller is available
& python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller missing — installing build extra..."
    & python -m pip install -e ".[build]"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install pyinstaller via .[build]" }
}

$script = Join-Path $RepoRoot "scripts\sign_windows_gui.py"
if (-not (Test-Path -LiteralPath $script)) {
    throw "Missing $script"
}

$outName = "Sign-WindowsGui"
$distDir = Join-Path $RepoRoot "dist"
$workDir = Join-Path $RepoRoot "build\sign-windows-gui"

if ($Clean) {
    if (Test-Path -LiteralPath $workDir) { Remove-Item -LiteralPath $workDir -Recurse -Force }
    $oldExe = Join-Path $distDir "$outName.exe"
    if (Test-Path -LiteralPath $oldExe) { Remove-Item -LiteralPath $oldExe -Force }
}

$args = @(
    "-m", "PyInstaller"
    "--noconfirm"
    "--clean"
    "--onefile"
    "--windowed"
    "--name", $outName
    "--distpath", $distDir
    "--workpath", $workDir
    "--specpath", $workDir
    $script
)

& python @args
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed (exit $LASTEXITCODE)"
}

$exe = Join-Path $distDir "$outName.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Expected output not found: $exe"
}

$item = Get-Item -LiteralPath $exe
Write-Host ""
Write-Host "=== Build OK ===" -ForegroundColor Green
Write-Host "Output: $($item.FullName)"
Write-Host ("Size:   {0:N0} bytes" -f $item.Length)
Write-Host ""
Write-Host "Run on the signing PC (needs Windows SDK signtool + your .pfx)."
Write-Host "This is NOT the main indexer — use scripts\build_windows.bat for gcode-index-gui.exe."
exit 0
