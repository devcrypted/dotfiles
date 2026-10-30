#Requires -Version 5.1
<#
.SYNOPSIS
    Debloat, de-clutter and harden Windows 10/11: preinstalled apps, telemetry, ads,
    Start menu, taskbar, Explorer, Copilot/Recall, Edge, and security settings.
.DESCRIPTION
    Run from an elevated PowerShell. Every registry value and service it changes is
    recorded first, so -Restore can put them back; a System Restore point is created
    before anything changes. Removed apps can be reinstalled from the Microsoft Store.
    Safe to rerun: values that are already right are skipped.

    Sections (run in this order; pick with -Only / -Skip):
      apps       remove preinstalled apps and ads (Candy Crush, Clipchamp, News, Teams...)
      privacy    telemetry, advertising ID, activity history, tailored experiences,
                 feedback prompts, error reporting, tracking services and tasks
      ai         Copilot, Recall, Click to Do, AI in Edge
      start      no web/Bing results, ads, recommendations or "suggested" apps in Start
      taskbar    hide search box, Task View, Widgets, Chat, Copilot; add "End task"
      explorer   show extensions and hidden files, open to This PC, classic right-click
                 menu, no recent/frequent files, no OneDrive ads
      ui         dark mode, no lock screen/Settings ads, no welcome or "finish setup"
                 nags, no Sticky Keys prompt, Fast Startup off (dual boot safe)
      edge       Edge policies: no first run, startup boost, background mode, shopping,
                 sidebar or tracking (Edge itself stays: Windows depends on it)
      onedrive   uninstall OneDrive (skip with -KeepOneDrive; local files are kept)
      xbox       remove Xbox apps and Game Bar, stop Xbox services (skip with -KeepXbox)
      security   Defender PUA + network protection + attack surface reduction rules,
                 SMBv1/PowerShell 2 off, LLMNR/NetBIOS off, NTLMv2 only, no autorun,
                 UAC always notify, LSA protection, firewall on, no Remote Assistance
      updates    no forced restarts while signed in, no peer-to-peer update sharing
      cleanup    temp files, Delivery Optimization cache, component store cleanup
.EXAMPLE
    .\windows\harden.ps1 -DryRun              # list what would change; changes nothing
    .\windows\harden.ps1                       # do everything
    .\windows\harden.ps1 -Skip onedrive,xbox -TaskbarLeft
    .\windows\harden.ps1 -Only privacy,start,taskbar
    .\windows\harden.ps1 -Restore C:\ProgramData\dotfiles\harden-undo-20261030-101500.json
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [ValidateSet('apps', 'privacy', 'ai', 'start', 'taskbar', 'explorer', 'ui', 'edge',
        'onedrive', 'xbox', 'security', 'updates', 'cleanup')]
    [string[]]$Only = @(),
    [ValidateSet('apps', 'privacy', 'ai', 'start', 'taskbar', 'explorer', 'ui', 'edge',
        'onedrive', 'xbox', 'security', 'updates', 'cleanup')]
    [string[]]$Skip = @(),
    [switch]$KeepOneDrive,
    [switch]$KeepXbox,
    # Move the Windows 11 taskbar icons to the left.
    [switch]$TaskbarLeft,
    [switch]$NoRestorePoint,
    # Put back the registry values and services recorded by an earlier run.
    [string]$Restore
)

$ErrorActionPreference = 'Stop'
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated (Administrator) PowerShell.'
}

$StateDir = Join-Path $env:ProgramData 'dotfiles'
$script:Undo = New-Object System.Collections.Generic.List[object]
$script:Changes = 0
$script:Notes = New-Object System.Collections.Generic.List[string]
$Build = [Environment]::OSVersion.Version.Build  # 22000+ is Windows 11

function Write-Section([string]$Name) { Write-Host "`n== $Name ==" -ForegroundColor Cyan }
function Write-Change([string]$Text) {
    $script:Changes++
    if ($DryRun) { Write-Host "  ~ $Text" -ForegroundColor Yellow } else { Write-Host "  + $Text" -ForegroundColor Green }
}
function Add-Note([string]$Text) { if (-not $script:Notes.Contains($Text)) { $script:Notes.Add($Text) } }

# --- Registry, services, tasks: each records how to undo itself ---------------------
function Set-Reg {
    param(
        [Parameter(Mandatory)][string]$Path,  # e.g. 'HKCU\Software\...'
        [Parameter(Mandatory)][string]$Name,  # '(Default)' for the key's default value
        [Parameter(Mandatory)][AllowEmptyString()]$Value,
        [ValidateSet('DWord', 'QWord', 'String', 'ExpandString', 'MultiString', 'Binary')]
        [string]$Type = 'DWord'
    )
    $key = "Registry::$Path"
    $existed = $false; $old = $null; $oldKind = $null
    if (Test-Path -LiteralPath $key) {
        $item = Get-Item -LiteralPath $key
        $valueName = if ($Name -eq '(Default)') { '' } else { $Name }
        if ($item.GetValueNames() -contains $valueName) {
            $existed = $true
            $old = $item.GetValue($valueName, $null, 'DoNotExpandEnvironmentNames')
            $oldKind = $item.GetValueKind($valueName).ToString()
            if ("$old" -eq "$Value") { return }
        }
    }
    Write-Change "$Path\$Name = $Value"
    if ($DryRun) { return }
    $script:Undo.Add([pscustomobject]@{ Kind = 'Reg'; Path = $Path; Name = $Name; Existed = $existed; Value = $old; Type = $oldKind })
    if (-not (Test-Path -LiteralPath $key)) { New-Item -Path $key -Force | Out-Null }
    New-ItemProperty -LiteralPath $key -Name $Name -Value $Value -PropertyType $Type -Force | Out-Null
}

