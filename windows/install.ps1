#Requires -Version 5.1
<#
.SYNOPSIS
    Idempotent Windows setup: winget packages, then WSL with an Ubuntu distro.
.DESCRIPTION
    Safe to rerun: installed packages are skipped (never upgraded) and enabled
    features or existing distros are left alone. Run from an elevated PowerShell.
.EXAMPLE
    .\windows\install.ps1
    .\windows\install.ps1 -SkipWsl
    irm https://raw.githubusercontent.com/devcrypted/dotfiles/main/windows/install.ps1 | iex
#>
[CmdletBinding()]
param(
    # winget export/import format; edit it to change the app list.
    [string]$PackagesFile = $(if ($PSScriptRoot) { Join-Path $PSScriptRoot 'packages.json' } else { '' }),
    [string]$Distro = 'Ubuntu-24.04',
    [switch]$SkipApps,
    [switch]$SkipWsl
)

$ErrorActionPreference = 'Stop'
$RawBase = 'https://raw.githubusercontent.com/devcrypted/dotfiles/main/windows'

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated (Administrator) PowerShell.'
}

if (-not $SkipApps) {
    if (-not $PackagesFile) {
        # Piped through `iex` there is no script folder: fetch the list from GitHub.
        $PackagesFile = Join-Path $env:TEMP 'dotfiles-packages.json'
        Invoke-WebRequest "$RawBase/packages.json" -OutFile $PackagesFile -UseBasicParsing
    }
    Write-Host 'Installing winget packages (installed ones are skipped)...' -ForegroundColor Cyan
    winget import --import-file $PackagesFile --no-upgrade --ignore-unavailable `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "winget import reported problems (exit code $LASTEXITCODE); see the output above."
    }
}

if (-not $SkipWsl) {
    $restartNeeded = $false
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
    if ($restartNeeded) {
        Write-Warning 'Restart Windows to finish enabling the WSL features.'
    }
}

Write-Host 'Done. Next, inside WSL: see "Linux / WSL" in the README.' -ForegroundColor Green
