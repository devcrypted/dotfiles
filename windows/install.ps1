#Requires -Version 5.1
<#
.SYNOPSIS
    Idempotent Windows setup: winget apps, WSL with an Ubuntu distro, then debloating
    and hardening (windows/harden.ps1).
.DESCRIPTION
    The first run asks a few questions about this machine (harden it? keep OneDrive?
    keep Xbox? taskbar on the left?) and saves the answers to
    %ProgramData%\dotfiles\profile.json, so later runs don't ask. -Setup asks again.

    Per-machine overrides (optional) go in %ProgramData%\dotfiles\config.json:
      { "skipApps":   ["Docker.DockerDesktop"],      winget IDs from packages.json to leave out
        "extraApps":  ["Spotify.Spotify"],           more winget IDs for this machine
        "hardenSkip": ["security", "edge"] }         harden.ps1 sections to leave alone

    Safe to rerun: installed packages are skipped (never upgraded), enabled features
    and existing distros are left alone, and hardening runs again only when
    harden.ps1 or the answers change (or with -RerunHarden).
    Run from an elevated Windows PowerShell.
.EXAMPLE
    .\windows\install.ps1
    .\windows\install.ps1 -Setup               # answer the questions again
    .\windows\install.ps1 -SkipWsl -SkipHarden
    .\windows\install.ps1 -Yes                 # don't ask: harden with the defaults
    irm https://dot.kamal.sh | iex             # short URL (web/worker.js)
#>
[CmdletBinding()]
param(
    # winget export/import format; edit it to change the app list.
    [string]$PackagesFile = $(if ($PSScriptRoot) { Join-Path $PSScriptRoot 'packages.json' } else { '' }),
    [string]$Distro = 'Ubuntu-24.04',
    [switch]$SkipApps,
    [switch]$SkipWsl,
    [switch]$SkipHarden,
    [switch]$RerunHarden,
    # Ask the machine questions again.
    [switch]$Setup,
    # Don't ask: use saved answers, or the defaults on a first run.
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'
$RawBase = 'https://raw.githubusercontent.com/devcrypted/dotfiles/main/windows'
$StateDir = Join-Path $env:ProgramData 'dotfiles'
$ProfileFile = Join-Path $StateDir 'profile.json'
$ConfigFile = Join-Path $StateDir 'config.json'
$StateFile = Join-Path $StateDir 'state.json'

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated (Administrator) PowerShell.'
}

# Use the file next to this script, or download it when piped through `iex`.
function Get-RepoFile([string]$Name) {
    if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot $Name))) { return Join-Path $PSScriptRoot $Name }
    $path = Join-Path $env:TEMP "dotfiles-$Name"
    Invoke-WebRequest "$RawBase/$Name" -OutFile $path -UseBasicParsing
    return $path
}

function Read-Json([string]$Path) {
    if (Test-Path $Path) { return Get-Content -Raw $Path | ConvertFrom-Json }
    return $null
}

# --- Per-machine overrides (config.json, optional) ---------------------------------
$local = Read-Json $ConfigFile
$skipApps = @($local.skipApps | Where-Object { $_ })
$extraApps = @($local.extraApps | Where-Object { $_ })
$hardenSkip = @($local.hardenSkip | Where-Object { $_ })
if ($local) { Write-Host "Using overrides from $ConfigFile" -ForegroundColor DarkCyan }

# --- Machine profile: asked once, saved -------------------------------------------
$defaults = [ordered]@{ harden = $true; keepOneDrive = $false; keepXbox = $false; taskbarLeft = $false }
$saved = Read-Json $ProfileFile
$answers = [ordered]@{}
foreach ($key in $defaults.Keys) {
    $answers[$key] = if ($saved -and $null -ne $saved.$key) { [bool]$saved.$key } else { $defaults[$key] }
}
$missing = @($defaults.Keys | Where-Object { -not $saved -or $null -eq $saved.$_ })
$interactive = [Environment]::UserInteractive -and -not [Console]::IsInputRedirected -and -not $Yes

function Ask([string]$Question, [bool]$Default) {
    $hint = if ($Default) { '[Y/n]' } else { '[y/N]' }
    while ($true) {
        $reply = (Read-Host "  $Question $hint").Trim().ToLower()
        if ($reply -eq '') { return $Default }
        if ($reply -in 'y', 'yes') { return $true }
        if ($reply -in 'n', 'no') { return $false }
        Write-Host '     Please answer y or n.'
    }
}