function Disable-Svc([string]$Name, [ValidateSet('Disabled', 'Manual')][string]$StartType = 'Disabled') {
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc -or $svc.StartType.ToString() -eq $StartType) { return }
    Write-Change "service $Name -> $StartType"
    if ($DryRun) { return }
    $script:Undo.Add([pscustomobject]@{ Kind = 'Service'; Name = $Name; StartType = $svc.StartType.ToString() })
    if ($StartType -eq 'Disabled') { Stop-Service -Name $Name -Force -ErrorAction SilentlyContinue }
    Set-Service -Name $Name -StartupType $StartType -ErrorAction SilentlyContinue
}

function Disable-Task([string]$Path, [string]$Name) {
    $task = Get-ScheduledTask -TaskPath $Path -TaskName $Name -ErrorAction SilentlyContinue
    if (-not $task -or $task.State -eq 'Disabled') { return }
    Write-Change "scheduled task $Path$Name -> disabled"
    if ($DryRun) { return }
    $script:Undo.Add([pscustomobject]@{ Kind = 'Task'; Path = $Path; Name = $Name })
    $task | Disable-ScheduledTask | Out-Null
}

function Remove-Appx([string[]]$Patterns) {
    foreach ($pattern in $Patterns) {
        $installed = @(Get-AppxPackage -AllUsers -Name $pattern -ErrorAction SilentlyContinue)
        $provisioned = @(Get-AppxProvisionedPackage -Online | Where-Object DisplayName -Like $pattern)
        if (-not $installed -and -not $provisioned) { continue }
        Write-Change "remove app $pattern"
        if ($DryRun) { continue }
        foreach ($pkg in $installed) {
            try { Remove-AppxPackage -Package $pkg.PackageFullName -AllUsers -ErrorAction Stop }
            catch { Write-Host "    could not remove $($pkg.Name): $($_.Exception.Message)" -ForegroundColor DarkYellow }
        }
        # Provisioned packages are what new user accounts get.
        foreach ($pkg in $provisioned) {
            Remove-AppxProvisionedPackage -Online -PackageName $pkg.PackageName -ErrorAction SilentlyContinue | Out-Null
        }
    }
}

function Disable-Feature([string]$Name) {
    $feature = Get-WindowsOptionalFeature -Online -FeatureName $Name -ErrorAction SilentlyContinue
    if (-not $feature -or $feature.State -ne 'Enabled') { return }
    Write-Change "turn off Windows feature $Name"
    if (-not $DryRun) {
        Disable-WindowsOptionalFeature -Online -FeatureName $Name -NoRestart -WarningAction SilentlyContinue | Out-Null
        Add-Note 'Restart Windows to finish turning off Windows features.'
    }
}

# --- Restore -----------------------------------------------------------------------
if ($Restore) {
    $records = Get-Content -Raw -LiteralPath $Restore | ConvertFrom-Json
    [array]::Reverse($records)
    foreach ($r in $records) {
        switch ($r.Kind) {
            'Reg' {
                $key = "Registry::$($r.Path)"
                if ($r.Existed) {
                    if (-not (Test-Path -LiteralPath $key)) { New-Item -Path $key -Force | Out-Null }
                    New-ItemProperty -LiteralPath $key -Name $r.Name -Value $r.Value -PropertyType $r.Type -Force | Out-Null
                } else {
                    Remove-ItemProperty -LiteralPath $key -Name $r.Name -ErrorAction SilentlyContinue
                }
            }
            'Service' { Set-Service -Name $r.Name -StartupType $r.StartType -ErrorAction SilentlyContinue }
            'Task' { Enable-ScheduledTask -TaskPath $r.Path -TaskName $r.Name -ErrorAction SilentlyContinue | Out-Null }
        }
    }
    Write-Host "Restored $($records.Count) setting(s) from $Restore. Sign out and back in (or restart) to see them." -ForegroundColor Green
    return
}

# --- Sections ------------------------------------------------------------------------
$CDM = 'HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager'
$Adv = 'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced'

