param([switch]$Once)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$taskRuntime = Join-Path $taskRoot 'ags_runtime\ags_oke'
$taskRelay = Get-Content -LiteralPath (Join-Path $taskRuntime 'relay-connection.json') -Raw | ConvertFrom-Json
$taskPrivateKey = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.oci\aegis-hosting\aegis-web-ed25519'
$taskKnownHosts = Join-Path $taskRuntime 'known_hosts'
$taskStopFlag = Join-Path $taskRuntime 'stop-model-relay'
$taskArguments = @('-N', '-i', $taskPrivateKey, '-p', '32022', '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=yes', '-o', "UserKnownHostsFile=$taskKnownHosts",
    '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15',
    '-o', 'ServerAliveCountMax=3', '-o', 'ConnectTimeout=10', '-o', 'LogLevel=ERROR',
    '-R', '0.0.0.0:11434:127.0.0.1:11436', "relay@$($taskRelay.node_ip)")
do {
    if (Test-Path -LiteralPath $taskStopFlag) { break }
    & ssh.exe @taskArguments
    if ($Once) { break }
    Write-Output "$(Get-Date -Format o) Model relay disconnected; reconnecting."
    Start-Sleep -Seconds 5
} while (-not (Test-Path -LiteralPath $taskStopFlag))
