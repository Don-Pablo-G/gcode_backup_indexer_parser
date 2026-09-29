#Requires -Version 5.1
<#
.SYNOPSIS
  Local Authenticode signing for gcode-index-gui.exe (post-download / post-build).

.DESCRIPTION
  Signs an unsigned Windows GUI exe with a local .pfx using signtool from the
  Windows SDK. Secrets stay on the machine — never commit .pfx or passwords.

  Password (first match wins):
    1. -Password SecureString parameter
    2. Env GCODE_SIGN_PFX_PASSWORD
    3. Interactive SecureString prompt

  PFX path (first match wins):
    1. -PfxPath parameter
    2. Env GCODE_SIGN_PFX

.PARAMETER Path
  Path to gcode-index-gui.exe, or to an unzipped onedir folder that contains it.

.PARAMETER PfxPath
  Path to the code-signing .pfx (optional if GCODE_SIGN_PFX is set).

.PARAMETER Password
  SecureString PFX password (optional; see Description).

.PARAMETER TimestampUrl
  RFC3161 timestamp server URL. Default: DigiCert public server.
  Override with -TimestampUrl or env GCODE_SIGN_TIMESTAMP_URL.
  Pass empty string to skip timestamping.

.PARAMETER SignTool
  Explicit path to signtool.exe (optional; otherwise discovered).

.EXAMPLE
  # After unzipping a GitHub Actions artifact:
  .\scripts\sign-windows.ps1 -Path "$env:USERPROFILE\Downloads\gcode-index-gui-0.2.114"

.EXAMPLE
  $env:GCODE_SIGN_PFX = "D:\certs\shop-codesign.pfx"
  .\scripts\sign-windows.ps1 -Path .\dist\gcode-index-gui-0.2.114\gcode-index-gui.exe

.NOTES
  Requires Windows SDK "Windows SDK Signing Tools for Desktop Apps" (signtool).
  This script does NOT create certificates or trust them on shop PCs — see README.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Path,

    [Parameter()]
    [string]$PfxPath = $env:GCODE_SIGN_PFX,

    [Parameter()]
    [SecureString]$Password,

    [Parameter()]
    [AllowEmptyString()]
    [string]$TimestampUrl = $(
        if ($env:GCODE_SIGN_TIMESTAMP_URL) { $env:GCODE_SIGN_TIMESTAMP_URL }
        else { "http://timestamp.digicert.com" }
    ),

    [Parameter()]
    [string]$SignTool
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Err([string]$Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
}

function Resolve-TargetExe([string]$InputPath) {
    if (-not (Test-Path -LiteralPath $InputPath)) {
        throw "Path not found: $InputPath"
    }
    $item = Get-Item -LiteralPath $InputPath
    if (-not $item.PSIsContainer) {
        if ($item.Extension -ne ".exe") {
            throw "Expected a .exe file or an unzipped artifact folder, got: $($item.FullName)"
        }
        return $item.FullName
    }
    $candidates = @(
        Join-Path $item.FullName "gcode-index-gui.exe"
        Join-Path $item.FullName "gcode-index-gui\gcode-index-gui.exe"
    )
    # Also search one level for versioned onedir folders
    $candidates += Get-ChildItem -LiteralPath $item.FullName -Filter "gcode-index-gui.exe" -Recurse -Depth 2 -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) {
            return (Get-Item -LiteralPath $c).FullName
        }
    }
    throw "Could not find gcode-index-gui.exe under folder: $($item.FullName)"
}