function Invoke-Apps {
    Remove-Appx @(
        # Microsoft extras
        'Microsoft.3DBuilder', 'Microsoft.BingFinance', 'Microsoft.BingFoodAndDrink', 'Microsoft.BingHealthAndFitness',
        'Microsoft.BingNews', 'Microsoft.BingSports', 'Microsoft.BingTranslator', 'Microsoft.BingTravel',
        'Microsoft.BingWeather', 'Microsoft.BingSearch', 'Microsoft.Messaging', 'Microsoft.Microsoft3DViewer',
        'Microsoft.MicrosoftOfficeHub', 'Microsoft.MicrosoftSolitaireCollection', 'Microsoft.MixedReality.Portal',
        'Microsoft.NetworkSpeedTest', 'Microsoft.News', 'Microsoft.Office.OneNote', 'Microsoft.Office.Sway',
        'Microsoft.OneConnect', 'Microsoft.People', 'Microsoft.Print3D', 'Microsoft.SkypeApp', 'Microsoft.Todos',
        'Microsoft.WindowsFeedbackHub', 'Microsoft.WindowsMaps', 'Microsoft.GetHelp', 'Microsoft.Getstarted',
        'Microsoft.ZuneMusic', 'Microsoft.ZuneVideo', 'Microsoft.YourPhone', 'Microsoft.PowerAutomateDesktop',
        'Microsoft.549981C3F5F10', # Cortana
        'Microsoft.OutlookForWindows', 'microsoft.windowscommunicationsapps', # new and old Mail/Calendar
        'Microsoft.Windows.DevHome', 'Microsoft.MicrosoftJournal', 'Microsoft.MicrosoftStickyNotes',
        'Microsoft.WindowsSoundRecorder', 'Microsoft.Wallet',
        'Clipchamp.Clipchamp', 'MicrosoftTeams', 'MSTeams', 'MicrosoftCorporationII.MicrosoftFamily',
        'MicrosoftCorporationII.QuickAssist', 'Microsoft.Windows.Ai.Copilot.Provider', 'Microsoft.Copilot',
        'Microsoft.MicrosoftPCManager', 'Microsoft.StartExperiencesApp', # Start menu "Phone Link" pane
        # Preinstalled third-party apps and games
        '*CandyCrush*', '*BubbleWitch*', '*king.com*', '*Disney*', '*Spotify*', '*Facebook*', '*Instagram*',
        '*TikTok*', '*Twitter*', '*Netflix*', '*LinkedIn*', '*AmazonVideo*', '*PrimeVideo*', '*Hulu*',
        '*Duolingo*', '*EclipseManager*', '*ActiproSoftware*', '*AdobePhotoshopExpress*', '*PandoraMedia*',
        '*Flipboard*', '*Shazam*', '*Wunderlist*', '*Royal Revolt*', '*Sway*', '*Dolby*', '*McAfee*',
        '*Norton*', '*ExpressVPN*', '*WinZip*', '*Booking*', '*Picsart*', '*CyberLink*', '*Asphalt*',
        '*MarchofEmpires*', '*HiddenCity*', '*FarmVille*', '*Minecraft*'
    )
    # Stop Windows from silently reinstalling sponsored apps.
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableWindowsConsumerFeatures' 1
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableConsumerAccountStateContent' 1
    foreach ($name in 'ContentDeliveryAllowed', 'FeatureManagementEnabled', 'OemPreInstalledAppsEnabled',
        'PreInstalledAppsEnabled', 'PreInstalledAppsEverEnabled', 'SilentInstalledAppsEnabled',
        'SoftLandingEnabled', 'SystemPaneSuggestionsEnabled') {
        Set-Reg $CDM $name 0
    }
    # Outlook and Dev Home come back through Windows Update unless these markers exist.
    Set-Reg 'HKLM\SOFTWARE\Microsoft\WindowsUpdate\Orchestrator\UScheduler_Oobe\OutlookUpdate' 'workCompleted' 1
    Set-Reg 'HKLM\SOFTWARE\Microsoft\WindowsUpdate\Orchestrator\UScheduler_Oobe\DevHomeUpdate' 'workCompleted' 1
    Add-Note 'Removed apps can be reinstalled from the Microsoft Store (or winget) if you miss one.'
}

