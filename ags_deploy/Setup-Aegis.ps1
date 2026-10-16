#Requires -Version 5.1
<#
.SYNOPSIS
Install missing Windows deployment tools and check the selected Aegis target.
.DESCRIPTION
Run before Deploy-Aegis.ps1. Uses the adjacent private JSON by default. Installs
missing workstation tools; installer/UAC prompts and a Windows restart may need
operator action. CONNECT still controls remote preflight; credentials are entered
privately. Creates no OCI infrastructure and never builds or publishes images.
-CheckOnly checks existing tools without installs, Docker startup or registry login.
#>
[CmdletBinding()]
param([string]$Inputs, [switch]$CheckOnly, [switch]$CommittedSource)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Setup-Aegis.ps1 is for Windows PowerShell workstations.' }
if (-not $Inputs) { $Inputs = Join-Path $PSScriptRoot 'aegis-oci-inputs.json' }
$Inputs = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Inputs)
. (Join-Path $PSScriptRoot 'scripts\deployment-environment.ps1')
. (Join-Path $PSScriptRoot 'scripts\setup-prerequisites.ps1')
try {
    $result = Invoke-AegisPrerequisites -DeploymentRoot $PSScriptRoot -Inputs $Inputs -InstallMissing:(-not $CheckOnly) -CommittedSource:$CommittedSource
    Write-Host ''
    Write-Host 'AEGIS_PREREQUISITES_READY' -ForegroundColor Green
    Write-Host ('Report: ' + $result.ReportPath)
    $nextLauncher = (Join-Path $PSScriptRoot 'Deploy-Aegis.ps1').Replace("'", "''")
    $nextInputs = $Inputs.Replace("'", "''")
    Write-Host 'Next command for the same destination (normal release approvals still apply):'
    $nextCommand = "& '" + $nextLauncher + "' -Inputs '" + $nextInputs + "'"
    if ($CommittedSource) { $nextCommand += ' -CommittedSource' }
    Write-Host $nextCommand
}
catch {
    Write-Host ('Prerequisite setup stopped: ' + $_.Exception.Message) -ForegroundColor Red
    throw
}
finally {
    if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        Read-Host 'Press Enter to finish' | Out-Null
    }
}
