param([string]$EnvFile = '.env.oracle', [string]$SecretDirectory = 'secrets/oracle', [int]$Port = 3003)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install Docker Desktop with Linux containers, then rerun this script.' }
    & docker info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop, then rerun this script.' }
    & docker run --rm --mount "type=bind,source=$taskRoot,target=/workspace" python:3.12-slim python /workspace/scripts/setup_oracle.py --env-file $EnvFile --secret-dir $SecretDirectory --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Private configuration setup failed.' }
    $taskCompose = @('compose', '--env-file', $EnvFile, '-f', 'compose.oracle.yaml')
    & docker @taskCompose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Oracle Compose configuration is invalid.' }
    & docker @taskCompose up --build -d --wait --wait-timeout 1200
    if ($LASTEXITCODE -ne 0) { throw 'Container startup failed. Inspect docker compose logs using the same env file and Compose file.' }
    $taskConfig = Get-Content -LiteralPath $EnvFile
    if ($taskConfig -contains 'MODEL_PROVIDER=ollama') {
        foreach ($taskKey in @('AEGIS_MODEL', 'EMBEDDING_MODEL')) {
            $taskLine = $taskConfig | Where-Object { $_.StartsWith("$taskKey=") } | Select-Object -First 1
            if (-not $taskLine) { throw "Missing $taskKey in configuration." }
            $taskModel = $taskLine.Split('=', 2)[1]
            & docker @taskCompose exec -T ollama ollama pull $taskModel
            if ($LASTEXITCODE -ne 0) { throw 'Model download failed. Rerun the script to retry; saved data is preserved.' }
        }
    }
    Write-Host 'Oracle containers are ready. Open the configured Aegis URL (default http://localhost:3003).'
    Write-Host 'To create a colleague login, run ./scripts/create-colleague.ps1.'
} finally { Pop-Location }
