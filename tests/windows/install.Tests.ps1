# Tests for windows/install.ps1's package selection. They run `-ListPackages`, which
# prints the winget IDs a machine would get and changes nothing, so they work on any OS
# with PowerShell (CI runs them on Linux). winget, WSL and hardening are not exercised.
#   Invoke-Pester tests/windows

BeforeAll {
    $script:Install = Join-Path $PSScriptRoot '..' '..' 'windows' 'install.ps1'
    $script:Base = (Get-Content -Raw (Join-Path $PSScriptRoot '..' '..' 'windows' 'packages.json') | ConvertFrom-Json).Sources.Packages.PackageIdentifier
    $script:Personas = Get-Content -Raw (Join-Path $PSScriptRoot '..' '..' 'windows' 'personas.json') | ConvertFrom-Json

    # Run the installer against a throwaway %ProgramData% so a real machine's answers
    # are never read or written.
    function Get-Packages {
        param([hashtable]$Params = @{}, [hashtable]$Profile, [hashtable]$Config)
        $env:ProgramData = Join-Path $TestDrive ([guid]::NewGuid())
        $dir = Join-Path $env:ProgramData 'dotfiles'
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        if ($Profile) { $Profile | ConvertTo-Json | Set-Content (Join-Path $dir 'profile.json') }
        if ($Config) { $Config | ConvertTo-Json | Set-Content (Join-Path $dir 'config.json') }
        $out = & $script:Install -ListPackages @Params
        return , @($out)
    }
}

Describe 'package selection' {
    It 'installs only the base when no persona is selected' {
        $ids = Get-Packages
        $ids | Should -Be ($script:Base | Select-Object -Unique)
    }

    It 'adds the selected personas and lists a shared package once' {
        $ids = Get-Packages -Params @{ Persona = 'node,k8s' }
        $ids | Should -Contain 'OpenJS.NodeJS.LTS'
        $ids | Should -Contain 'Kubernetes.kubectl'
        @($ids | Where-Object { $_ -eq 'Docker.DockerDesktop' }).Count | Should -Be 1
        $ids | Should -Not -Contain 'Python.Python.3.13'
    }

    It 'uses the persona saved in the profile' {
        $ids = Get-Packages -Profile @{ personas = @('python') }
        $ids | Should -Contain 'astral-sh.uv'
    }

    It 'lets -Persona none clear a saved selection' {
        $ids = Get-Packages -Params @{ Persona = 'none' } -Profile @{ personas = @('python') }
        $ids | Should -Not -Contain 'astral-sh.uv'
    }

    It 'applies skipApps and extraApps from config.json' {
        $ids = Get-Packages -Params @{ Persona = 'node' } -Config @{ skipApps = @('Docker.DockerDesktop', 'Git.Git'); extraApps = @('Spotify.Spotify') }
        $ids | Should -Not -Contain 'Docker.DockerDesktop'
        $ids | Should -Not -Contain 'Git.Git'
        $ids | Should -Contain 'Spotify.Spotify'
        $ids | Should -Contain 'pnpm.pnpm'
    }

    It 'stops with the valid names for an unknown persona' {
        { Get-Packages -Params @{ Persona = 'nope' } } | Should -Throw '*nope*node*'
    }

    It 'never changes the machine: the profile file is not written' {
        Get-Packages -Params @{ Persona = 'node' } | Out-Null
        Test-Path (Join-Path $env:ProgramData 'dotfiles' 'profile.json') | Should -BeFalse
    }
}
