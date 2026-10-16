#Requires -Version 5.1
# Run from an open PowerShell window. No credentials are stored here.
[CmdletBinding()]
param([string]$Inputs, [switch]$CommittedSource)
$ErrorActionPreference = 'Stop'
$aegisRepository = Split-Path -Parent $PSScriptRoot
$aegisLauncher = Join-Path $aegisRepository 'ags_deploy\deploy.ps1'
if (-not $Inputs) { $Inputs = Join-Path $PSScriptRoot 'aegis-oci-inputs.json' }
# Resolve relative input paths before changing to the repository directory.
$aegisInputs = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Inputs)
try {
    if (-not (Test-Path -LiteralPath $aegisLauncher -PathType Leaf)) { throw "Deployment script not found: $aegisLauncher" }
    if (-not (Test-Path -LiteralPath $aegisInputs -PathType Leaf)) { throw "Target inputs not found: $aegisInputs" }
    Write-Host 'READ-ONLY PREFLIGHT: type CONNECT when prompted. Nothing will be deployed.'
    Write-Host ('Selected destination inputs: ' + $aegisInputs)
    Push-Location -LiteralPath $aegisRepository
    try {
        & $aegisLauncher -Inputs $aegisInputs -CommittedSource:$CommittedSource -CheckOnly
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-Host ('Stopped: ' + $_.Exception.Message) -ForegroundColor Red
    throw
}
finally {
    if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        Read-Host 'Press Enter to finish' | Out-Null
    }
}