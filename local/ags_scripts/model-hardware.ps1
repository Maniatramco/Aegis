function Resolve-AegisHardware {
    param([ValidateSet('Auto', 'Cpu', 'Gpu')][string]$Mode = 'Auto', [scriptblock]$Probe)
    if ($Mode -eq 'Cpu') { return 'Cpu' }
    $available = & $Probe
    if ($available) { return 'Gpu' }
    if ($Mode -eq 'Gpu') { throw 'GPU mode requested, but Docker cannot access a supported NVIDIA GPU. Use Auto or Cpu.' }
    return 'Cpu'
}

function Test-AegisContainerGpu {
    param([string]$Image)
    # Host nvidia-smi is insufficient: test actual device access inside our image.
    & docker run --rm --gpus all --entrypoint nvidia-smi $Image --query-gpu=name --format=csv,noheader *> $null
    return ($LASTEXITCODE -eq 0)
}
