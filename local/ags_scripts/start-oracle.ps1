param([string]$EnvFile = '.env.oracle', [string]$SecretDirectory = 'secrets/oracle', [int]$Port = 3003,
    [ValidateSet('Auto', 'Cpu', 'Gpu')][string]$Hardware = 'Auto', [switch]$Gpu)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location -LiteralPath $taskRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install Docker Desktop with Linux containers, then rerun this script.' }
    & docker info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop, then rerun this script.' }
    & docker run --rm --mount "type=bind,source=$taskRoot,target=/workspace" python:3.12-slim python /workspace/local/ags_scripts/setup_oracle.py --env-file $EnvFile --secret-dir $SecretDirectory --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Private configuration setup failed.' }
    $taskCompose = @('compose', '--project-directory', $taskRoot, '--env-file', $EnvFile, '-f', 'local/compose.oracle.yaml')
    . "$PSScriptRoot/model-hardware.ps1"
    $taskBaseCompose = $taskCompose.Clone()
    $taskImage = (& docker @taskCompose config --format json | ConvertFrom-Json).services.ollama.image
    if ($LASTEXITCODE -ne 0) { throw 'Oracle Compose configuration is invalid.' }
    & docker image inspect $taskImage *> $null
    if ($LASTEXITCODE -ne 0) {
        & docker pull $taskImage
        if ($LASTEXITCODE -ne 0) { throw 'Ollama image download failed.' }
    }
    if ($Gpu) { $Hardware = 'Gpu' }
    $taskHardware = Resolve-AegisHardware -Mode $Hardware -Probe { Test-AegisContainerGpu -Image $taskImage }
    Write-Host "Model hardware: $taskHardware (container device probe; actual inference verified below)."
    if ($taskHardware -eq 'Gpu') { $taskCompose += @('-f', 'local/compose.gpu.yaml') }
    & docker @taskCompose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Oracle Compose configuration is invalid.' }
    & docker @taskCompose up --build -d --wait --wait-timeout 1200
    if ($LASTEXITCODE -ne 0) {
        if ($Hardware -eq 'Auto' -and $taskHardware -eq 'Gpu') {
            Write-Host 'GPU startup failed; retrying the CPU configuration with the same data volumes.'
            $taskCompose = $taskBaseCompose
            $taskHardware = 'Cpu'
            & docker @taskCompose up --build -d --wait --wait-timeout 1200
        }
        if ($LASTEXITCODE -ne 0) { throw 'Container startup failed. Inspect docker compose logs using the same env file and Compose file.' }
    }
    $taskConfig = Get-Content -LiteralPath $EnvFile
    if ($taskConfig -contains 'MODEL_PROVIDER=ollama') {
        foreach ($taskKey in @('AEGIS_MODEL', 'EMBEDDING_MODEL', 'AEGIS_OCR_MODEL')) {
            if ($taskKey -eq 'AEGIS_OCR_MODEL' -and $taskConfig -contains 'AEGIS_OCR_ENABLED=false') { continue }
            $taskLine = $taskConfig | Where-Object { $_.StartsWith("$taskKey=") } | Select-Object -First 1
            if (-not $taskLine -and $taskKey -eq 'AEGIS_OCR_MODEL') { $taskLine = 'AEGIS_OCR_MODEL=qwen2.5vl:3b' }; if (-not $taskLine) { throw "Missing $taskKey in configuration." }
            $taskModel = $taskLine.Split('=', 2)[1]
            & docker @taskCompose exec -T ollama ollama pull $taskModel
            if ($LASTEXITCODE -ne 0) { throw 'Model download failed. Rerun the script to retry; saved data is preserved.' }
        }
        & docker @taskCompose exec -T api python -m ags_app.container_smoke
        if ($LASTEXITCODE -ne 0 -and $Hardware -eq 'Auto' -and $taskHardware -eq 'Gpu') {
            Write-Host 'GPU inference smoke test failed; checking CPU with the same installed models and volumes.'
            $taskCompose = $taskBaseCompose
            & docker @taskCompose up -d --no-deps --wait --wait-timeout 300 ollama
            if ($LASTEXITCODE -ne 0) { throw 'CPU fallback container did not become healthy.' }
            & docker @taskCompose exec -T api python -m ags_app.ocr_smoke
        & docker @taskCompose exec -T api python -m ags_app.container_smoke
        }
        if ($LASTEXITCODE -ne 0) { throw 'Model smoke test failed; containers and saved data are preserved. Inspect the error and retry.' }
    }
    Write-Host 'Oracle containers are ready. Open the configured Aegis URL (default http://localhost:3003).'
    Write-Host 'To create a colleague login, run ./local/ags_scripts/create-colleague.ps1.'
} finally { Pop-Location }
