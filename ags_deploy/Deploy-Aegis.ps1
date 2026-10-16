#Requires -Version 5.1
# Run from an open PowerShell window. No credentials are stored here.
$ErrorActionPreference = 'Stop'
$aegisRepository = Split-Path -Parent $PSScriptRoot
$aegisLauncher = Join-Path $aegisRepository 'ags_deploy\deploy.ps1'
$aegisInputs = Join-Path $aegisRepository 'ags_deploy\aegis-oci-inputs.json'
try {
    if (-not (Test-Path -LiteralPath $aegisLauncher -PathType Leaf)) { throw "Deployment script not found: $aegisLauncher" }
    if (-not (Test-Path -LiteralPath $aegisInputs -PathType Leaf)) { throw "Target inputs not found: $aegisInputs" }
    Write-Host 'DEPLOYMENT: type CONNECT for preflight, then review the plan before typing PUBLISH.'
    Push-Location -LiteralPath $aegisRepository
    try {
        & $aegisLauncher -Inputs $aegisInputs
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