if ($interactive -and ($Setup -or $missing)) {
    Write-Host "`nA few questions about this machine (saved to $ProfileFile; Enter keeps the [default]):" -ForegroundColor Cyan
    $answers.harden = Ask 'Debloat and harden Windows (preinstalled apps, telemetry, ads, Copilot/Recall, Start menu, taskbar, security)?' $answers.harden
    if ($answers.harden) {
        $answers.keepOneDrive = Ask 'Keep OneDrive?' $answers.keepOneDrive
        $answers.keepXbox = Ask 'Keep the Xbox app and Game Bar?' $answers.keepXbox
        $answers.taskbarLeft = Ask 'Move the taskbar icons to the left?' $answers.taskbarLeft
    }
    Write-Host ''
}
if ($Setup -or $missing) {
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
    $answers | ConvertTo-Json | Set-Content -Encoding UTF8 $ProfileFile
    if (-not $interactive) { Write-Host "Saved default answers to $ProfileFile (rerun with -Setup to change them)." -ForegroundColor DarkCyan }
}

# --- Apps --------------------------------------------------------------------------
if (-not $SkipApps) {
    if (-not $PackagesFile) { $PackagesFile = Get-RepoFile 'packages.json' }
    if ($skipApps -or $extraApps) {
        # Apply config.json to a copy of the list: drop skipped IDs, add extra ones.
        $list = Get-Content -Raw $PackagesFile | ConvertFrom-Json
        foreach ($source in $list.Sources) {
            $source.Packages = @($source.Packages | Where-Object { $skipApps -notcontains $_.PackageIdentifier })
        }
        $winget = $list.Sources | Where-Object { $_.SourceDetails.Name -eq 'winget' } | Select-Object -First 1
        foreach ($id in $extraApps) {
            if (@($winget.Packages.PackageIdentifier) -notcontains $id) {
                $winget.Packages += [pscustomobject]@{ PackageIdentifier = $id }
            }
        }
        $list.Sources = @($list.Sources | Where-Object { @($_.Packages).Count })
        $PackagesFile = Join-Path $env:TEMP 'dotfiles-packages.local.json'
        [IO.File]::WriteAllText($PackagesFile, ($list | ConvertTo-Json -Depth 6))  # UTF-8, no BOM
    }
    Write-Host 'Installing winget packages (installed ones are skipped)...' -ForegroundColor Cyan
    winget import --import-file $PackagesFile --no-upgrade --ignore-unavailable `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "winget import reported problems (exit code $LASTEXITCODE); see the output above."
    }
}

# --- WSL ---------------------------------------------------------------------------
$restartNeeded = $false
if (-not $SkipWsl) {
    foreach ($feature in 'Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform', 'HypervisorPlatform') {
        if ((Get-WindowsOptionalFeature -Online -FeatureName $feature).State -ne 'Enabled') {
            Write-Host "Enabling $feature..." -ForegroundColor Yellow
            $result = Enable-WindowsOptionalFeature -Online -FeatureName $feature -All -NoRestart
            $restartNeeded = $restartNeeded -or $result.RestartNeeded
        }
    }
    # `wsl --list` prints UTF-16; strip the NULs before comparing names.
    $distros = (wsl.exe --list --quiet 2>$null) -replace "`0", '' | Where-Object { $_ }
    if ($distros -notcontains $Distro) {
        Write-Host "Installing WSL distro $Distro..." -ForegroundColor Yellow
        wsl.exe --install --distribution $Distro --no-launch
    }
}

# --- Debloat and harden: once, then again when harden.ps1 or the answers change ----
if (-not $SkipHarden -and $answers.harden) {
    $script = Get-RepoFile 'harden.ps1'
    $sha = [Security.Cryptography.SHA256]::Create()
    $settings = @{ answers = $answers; skip = $hardenSkip } | ConvertTo-Json -Compress -Depth 4
    $bytes = [IO.File]::ReadAllBytes($script) + [Text.Encoding]::UTF8.GetBytes($settings)
    $fingerprint = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '').Substring(0, 16)
    $state = Read-Json $StateFile
    if ($state -and $state.harden -eq $fingerprint -and -not $RerunHarden) {
        Write-Host 'Debloat and hardening: done earlier (rerun with -RerunHarden).' -ForegroundColor DarkGray
    } else {
        Write-Host 'Debloating and hardening Windows...' -ForegroundColor Cyan
        $hardenArgs = @{ KeepOneDrive = $answers.keepOneDrive; KeepXbox = $answers.keepXbox; TaskbarLeft = $answers.taskbarLeft }
        if ($hardenSkip) { $hardenArgs.Skip = [string[]]$hardenSkip }
        & $script @hardenArgs
        New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
        @{ harden = $fingerprint; at = (Get-Date).ToString('s') } | ConvertTo-Json | Set-Content -Encoding UTF8 $StateFile
        $restartNeeded = $true
    }
}

if ($restartNeeded) {
    Write-Warning 'Restart Windows to finish (WSL features and hardening take effect after a restart).'
}
Write-Host 'Done. Next, inside WSL: see "Linux / WSL" in the README.' -ForegroundColor Green
