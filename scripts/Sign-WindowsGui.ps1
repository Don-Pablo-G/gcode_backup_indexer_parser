#Requires -Version 5.1
<#
.SYNOPSIS
  Small WinForms picker for local Authenticode signing (calls sign-windows.ps1).

.DESCRIPTION
  Browse for gcode-index-gui.exe (or an unzipped artifact folder), browse for a
  .pfx, enter an optional password, and Sign. Remembers last target/PFX paths in
  %LOCALAPPDATA%\gcode-index\sign-windows-gui.ini (paths only — never the password).

  Prefer launching via Sign-WindowsGui.bat (double-click) so STA + Bypass are set.
  Absolute paths are used throughout so the current directory does not matter.

.NOTES
  Requires Windows + .NET WinForms + the sibling scripts\sign-windows.ps1 + signtool.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$SignScript = Join-Path $ScriptDir "sign-windows.ps1"
$IniPath = Join-Path $env:LOCALAPPDATA "gcode-index\sign-windows-gui.ini"

function Get-IniValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key
    )
    if (-not (Test-Path -LiteralPath $Path)) { return "" }
    $inSection = $false
    foreach ($line in Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue) {
        $t = $line.Trim()
        if ($t -eq "" -or $t.StartsWith("#") -or $t.StartsWith(";")) { continue }
        if ($t -match '^\[(.+)\]$') {
            $inSection = ($Matches[1] -eq "Paths")
            continue
        }
        if (-not $inSection) { continue }
        if ($t -match "^$([regex]::Escape($Key))\s*=\s*(.*)$") {
            return $Matches[1].Trim()
        }
    }
    return ""
}

function Save-IniPaths {
    param(
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$Pfx
    )
    $dir = Split-Path -Parent $IniPath
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    @"
# Paths only — do not put passwords here
[Paths]
LastTarget=$Target
LastPfx=$Pfx
"@ | Set-Content -LiteralPath $IniPath -Encoding UTF8
}

function Append-Log {
    param([System.Windows.Forms.TextBox]$Box, [string]$Text)
    if (-not $Text) { return }
    if ($Box.Text.Length -gt 0) { $Box.AppendText([Environment]::NewLine) }
    $Box.AppendText($Text)
    $Box.SelectionStart = $Box.Text.Length
    $Box.ScrollToCaret()
}

