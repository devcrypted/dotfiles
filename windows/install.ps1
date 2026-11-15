#Requires -Version 5.1
<#
.SYNOPSIS
    Idempotent Windows setup: winget apps, WSL with an Ubuntu distro, then debloating
    and hardening (windows/harden.ps1).
.DESCRIPTION
    The first run asks a few questions about this machine (harden it? keep OneDrive?
    keep Xbox? taskbar on the left?) and saves the answers to
    %ProgramData%\dotfiles\profile.json, so later runs don't ask. -Setup asks again.

    Personas are named toolsets (windows\personas.json: node, python, k8s, ai, azure,
    devops). packages.json is installed everywhere; each selected persona adds its
    packages. The selection is asked once and saved with the other answers; -Persona
    sets it without asking. -ListPackages prints what a machine would get and exits.

    Per-machine overrides (optional) go in %ProgramData%\dotfiles\config.json:
      { "skipApps":   ["Docker.DockerDesktop"],      winget IDs (base or persona) to leave out
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
    .\windows\install.ps1 -Persona node,k8s    # a Node.js and Kubernetes dev machine
    .\windows\install.ps1 -ListPackages        # preview the apps; changes nothing
    irm https://dot.kamal.sh | iex             # short URL (web/worker.js)
#>
[CmdletBinding()]
param(
    # winget export/import format; edit it to change the base app list.
    [string]$PackagesFile = $(if ($PSScriptRoot) { Join-Path $PSScriptRoot 'packages.json' } else { '' }),
    [string]$Distro = 'Ubuntu-24.04',
    [switch]$SkipApps,
    [switch]$SkipWsl,
    [switch]$SkipHarden,
    [switch]$RerunHarden,
    # Ask the machine questions again.
    [switch]$Setup,
    # Don't ask: use saved answers, or the defaults on a first run.
    [switch]$Yes,
    # Toolsets from personas.json to install on top of the base list; "none" for the base only.
    [string[]]$Persona,
    # Print the winget IDs this machine would get, then exit. Changes nothing, needs no admin.
    [switch]$ListPackages
)

$ErrorActionPreference = 'Stop'
$RawBase = 'https://raw.githubusercontent.com/devcrypted/dotfiles/main/windows'
$StateDir = Join-Path $env:ProgramData 'dotfiles'
$ProfileFile = Join-Path $StateDir 'profile.json'
$ConfigFile = Join-Path $StateDir 'config.json'
$StateFile = Join-Path $StateDir 'state.json'

if (-not $ListPackages) {
    $principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this script from an elevated (Administrator) PowerShell.'
    }
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

# The base list plus the selected personas' packages, minus skipApps, plus extraApps.
function Resolve-PackageList($List, [string[]]$Selected, $KnownPersonas, [string[]]$Skip, [string[]]$Extra) {
    $winget = $List.Sources | Where-Object { $_.SourceDetails.Name -eq 'winget' } | Select-Object -First 1
    $add = {
        param($Id)
        if (@($winget.Packages.PackageIdentifier) -notcontains $Id) {
            $winget.Packages += [pscustomobject]@{ PackageIdentifier = $Id }
        }
    }
    foreach ($name in $Selected) {
        foreach ($id in $KnownPersonas.$name.packages) { & $add $id }
    }
    foreach ($source in $List.Sources) {
        $source.Packages = @($source.Packages | Where-Object { $Skip -notcontains $_.PackageIdentifier })
    }
    foreach ($id in $Extra) { & $add $id }
    $List.Sources = @($List.Sources | Where-Object { @($_.Packages).Count })
    return $List
}

# A numbered menu: numbers or names, "none" for the base only, Enter keeps the default.
function Read-PersonaChoice($KnownPersonas, [string[]]$Current) {
    $names = @($KnownPersonas.PSObject.Properties.Name)
    Write-Host '  Personas: toolsets for the work this machine does. Pick any number.'
    for ($i = 0; $i -lt $names.Count; $i++) {
        Write-Host ('       {0}  {1,-7}  {2}' -f ($i + 1), $names[$i], $KnownPersonas.($names[$i]).about)
    }
    $shown = if ($Current) { $Current -join ',' } else { 'none' }
    while ($true) {
        $reply = (Read-Host "     Numbers or names (e.g. 1 3), or none [$shown]").Trim().ToLower()
        if ($reply -eq '') { return $Current }
        if ($reply -in 'none', '-', '0') { return @() }
        $picked = @()
        foreach ($token in ($reply -split '[,\s]+' | Where-Object { $_ })) {
            if ($token -match '^\d+$' -and [int]$token -ge 1 -and [int]$token -le $names.Count) { $token = $names[[int]$token - 1] }
            if ($names -notcontains $token) { $picked = $null; break }
            $picked += $token
        }
        if ($null -ne $picked) { return @($picked | Select-Object -Unique) }
        Write-Host '     Please answer with numbers or names from the list, or none.'
    }
}

# --- Per-machine overrides (config.json, optional) ---------------------------------
# Not named $skipApps/$extraApps: PowerShell variables are case-insensitive, so $skipApps
# would overwrite the -SkipApps switch.
$local = Read-Json $ConfigFile
$skipIds = @($local.skipApps | Where-Object { $_ })
$extraIds = @($local.extraApps | Where-Object { $_ })
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

# Personas. Precedence: -Persona, then the saved answer, then (asked below) nothing. They
# are kept apart from $answers: hardening's fingerprint must not change with them.
$knownPersonas = Get-Content -Raw (Get-RepoFile 'personas.json') | ConvertFrom-Json
$personaNames = @($knownPersonas.PSObject.Properties.Name)
$personasGiven = $PSBoundParameters.ContainsKey('Persona')
$personasSaved = $saved -and ($saved.PSObject.Properties.Name -contains 'personas')
if ($personasGiven) {
    $personas = @($Persona | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ -and $_ -ne 'none' })
} elseif ($personasSaved) {
    $personas = @($saved.personas | Where-Object { $_ })
} else {
    $personas = @()
}
$unknown = @($personas | Where-Object { $personaNames -notcontains $_ })
if ($unknown) {
    throw "No such persona: $($unknown -join ', ') (available: $($personaNames -join ', '))"
}
$personasKnown = $personasGiven -or $personasSaved

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