function Find-SignTool([string]$Explicit) {
    if ($Explicit) {
        if (-not (Test-Path -LiteralPath $Explicit)) {
            throw "SignTool path not found: $Explicit"
        }
        return (Get-Item -LiteralPath $Explicit).FullName
    }

    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        return $cmd.Source
    }

    $kitRoots = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
        "${env:ProgramFiles}\Windows Kits\10\bin"
    )
    $found = @()
    foreach ($root in $kitRoots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $found += Get-ChildItem -LiteralPath $root -Filter "signtool.exe" -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Directory.Name -match '^(x64|x86)$' }
    }
    if (-not $found) {
        throw @"
signtool.exe not found.

Install the Windows SDK Signing Tools (Desktop Apps) from:
  https://developer.microsoft.com/windows/downloads/windows-sdk/

Typical location after install:
  C:\Program Files (x86)\Windows Kits\10\bin\<version>\x64\signtool.exe

Or pass -SignTool with the full path, or add the kit bin\x64 folder to PATH.
"@
    }

    # Prefer highest SDK version, then x64 over x86
    $picked = $found |
        Sort-Object @{
            Expression = {
                if ($_.FullName -match '\\bin\\([\d.]+)\\') { [version]$Matches[1] } else { [version]"0.0" }
            }
            Descending = $true
        }, @{
            Expression = { if ($_.Directory.Name -eq "x64") { 0 } else { 1 } }
        } |
        Select-Object -First 1
    return $picked.FullName
}

function Get-PfxSecurePassword([SecureString]$Provided) {
    if ($Provided) { return $Provided }
    $plain = $env:GCODE_SIGN_PFX_PASSWORD
    if ($plain) {
        return (ConvertTo-SecureString -String $plain -AsPlainText -Force)
    }
    Write-Host "Enter PFX password (input hidden):" -ForegroundColor Cyan
    $secure = Read-Host -AsSecureString
    if (-not $secure -or $secure.Length -eq 0) {
        throw "PFX password is required (pass -Password, set GCODE_SIGN_PFX_PASSWORD, or type it at the prompt)."
    }
    return $secure
}

function ConvertFrom-SecureStringPlain([SecureString]$Secure) {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

# --- main ---

try {
    $exe = Resolve-TargetExe -InputPath $Path
    Write-Host "Target: $exe"

    if (-not $PfxPath) {
        throw @"
No .pfx path given.

Pass -PfxPath or set env GCODE_SIGN_PFX to your local certificate file.
Do not commit .pfx files to the repository.
"@
    }
    if (-not (Test-Path -LiteralPath $PfxPath)) {
        throw "PFX file not found: $PfxPath"
    }
    $pfxFull = (Get-Item -LiteralPath $PfxPath).FullName
    Write-Host "PFX:    $pfxFull"

    $signtoolPath = Find-SignTool -Explicit $SignTool
    Write-Host "Tool:   $signtoolPath"

    $securePwd = Get-PfxSecurePassword -Provided $Password
    $plainPwd = ConvertFrom-SecureStringPlain -Secure $securePwd

    $argList = @(
        "sign"
        "/fd", "SHA256"
        "/f", $pfxFull
        "/p", $plainPwd
    )
    if ($TimestampUrl) {
        Write-Host "Stamp:  $TimestampUrl"
        $argList += @("/tr", $TimestampUrl, "/td", "SHA256")
    }
    else {
        Write-Host "Stamp:  (skipped)"
    }
    $argList += $exe

    Write-Host ""
    Write-Host "Signing…" -ForegroundColor Cyan
    try {
        # Avoid echoing /p in our logs. Password may still appear briefly in OS process lists
        # (inherent to signtool /p) — prefer a machine-local PFX and a locked-down signing PC.
        & $signtoolPath @argList
        $code = $LASTEXITCODE
    }
    finally {
        $plainPwd = $null
        $argList = $null
        [GC]::Collect()
    }

    if ($code -ne 0) {
        throw "signtool failed with exit code $code. Check PFX password, cert purpose (Code Signing), and that the exe is not locked."
    }

    Write-Host ""
    Write-Host "Verifying signature…" -ForegroundColor Cyan
    & $signtoolPath verify /pa /v $exe
    if ($LASTEXITCODE -ne 0) {
        throw "signtool verify failed (exit $LASTEXITCODE). Signing may have partially succeeded — inspect the exe."
    }

    Write-Host ""
    Write-Host "OK — signed: $exe" -ForegroundColor Green
    Write-Host "Remember: shop PCs must trust the signing certificate (or its CA) or SmartScreen/UAC warnings remain."
    exit 0
}
catch {
    Write-Err $_.Exception.Message
    exit 1
}