if (-not (Test-Path -LiteralPath $SignScript)) {
    [System.Windows.Forms.MessageBox]::Show(
        "Cannot find sign-windows.ps1 next to this tool:`n$SignScript`n`nKeep Sign-WindowsGui.ps1 in the repo scripts\ folder (or copy both scripts together).",
        "Sign Windows GUI",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "G-code Index — local signing"
$form.Size = New-Object System.Drawing.Size(640, 420)
$form.MinimumSize = New-Object System.Drawing.Size(520, 360)
$form.StartPosition = "CenterScreen"
$form.Font = New-Object System.Drawing.Font("Segoe UI", 9)

$lblTarget = New-Object System.Windows.Forms.Label
$lblTarget.Text = "Target (.exe or unzipped artifact folder)"
$lblTarget.Location = New-Object System.Drawing.Point(12, 12)
$lblTarget.AutoSize = $true

$txtTarget = New-Object System.Windows.Forms.TextBox
$txtTarget.Location = New-Object System.Drawing.Point(12, 34)
$txtTarget.Anchor = "Top,Left,Right"
$txtTarget.Width = 430

$btnExe = New-Object System.Windows.Forms.Button
$btnExe.Text = "Exe…"
$btnExe.Location = New-Object System.Drawing.Point(450, 32)
$btnExe.Width = 70
$btnExe.Anchor = "Top,Right"

$btnFolder = New-Object System.Windows.Forms.Button
$btnFolder.Text = "Folder…"
$btnFolder.Location = New-Object System.Drawing.Point(526, 32)
$btnFolder.Width = 80
$btnFolder.Anchor = "Top,Right"

$lblPfx = New-Object System.Windows.Forms.Label
$lblPfx.Text = "Certificate (.pfx)"
$lblPfx.Location = New-Object System.Drawing.Point(12, 70)
$lblPfx.AutoSize = $true

$txtPfx = New-Object System.Windows.Forms.TextBox
$txtPfx.Location = New-Object System.Drawing.Point(12, 92)
$txtPfx.Anchor = "Top,Left,Right"
$txtPfx.Width = 504

$btnPfx = New-Object System.Windows.Forms.Button
$btnPfx.Text = "Browse…"
$btnPfx.Location = New-Object System.Drawing.Point(526, 90)
$btnPfx.Width = 80
$btnPfx.Anchor = "Top,Right"

$lblPwd = New-Object System.Windows.Forms.Label
$lblPwd.Text = "PFX password (leave blank to be prompted)"
$lblPwd.Location = New-Object System.Drawing.Point(12, 126)
$lblPwd.AutoSize = $true

$txtPwd = New-Object System.Windows.Forms.TextBox
$txtPwd.Location = New-Object System.Drawing.Point(12, 148)
$txtPwd.Anchor = "Top,Left,Right"
$txtPwd.Width = 594
$txtPwd.UseSystemPasswordChar = $true

$btnSign = New-Object System.Windows.Forms.Button
$btnSign.Text = "Sign"
$btnSign.Location = New-Object System.Drawing.Point(12, 186)
$btnSign.Width = 100
$btnSign.Height = 28

$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Text = "Ready — pick a target and .pfx, then Sign."
$lblStatus.Location = New-Object System.Drawing.Point(120, 192)
$lblStatus.AutoSize = $true
$lblStatus.Anchor = "Top,Left,Right"
$lblStatus.MaximumSize = New-Object System.Drawing.Size(490, 0)

$txtLog = New-Object System.Windows.Forms.TextBox
$txtLog.Location = New-Object System.Drawing.Point(12, 228)
$txtLog.Multiline = $true
$txtLog.ScrollBars = "Vertical"
$txtLog.ReadOnly = $true
$txtLog.Anchor = "Top,Bottom,Left,Right"
$txtLog.Size = New-Object System.Drawing.Size(594, 140)
$txtLog.Font = New-Object System.Drawing.Font("Consolas", 9)

$form.Controls.AddRange(@(
    $lblTarget, $txtTarget, $btnExe, $btnFolder,
    $lblPfx, $txtPfx, $btnPfx,
    $lblPwd, $txtPwd,
    $btnSign, $lblStatus, $txtLog
))

# Restore last paths (not password)
$lastTarget = Get-IniValue -Path $IniPath -Key "LastTarget"
$lastPfx = Get-IniValue -Path $IniPath -Key "LastPfx"
if ($lastTarget) { $txtTarget.Text = $lastTarget }
if ($lastPfx) { $txtPfx.Text = $lastPfx }

$btnExe.Add_Click({
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Filter = "Executable (*.exe)|*.exe|All files (*.*)|*.*"
    $dlg.Title = "Select gcode-index-gui.exe"
    $dlg.CheckFileExists = $true
    if ($txtTarget.Text -and (Test-Path -LiteralPath $txtTarget.Text)) {
        $item = Get-Item -LiteralPath $txtTarget.Text
        if ($item.PSIsContainer) {
            $dlg.InitialDirectory = $item.FullName
        }
        else {
            $dlg.InitialDirectory = $item.DirectoryName
            $dlg.FileName = $item.Name
        }
    }
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $txtTarget.Text = $dlg.FileName
    }
})

$btnFolder.Add_Click({
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = "Select unzipped artifact folder containing gcode-index-gui.exe"
    $dlg.ShowNewFolderButton = $false
    if ($txtTarget.Text -and (Test-Path -LiteralPath $txtTarget.Text)) {
        $item = Get-Item -LiteralPath $txtTarget.Text
        if ($item.PSIsContainer) { $dlg.SelectedPath = $item.FullName }
        else { $dlg.SelectedPath = $item.DirectoryName }
    }
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $txtTarget.Text = $dlg.SelectedPath
    }
})

$btnPfx.Add_Click({
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Filter = "PFX certificate (*.pfx;*.p12)|*.pfx;*.p12|All files (*.*)|*.*"
    $dlg.Title = "Select code-signing .pfx"
    $dlg.CheckFileExists = $true
    if ($txtPfx.Text -and (Test-Path -LiteralPath $txtPfx.Text)) {
        $item = Get-Item -LiteralPath $txtPfx.Text
        $dlg.InitialDirectory = $item.DirectoryName
        $dlg.FileName = $item.Name
    }
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $txtPfx.Text = $dlg.FileName
    }
})

function Prompt-PasswordIfNeeded {
    param([string]$Current)
    if ($Current -and $Current.Length -gt 0) { return $Current }

    $dlg = New-Object System.Windows.Forms.Form
    $dlg.Text = "PFX password"
    $dlg.Size = New-Object System.Drawing.Size(360, 140)
    $dlg.StartPosition = "CenterParent"
    $dlg.FormBorderStyle = "FixedDialog"
    $dlg.MaximizeBox = $false
    $dlg.MinimizeBox = $false
    $dlg.ShowInTaskbar = $false

    $l = New-Object System.Windows.Forms.Label
    $l.Text = "Enter the .pfx password:"
    $l.Location = New-Object System.Drawing.Point(12, 12)
    $l.AutoSize = $true

    $t = New-Object System.Windows.Forms.TextBox
    $t.Location = New-Object System.Drawing.Point(12, 36)
    $t.Width = 320
    $t.UseSystemPasswordChar = $true

    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = "OK"
    $ok.Location = New-Object System.Drawing.Point(176, 70)
    $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $ok.Width = 75

    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = "Cancel"
    $cancel.Location = New-Object System.Drawing.Point(257, 70)
    $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $cancel.Width = 75

    $dlg.Controls.AddRange(@($l, $t, $ok, $cancel))
    $dlg.AcceptButton = $ok
    $dlg.CancelButton = $cancel

    if ($dlg.ShowDialog($form) -ne [System.Windows.Forms.DialogResult]::OK) {
        return $null
    }
    return $t.Text
}

