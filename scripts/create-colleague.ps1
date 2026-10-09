param([string]$Username, [string]$EnvFile = '.env.oracle')
$ErrorActionPreference = 'Stop'
if (-not $Username) { $Username = Read-Host 'Colleague Aegis username' }
$taskSecurePassword = Read-Host 'Colleague Aegis password (12–200 characters)' -AsSecureString
$taskPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($taskSecurePassword)
Push-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
try {
    $taskPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($taskPointer)
    $taskPayload = @{ username = $Username; password = $taskPassword } | ConvertTo-Json -Compress
    $taskPayload | & docker compose --env-file $EnvFile -f compose.oracle.yaml exec -T api python -m app.provision_account
    if ($LASTEXITCODE -ne 0) { throw 'Account provisioning did not complete. Existing accounts were not changed.' }
} finally {
    $taskPassword = $null; $taskPayload = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($taskPointer)
    $taskSecurePassword.Dispose()
    Pop-Location
}