function Invoke-Privacy {
    $dc = 'HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection'
    Set-Reg $dc 'AllowTelemetry' 0  # Enterprise/Education honour 0; Home/Pro clamp to "required"
    Set-Reg $dc 'MaxTelemetryAllowed' 1
    Set-Reg $dc 'DoNotShowFeedbackNotifications' 1
    Set-Reg $dc 'AllowDeviceNameInTelemetry' 0
    Set-Reg $dc 'LimitDiagnosticLogCollection' 1
    Set-Reg $dc 'LimitDumpCollection' 1
    Set-Reg $dc 'DisableOneSettingsDownloads' 1
    Set-Reg 'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection' 'AllowTelemetry' 0
    Set-Reg 'HKCU\Software\Microsoft\Siuf\Rules' 'NumberOfSIUFInPeriod' 0
    Set-Reg 'HKCU\Software\Microsoft\Siuf\Rules' 'PeriodInNanoSeconds' 0
    # Advertising ID, tailored experiences, language list for websites, app launch tracking.
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\AdvertisingInfo' 'DisabledByGroupPolicy' 1
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo' 'Enabled' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Privacy' 'TailoredExperiencesWithDiagnosticDataEnabled' 0
    Set-Reg 'HKCU\Software\Policies\Microsoft\Windows\CloudContent' 'DisableTailoredExperiencesWithDiagnosticData' 1
    Set-Reg 'HKCU\Control Panel\International\User Profile' 'HttpAcceptLanguageOptOut' 1
    Set-Reg $Adv 'Start_TrackProgs' 0
    # Activity history / Timeline, cloud clipboard, inking and typing personalisation.
    $sys = 'HKLM\SOFTWARE\Policies\Microsoft\Windows\System'
    Set-Reg $sys 'EnableActivityFeed' 0
    Set-Reg $sys 'PublishUserActivities' 0
    Set-Reg $sys 'UploadUserActivities' 0
    Set-Reg $sys 'AllowCrossDeviceClipboard' 0
    Set-Reg 'HKCU\Software\Microsoft\InputPersonalization' 'RestrictImplicitInkCollection' 1
    Set-Reg 'HKCU\Software\Microsoft\InputPersonalization' 'RestrictImplicitTextCollection' 1
    Set-Reg 'HKCU\Software\Microsoft\InputPersonalization\TrainedDataStore' 'HarvestContacts' 0
    Set-Reg 'HKCU\Software\Microsoft\Personalization\Settings' 'AcceptedPrivacyPolicy' 0
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\TabletPC' 'PreventHandwritingDataSharing' 1
    Set-Reg 'HKCU\Software\Microsoft\Input\TIPC' 'Enabled' 0
    # Error reporting, Customer Experience Improvement Program, app compatibility telemetry.
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Error Reporting' 'Disabled' 1
    Set-Reg 'HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting' 'Disabled' 1
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\SQMClient\Windows' 'CEIPEnable' 0
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\AppCompat' 'AITEnable' 0
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\AppCompat' 'DisableInventory' 1
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\AppCompat' 'DisableUAR' 1
    # Find My Device pings, cloud-optimised content, search history in the cloud.
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\FindMyDevice' 'AllowFindMyDevice' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\SearchSettings' 'IsDeviceSearchHistoryEnabled' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\SearchSettings' 'IsMSACloudSearchEnabled' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\SearchSettings' 'IsAADCloudSearchEnabled' 0

    Disable-Svc 'DiagTrack'           # Connected User Experiences and Telemetry
    Disable-Svc 'dmwappushservice'    # WAP push routing, used by telemetry
    Disable-Svc 'diagsvc' 'Manual'
    Disable-Svc 'WerSvc' 'Manual'
    Disable-Svc 'RetailDemo'
    Disable-Svc 'MapsBroker' 'Manual'
    Disable-Svc 'WMPNetworkSvc'
    Disable-Svc 'RemoteRegistry'
    Disable-Svc 'lfsvc' 'Manual'      # geolocation: only starts when an app asks

    $tasks = @(
        @('\Microsoft\Windows\Application Experience\', 'Microsoft Compatibility Appraiser'),
        @('\Microsoft\Windows\Application Experience\', 'Microsoft Compatibility Appraiser Exp'),
        @('\Microsoft\Windows\Application Experience\', 'ProgramDataUpdater'),
        @('\Microsoft\Windows\Application Experience\', 'StartupAppTask'),
        @('\Microsoft\Windows\Application Experience\', 'MareBackup'),
        @('\Microsoft\Windows\Application Experience\', 'PcaPatchDbTask'),
        @('\Microsoft\Windows\Autochk\', 'Proxy'),
        @('\Microsoft\Windows\Customer Experience Improvement Program\', 'Consolidator'),
        @('\Microsoft\Windows\Customer Experience Improvement Program\', 'UsbCeip'),
        @('\Microsoft\Windows\DiskDiagnostic\', 'Microsoft-Windows-DiskDiagnosticDataCollector'),
        @('\Microsoft\Windows\Feedback\Siuf\', 'DmClient'),
        @('\Microsoft\Windows\Feedback\Siuf\', 'DmClientOnScenarioDownload'),
        @('\Microsoft\Windows\Windows Error Reporting\', 'QueueReporting'),
        @('\Microsoft\Windows\Maps\', 'MapsUpdateTask'),
        @('\Microsoft\Windows\Maps\', 'MapsToastTask'),
        @('\Microsoft\Windows\CloudExperienceHost\', 'CreateObjectTask'),
        @('\Microsoft\Windows\Flighting\FeatureConfig\', 'UsageDataReporting')
    )
    foreach ($t in $tasks) { Disable-Task $t[0] $t[1] }
}

function Invoke-AI {
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot' 'TurnOffWindowsCopilot' 1
    Set-Reg 'HKCU\Software\Policies\Microsoft\Windows\WindowsCopilot' 'TurnOffWindowsCopilot' 1
    $ai = 'HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsAI'
    Set-Reg $ai 'DisableAIDataAnalysis' 1    # Recall snapshots
    Set-Reg $ai 'AllowRecallEnablement' 0
    Set-Reg $ai 'TurnOffSavingSnapshots' 1
    Set-Reg $ai 'DisableClickToDo' 1
    Set-Reg 'HKCU\Software\Policies\Microsoft\Windows\WindowsAI' 'DisableAIDataAnalysis' 1
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Edge' 'CopilotPageContext' 0
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Edge' 'CopilotCDPPageContext' 0
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Edge' 'Microsoft365CopilotChatIconEnabled' 0
    Set-Reg 'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Paint' 'DisableCocreator' 1
    Set-Reg 'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Paint' 'DisableGenerativeFill' 1
    Set-Reg 'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Paint' 'DisableImageCreator' 1
    Remove-Appx @('Microsoft.Copilot', 'Microsoft.Windows.Ai.Copilot.Provider', 'Microsoft.MicrosoftOfficeHub')
    Disable-Feature 'Recall'
}

function Invoke-Start {
    # Search: local results only, no Bing, no "search highlights".
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Search' 'BingSearchEnabled' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Search' 'CortanaConsent' 0
    Set-Reg 'HKCU\Software\Policies\Microsoft\Windows\Explorer' 'DisableSearchBoxSuggestions' 1
    $search = 'HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Search'
    Set-Reg $search 'DisableWebSearch' 1
    Set-Reg $search 'ConnectedSearchUseWeb' 0
    Set-Reg $search 'AllowCortana' 0
    Set-Reg $search 'AllowCloudSearch' 0
    Set-Reg $search 'EnableDynamicContentInWSB' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Feeds\DSB' 'ShowDynamicContent' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\SearchSettings' 'IsDynamicSearchBoxEnabled' 0
    # Start: no recommendations, recent files, ads or account nags; more room for pins.
    Set-Reg $Adv 'Start_IrisRecommendations' 0
    Set-Reg $Adv 'Start_TrackDocs' 0
    Set-Reg $Adv 'Start_AccountNotifications' 0
    Set-Reg $Adv 'Start_RecoPersonalizedSites' 0
    Set-Reg $Adv 'Start_Layout' 1
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Start' 'ShowRecentList' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Start' 'ShowAllPinsList' 1
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer' 'HideRecommendedPersonalizedSites' 1
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer' 'HideRecommendedSection' 1
    Set-Reg 'HKLM\SOFTWARE\Microsoft\PolicyManager\current\device\Start' 'HideRecommendedSection' 1
    # HideRecommendedSection only takes effect in an "education environment" on Home/Pro.
    Set-Reg 'HKLM\SOFTWARE\Microsoft\PolicyManager\current\device\Education' 'IsEducationEnvironment' 1
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer' 'NoStartMenuMFUprogramsList' 1
    # "Suggested" apps and tips in Start / Settings / notifications.
    foreach ($id in '310093', '314563', '338387', '338388', '338389', '338393', '353694', '353696', '353698', '88000326') {
        Set-Reg $CDM "SubscribedContent-$($id)Enabled" 0
    }
}

function Invoke-Taskbar {
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Search' 'SearchboxTaskbarMode' 0
    Set-Reg $Adv 'ShowTaskViewButton' 0
    Set-Reg $Adv 'TaskbarMn' 0           # Chat / Teams
    Set-Reg $Adv 'ShowCopilotButton' 0
    Set-Reg $Adv 'TaskbarBadges' 1
    Set-Reg $Adv 'TaskbarSn' 0           # "Share any window" in Teams calls
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\TaskbarDeveloperSettings' 'TaskbarEndTask' 1
    # Widgets / News and Interests (the TaskbarDa value is locked on new builds; policy works).
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Dsh' 'AllowNewsAndInterests' 0
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Feeds' 'EnableFeeds' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Feeds' 'ShellFeedsTaskbarViewMode' 2
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer' 'HideSCAMeetNow' 1
    Set-Reg 'HKCU\Software\Policies\Microsoft\Windows\Explorer' 'HidePeopleBar' 1
    Remove-Appx @('MicrosoftWindows.Client.WebExperience')  # the Widgets board itself
    if ($TaskbarLeft) { Set-Reg $Adv 'TaskbarAl' 0 }
}

function Invoke-Explorer {
    Set-Reg $Adv 'HideFileExt' 0
    Set-Reg $Adv 'Hidden' 1
    Set-Reg $Adv 'LaunchTo' 1            # This PC instead of Home
    Set-Reg $Adv 'ShowSyncProviderNotifications' 0
    Set-Reg $Adv 'NavPaneExpandToCurrentFolder' 1
    Set-Reg $Adv 'UseCompactMode' 1
    Set-Reg $Adv 'ShowInfoTip' 1
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer' 'ShowRecent' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer' 'ShowFrequent' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer' 'ShowCloudFilesInQuickAccess' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\CabinetState' 'FullPath' 1
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\OperationStatusManager' 'EnthusiastMode' 1
    if ($Build -ge 22000) {
        # Windows 10 style right-click menu (no "Show more options").
        Set-Reg 'HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32' '(Default)' '' 'String' # gitleaks:allow
        # Hide Gallery and Home from the navigation pane.
        Set-Reg 'HKCU\Software\Classes\CLSID\{e88865ea-0e1c-4e20-9aa6-edcd0212c87c}' 'System.IsPinnedToNameSpaceTree' 0 # gitleaks:allow
        Set-Reg 'HKCU\Software\Classes\CLSID\{f874310e-b6b7-47dc-bc84-b9e6b38f5903}' 'System.IsPinnedToNameSpaceTree' 0 # gitleaks:allow
    }
    # No "- Shortcut" suffix on new shortcuts.
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\NamingTemplates' 'ShortcutNameTemplate' '%s.lnk' 'String'
}

function Invoke-UI {
    $theme = 'HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'
    Set-Reg $theme 'AppsUseLightTheme' 0
    Set-Reg $theme 'SystemUsesLightTheme' 0
    # Lock screen and Settings: no tips, fun facts or ads.
    Set-Reg $CDM 'RotatingLockScreenOverlayEnabled' 0
    Set-Reg $CDM 'RotatingLockScreenEnabled' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\UserProfileEngagement' 'ScoobeSystemSettingEnabled' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\SystemSettings\AccountNotifications' 'EnableAccountNotifications' 0
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Mobility' 'OptedIn' 0
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableSoftLanding' 1
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableCloudOptimizedContent' 1
    Set-Reg 'HKCU\Software\Policies\Microsoft\Windows\CloudContent' 'DisableWindowsSpotlightFeatures' 1
    Set-Reg 'HKCU\Software\Policies\Microsoft\Windows\CloudContent' 'DisableSpotlightCollectionOnDesktop' 1
    Set-Reg 'HKCU\Software\Policies\Microsoft\Windows\CloudContent' 'DisableThirdPartySuggestions' 1
    # Sticky/Filter/Toggle Keys pop-ups from pressing Shift five times.
    Set-Reg 'HKCU\Control Panel\Accessibility\StickyKeys' 'Flags' '506' 'String'
    Set-Reg 'HKCU\Control Panel\Accessibility\Keyboard Response' 'Flags' '122' 'String'
    Set-Reg 'HKCU\Control Panel\Accessibility\ToggleKeys' 'Flags' '58' 'String'
    # Snappier menus and startup apps.
    Set-Reg 'HKCU\Control Panel\Desktop' 'MenuShowDelay' '100' 'String'
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize' 'StartupDelayInMSec' 0
    # Fast Startup half-hibernates Windows, which locks the disk for Linux and skips updates.
    Set-Reg 'HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power' 'HiberbootEnabled' 0
    # Game DVR background recording costs FPS even when unused.
    Set-Reg 'HKCU\System\GameConfigStore' 'GameDVR_Enabled' 0
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\GameDVR' 'AllowGameDVR' 0
}

function Invoke-Edge {
    $edge = 'HKLM\SOFTWARE\Policies\Microsoft\Edge'
    $off = @('StartupBoostEnabled', 'BackgroundModeEnabled', 'EdgeShoppingAssistantEnabled', 'HubsSidebarEnabled',
        'PersonalizationReportingEnabled', 'ShowRecommendationsEnabled', 'SpotlightExperiencesAndRecommendationsEnabled',
        'UserFeedbackAllowed', 'NewTabPageContentEnabled', 'AlternateErrorPagesEnabled',
        'ShowMicrosoftRewards', 'EdgeFollowEnabled', 'EdgeCollectionsEnabled', 'DiagnosticData', 'SearchSuggestEnabled',
        'ResolveNavigationErrorsUseWebService', 'PromotionalTabsEnabled', 'WalletDonationEnabled', 'EdgeWalletCheckoutEnabled',
        'ShowAcrobatSubscriptionButton', 'TabServicesEnabled', 'QuickSearchShowMiniMenu', 'TextPredictionEnabled')
    foreach ($name in $off) { Set-Reg $edge $name 0 }
    Set-Reg $edge 'NewTabPageHideDefaultTopSites' 1
    Set-Reg $edge 'HideFirstRunExperience' 1
    Set-Reg $edge 'ConfigureDoNotTrack' 1
    Set-Reg $edge 'TrackingPrevention' 2      # balanced; strict (3) breaks some sites
    Set-Reg $edge 'DefaultBrowserSettingEnabled' 0
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\EdgeUpdate' 'CreateDesktopShortcutDefault' 0
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\EdgeUI' 'DisableMFUTracking' 1
}

function Invoke-OneDrive {
    if ($KeepOneDrive) { Write-Host '  kept (-KeepOneDrive)'; return }
    $setup = @("$env:SystemRoot\System32\OneDriveSetup.exe", "$env:SystemRoot\SysWOW64\OneDriveSetup.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
    $installed = (Test-Path "$env:LOCALAPPDATA\Microsoft\OneDrive\OneDrive.exe") -or
        (Get-AppxPackage -Name 'Microsoft.OneDriveSync' -ErrorAction SilentlyContinue)
    if ($installed) {
        Write-Change 'uninstall OneDrive (files in your OneDrive folder stay on disk)'
        if (-not $DryRun) {
            Get-Process OneDrive -ErrorAction SilentlyContinue | Stop-Process -Force
            if ($setup) { Start-Process $setup '/uninstall' -Wait -NoNewWindow }
            winget uninstall --id Microsoft.OneDrive --silent --accept-source-agreements 2>$null | Out-Null
        }
    }
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\OneDrive' 'DisableFileSyncNGSC' 1
    Set-Reg 'HKCU\Software\Classes\CLSID\{018D5C66-4533-4307-9B53-224DE2ED1FE6}' 'System.IsPinnedToNameSpaceTree' 0 # gitleaks:allow
    $run = 'Registry::HKCU\Software\Microsoft\Windows\CurrentVersion\Run'
    if ((Get-Item $run).GetValueNames() -contains 'OneDrive' -and -not $DryRun) {
        Remove-ItemProperty $run -Name 'OneDrive' -ErrorAction SilentlyContinue
    }
}

function Invoke-Xbox {
    if ($KeepXbox) { Write-Host '  kept (-KeepXbox)'; return }
    Remove-Appx @('Microsoft.XboxApp', 'Microsoft.GamingApp', 'Microsoft.XboxGamingOverlay', 'Microsoft.XboxGameOverlay',
        'Microsoft.XboxSpeechToTextOverlay', 'Microsoft.Xbox.TCUI', 'Microsoft.XboxIdentityProvider')
    foreach ($svc in 'XblAuthManager', 'XblGameSave', 'XboxNetApiSvc', 'XboxGipSvc') { Disable-Svc $svc 'Manual' }
    Set-Reg 'HKCU\Software\Microsoft\GameBar' 'UseNexusForGameBarEnabled' 0
    Set-Reg 'HKCU\Software\Microsoft\GameBar' 'AutoGameModeEnabled' 1
    # Without the Game Bar, Win+G and controller Xbox buttons would show "ms-gamingoverlay" errors.
    Set-Reg 'HKCU\Software\Classes\ms-gamingoverlay' 'NoOpenWith' '' 'String'
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR' 'AppCaptureEnabled' 0
}

function Invoke-Security {
    # Microsoft Defender (skipped when another antivirus has taken over).
    $mp = Get-MpComputerStatus -ErrorAction SilentlyContinue
    if ($mp -and $mp.AntivirusEnabled) {
        $pref = Get-MpPreference
        if ($pref.PUAProtection -ne 1) { Write-Change 'Defender: block potentially unwanted apps'; if (-not $DryRun) { Set-MpPreference -PUAProtection Enabled } }
        if ($pref.EnableNetworkProtection -ne 1) { Write-Change 'Defender: network protection on'; if (-not $DryRun) { Set-MpPreference -EnableNetworkProtection Enabled } }
        if ($pref.MAPSReporting -eq 0) { Write-Change 'Defender: cloud protection on'; if (-not $DryRun) { Set-MpPreference -MAPSReporting Advanced } }
        # Attack surface reduction rules in block mode: the low-false-positive set.
        $asr = @{
            '56a863a9-875e-4185-98a7-b882c64b5ce5' = 'abuse of vulnerable signed drivers' # gitleaks:allow
            '9e6c4e1f-7d60-472f-ba1a-a39ef669e4b2' = 'credential stealing from LSASS' # gitleaks:allow
            'e6db77e5-3df2-4cf1-b95a-636979351e5b' = 'persistence through WMI event subscriptions' # gitleaks:allow
            'be9ba2d9-53ea-4cdc-84e5-9b1eeee46550' = 'executables from email' # gitleaks:allow
            'd3e037e1-3eb8-44c8-a917-57927947596d' = 'scripts launching downloaded executables' # gitleaks:allow
            'd4f940ab-401b-4efc-aadc-ad5f3c50688a' = 'Office apps creating child processes' # gitleaks:allow
            '75668c1f-73b5-4cf0-bb93-3ecf5cb7cc84' = 'Office apps injecting into other processes' # gitleaks:allow
            '3b576869-a4ec-4529-8536-b80a7769e899' = 'Office apps creating executables' # gitleaks:allow
            '92e97fa1-2edf-4476-bdd6-9dd0b4dddc7b' = 'Win32 API calls from Office macros' # gitleaks:allow
            '26190899-1602-49e8-8b27-eb1d0a1ce869' = 'Office communication apps creating child processes' # gitleaks:allow
            '7674ba52-37eb-4a4f-a9a1-f0f9a1619a2c' = 'Adobe Reader creating child processes' # gitleaks:allow
            'b2b3f03d-6a65-4f7b-a9c7-1c7ef74a9ba4' = 'untrusted unsigned programs from USB' # gitleaks:allow
        }
        $current = @{}
        $ids = @($pref.AttackSurfaceReductionRules_Ids); $actions = @($pref.AttackSurfaceReductionRules_Actions)
        for ($i = 0; $i -lt $ids.Count; $i++) { if ($ids[$i]) { $current[$ids[$i].ToLower()] = $actions[$i] } }
        foreach ($id in $asr.Keys) {
            if ($current[$id] -ne 1) {
                Write-Change "Defender ASR: block $($asr[$id])"
                if (-not $DryRun) { Add-MpPreference -AttackSurfaceReductionRules_Ids $id -AttackSurfaceReductionRules_Actions Enabled }
            }
        }
    } else {
        Add-Note 'Defender is not the active antivirus; its settings were skipped.'
    }

    # Old protocols and name resolution that leak credentials on hostile networks.
    Disable-Feature 'SMB1Protocol'
    Disable-Feature 'MicrosoftWindowsPowerShellV2Root'
    Disable-Feature 'MicrosoftWindowsPowerShellV2'
    Set-Reg 'HKLM\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters' 'SMB1' 0
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient' 'EnableMulticast' 0  # LLMNR
    Set-Reg 'HKLM\SYSTEM\CurrentControlSet\Services\NetBT\Parameters' 'NodeType' 2      # no NetBIOS broadcasts
    Get-ChildItem 'Registry::HKLM\SYSTEM\CurrentControlSet\Services\NetBT\Parameters\Interfaces' -ErrorAction SilentlyContinue |
        ForEach-Object { Set-Reg ($_.Name) 'NetbiosOptions' 2 }
    Set-Reg 'HKLM\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters' 'RequireSecuritySignature' 1
    Set-Reg 'HKLM\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters' 'RequireSecuritySignature' 1
    $lsa = 'HKLM\SYSTEM\CurrentControlSet\Control\Lsa'
    Set-Reg $lsa 'LmCompatibilityLevel' 5   # NTLMv2 only
    Set-Reg $lsa 'NoLMHash' 1
    Set-Reg $lsa 'RestrictAnonymous' 1
    Set-Reg $lsa 'RestrictAnonymousSAM' 1
    Set-Reg $lsa 'EveryoneIncludesAnonymous' 0
    Set-Reg $lsa 'RunAsPPL' 1               # LSA protection against credential dumping
    Set-Reg 'HKLM\SYSTEM\CurrentControlSet\Control\SecurityProviders\WDigest' 'UseLogonCredential' 0
    Set-Reg 'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' 'LocalAccountTokenFilterPolicy' 0
    # UAC: always ask, on the secure desktop.
    $uac = 'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
    Set-Reg $uac 'EnableLUA' 1
    Set-Reg $uac 'ConsentPromptBehaviorAdmin' 2
    Set-Reg $uac 'PromptOnSecureDesktop' 1
    # No AutoRun/AutoPlay from USB sticks and discs.
    Set-Reg 'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer' 'NoDriveTypeAutoRun' 255
    Set-Reg 'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer' 'NoAutorun' 1
    Set-Reg 'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\AutoplayHandlers' 'DisableAutoplay' 1
    # Remote Assistance off; RDP (if someone turns it on) needs Network Level Authentication.
    Set-Reg 'HKLM\SYSTEM\CurrentControlSet\Control\Remote Assistance' 'fAllowToGetHelp' 0
    Set-Reg 'HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' 'UserAuthentication' 1
    # .hta/.vbs/.js double-clicks open Notepad instead of running (a classic phishing payload).
    foreach ($ext in 'hta', 'js', 'jse', 'vbs', 'vbe', 'wsf', 'wsh') {
        Set-Reg "HKCU\Software\Classes\.$ext" '(Default)' 'txtfile' 'String'
    }
    Disable-Svc 'SSDPSRV' 'Manual'   # UPnP device discovery
    Disable-Svc 'upnphost' 'Manual'
    Disable-Svc 'SharedAccess'       # Internet Connection Sharing
    $profiles = Get-NetFirewallProfile | Where-Object { -not $_.Enabled }
    if ($profiles) {
        Write-Change "firewall on for $($profiles.Name -join ', ')"
        if (-not $DryRun) { Set-NetFirewallProfile -All -Enabled True }
    }
    $bitlocker = Get-BitLockerVolume -MountPoint $env:SystemDrive -ErrorAction SilentlyContinue
    if ($bitlocker -and $bitlocker.ProtectionStatus -ne 'On') {
        Add-Note "BitLocker is off on $($env:SystemDrive). Turn it on in Settings > Privacy & security > Device encryption (save the recovery key)."
    }
    Add-Note 'Memory integrity (Core isolation) is worth turning on in Windows Security if your drivers and games allow it.'
}

function Invoke-Updates {
    $au = 'HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
    Set-Reg $au 'NoAutoRebootWithLoggedOnUsers' 1
    Set-Reg 'HKLM\SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization' 'DODownloadMode' 0  # no P2P sharing
    Set-Reg 'HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings' 'RestartNotificationsAllowed2' 1
    # Updates for other Microsoft products (Office, .NET) through Windows Update.
    Set-Reg 'HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings' 'AllowMUUpdateService' 1
}

function Invoke-Cleanup {
    $targets = @($env:TEMP, "$env:SystemRoot\Temp", "$env:SystemRoot\SoftwareDistribution\Download") | Where-Object { Test-Path $_ }
    foreach ($dir in $targets) {
        $old = @(Get-ChildItem $dir -Force -ErrorAction SilentlyContinue | Where-Object LastWriteTime -LT (Get-Date).AddDays(-1))
        if ($old) {
            Write-Change "delete $($old.Count) old item(s) in $dir"
            if (-not $DryRun) { $old | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue }
        }
    }
    Write-Change 'clear the Delivery Optimization cache'
    if (-not $DryRun) { Delete-DeliveryOptimizationCache -Force -ErrorAction SilentlyContinue }
    Write-Change 'clean up superseded Windows components (DISM, takes a few minutes)'
    if (-not $DryRun) { Dism.exe /Online /Cleanup-Image /StartComponentCleanup /Quiet | Out-Null }
}

# --- Run -----------------------------------------------------------------------------
$sections = [ordered]@{
    apps = 'Invoke-Apps'; privacy = 'Invoke-Privacy'; ai = 'Invoke-AI'; start = 'Invoke-Start'
    taskbar = 'Invoke-Taskbar'; explorer = 'Invoke-Explorer'; ui = 'Invoke-UI'; edge = 'Invoke-Edge'
    onedrive = 'Invoke-OneDrive'; xbox = 'Invoke-Xbox'; security = 'Invoke-Security'
    updates = 'Invoke-Updates'; cleanup = 'Invoke-Cleanup'
}
$selected = $sections.Keys | Where-Object { (-not $Only -or $Only -contains $_) -and $Skip -notcontains $_ }

$mode = if ($DryRun) { 'dry run: nothing changes' } else { 'applying' }
Write-Host "Windows hardening ($mode) - $((Get-CimInstance Win32_OperatingSystem).Caption) build $Build" -ForegroundColor Cyan

if (-not $DryRun -and -not $NoRestorePoint) {
    Write-Host 'Creating a System Restore point...' -ForegroundColor Cyan
    try {
        Enable-ComputerRestore -Drive "$env:SystemDrive\" -ErrorAction SilentlyContinue
        # Windows allows one restore point per 24 h unless this is 0.
        New-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore' -Name 'SystemRestorePointCreationFrequency' -Value 0 -PropertyType DWord -Force | Out-Null
        Checkpoint-Computer -Description 'Before dotfiles harden.ps1' -RestorePointType MODIFY_SETTINGS
    } catch {
        Write-Warning "No restore point ($($_.Exception.Message)). Stop now (Ctrl+C) if you want one; continuing in 10 s."
        Start-Sleep -Seconds 10
    }
}

try {
    foreach ($name in $selected) {
        Write-Section $name
        $before = $script:Changes
        & $sections[$name]
        if ($script:Changes -eq $before) { Write-Host '  nothing to change' -ForegroundColor DarkGray }
    }
} finally {
    if (-not $DryRun -and $script:Undo.Count) {
        New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
        $undoFile = Join-Path $StateDir ("harden-undo-{0:yyyyMMdd-HHmmss}.json" -f (Get-Date))
        $script:Undo | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $undoFile
        Write-Host "`nUndo file: $undoFile (.\windows\harden.ps1 -Restore <file>)" -ForegroundColor Cyan
    }
}

if (-not $DryRun -and ($selected -contains 'taskbar' -or $selected -contains 'explorer' -or $selected -contains 'start')) {
    Get-Process explorer -ErrorAction SilentlyContinue | Stop-Process -Force  # restarts by itself
}
foreach ($note in $script:Notes) { Write-Host "note: $note" -ForegroundColor DarkCyan }
if ($DryRun) {
    Write-Host "`n$($script:Changes) change(s) listed. Run without -DryRun to apply them." -ForegroundColor Green
} else {
    Write-Host "`nDone: $($script:Changes) change(s). Restart Windows to apply everything." -ForegroundColor Green
}