$btnSign.Add_Click({
    $target = $txtTarget.Text.Trim()
    $pfx = $txtPfx.Text.Trim()

    if (-not $target) {
        [System.Windows.Forms.MessageBox]::Show(
            "Choose a target .exe or unzipped folder first.",
            "Sign Windows GUI",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
        return
    }
    if (-not (Test-Path -LiteralPath $target)) {
        [System.Windows.Forms.MessageBox]::Show(
            "Target path not found:`n$target",
            "Sign Windows GUI",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
        return
    }
    if (-not $pfx) {
        [System.Windows.Forms.MessageBox]::Show(
            "Choose a .pfx certificate file first.",
            "Sign Windows GUI",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
        return
    }
    if (-not (Test-Path -LiteralPath $pfx)) {
        [System.Windows.Forms.MessageBox]::Show(
            "PFX file not found:`n$pfx",
            "Sign Windows GUI",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
        return
    }

    $pwd = Prompt-PasswordIfNeeded -Current $txtPwd.Text
    if ($null -eq $pwd) {
        $lblStatus.Text = "Cancelled — no password."
        return
    }
    if ($pwd.Length -eq 0) {
        [System.Windows.Forms.MessageBox]::Show(
            "PFX password is required.",
            "Sign Windows GUI",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
        return
    }

    # Resolve to absolute paths so cwd never matters
    $targetFull = (Resolve-Path -LiteralPath $target).Path
    $pfxFull = (Resolve-Path -LiteralPath $pfx).Path
    $signFull = (Resolve-Path -LiteralPath $SignScript).Path

    Save-IniPaths -Target $targetFull -Pfx $pfxFull

    $lblStatus.Text = "Signing…"
    $btnSign.Enabled = $false
    $form.Cursor = [System.Windows.Forms.Cursors]::WaitCursor
    Append-Log -Box $txtLog -Text ("---- " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " ----")
    Append-Log -Box $txtLog -Text "Target: $targetFull"
    Append-Log -Box $txtLog -Text "PFX:    $pfxFull"
    Append-Log -Box $txtLog -Text "Script: $signFull"
    [System.Windows.Forms.Application]::DoEvents()

    $code = -1
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = "powershell.exe"
        # Password via env for the child only (never written to ini / never logged here)
        $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$signFull`" -Path `"$targetFull`" -PfxPath `"$pfxFull`""
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $psi.WorkingDirectory = $ScriptDir
        $psi.EnvironmentVariables["GCODE_SIGN_PFX_PASSWORD"] = $pwd
        $psi.EnvironmentVariables["GCODE_SIGN_PFX"] = $pfxFull

        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        [void]$proc.Start()
        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit()
        $code = $proc.ExitCode

        if ($stdout) { Append-Log -Box $txtLog -Text $stdout.TrimEnd() }
        if ($stderr) { Append-Log -Box $txtLog -Text $stderr.TrimEnd() }
    }
    catch {
        Append-Log -Box $txtLog -Text ("ERROR: " + $_.Exception.Message)
        $code = 1
    }
    finally {
        $pwd = $null
        $txtPwd.Text = ""
        $btnSign.Enabled = $true
        $form.Cursor = [System.Windows.Forms.Cursors]::Default
    }

    if ($code -eq 0) {
        $lblStatus.Text = "OK — signed successfully."
        $lblStatus.ForeColor = [System.Drawing.Color]::DarkGreen
        [System.Windows.Forms.MessageBox]::Show(
            "Signed successfully.`n`n$targetFull`n`nShop PCs must trust this certificate (or its CA) or SmartScreen warnings remain.",
            "Sign Windows GUI",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    }
    else {
        $lblStatus.Text = "FAILED — see log (exit $code)."
        $lblStatus.ForeColor = [System.Drawing.Color]::Firebrick
        [System.Windows.Forms.MessageBox]::Show(
            "Signing failed (exit code $code).`nCheck the log below for details (missing signtool, wrong password, bad path, etc.).",
            "Sign Windows GUI",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    }
})

[void]$form.ShowDialog()
exit 0