if (-not $ListPackages -and $interactive -and ($Setup -or $missing -or -not $personasKnown)) {
    Write-Host "`nA few questions about this machine (saved to $ProfileFile; Enter keeps the [default]):" -ForegroundColor Cyan
    if (-not $personasGiven) {
        $personas = @(Read-PersonaChoice $knownPersonas $personas)
        $personasKnown = $true
    }
    $answers.harden = Ask 'Debloat and harden Windows (preinstalled apps, telemetry, ads, Copilot/Recall, Start menu, taskbar, security)?' $answers.harden
    if ($answers.harden) {
        $answers.keepOneDrive = Ask 'Keep OneDrive?' $answers.keepOneDrive
        $answers.keepXbox = Ask 'Keep the Xbox app and Game Bar?' $answers.keepXbox
        $answers.taskbarLeft = Ask 'Move the taskbar icons to the left?' $answers.taskbarLeft
    }
    Write-Host ''
}
if (-not $ListPackages -and ($Setup -or $missing -or $personasGiven -or ($interactive -and $personasKnown -and -not $personasSaved))) {
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
    # Without a personas answer the file omits it, so a later run with a terminal asks.
    $toSave = [ordered]@{} + $answers
    if ($personasKnown) { $toSave.personas = @($personas) }
    $toSave | ConvertTo-Json | Set-Content -Encoding UTF8 $ProfileFile
    if (-not $interactive) { Write-Host "Saved default answers to $ProfileFile (rerun with -Setup to change them)." -ForegroundColor DarkCyan }
}

# --- Apps --------------------------------------------------------------------------
if ($ListPackages) {
    if (-not $PackagesFile) { $PackagesFile = Get-RepoFile 'packages.json' }
    $list = Resolve-PackageList -List (Get-Content -Raw $PackagesFile | ConvertFrom-Json) -Selected $personas `
        -KnownPersonas $knownPersonas -Skip $skipIds -Extra $extraIds
    $list.Sources.Packages.PackageIdentifier | Select-Object -Unique
    return
}
if (-not $SkipApps -and -not (Get-Command winget -ErrorAction SilentlyContinue)) {
    # Fresh VMs and Windows Server images can lack winget; the rest still runs.
    Write-Warning 'winget was not found, so apps are skipped. Install "App Installer" from the Microsoft Store (or update Windows), then run this again.'
    $SkipApps = $true
}
if (-not $SkipApps) {
    if (-not $PackagesFile) { $PackagesFile = Get-RepoFile 'packages.json' }
    if ($personas -or $skipIds -or $extraIds) {
        # Resolve the base list, personas and config.json into a copy for winget.
        $list = Resolve-PackageList -List (Get-Content -Raw $PackagesFile | ConvertFrom-Json) -Selected $personas `
            -KnownPersonas $knownPersonas -Skip $skipIds -Extra $extraIds
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
