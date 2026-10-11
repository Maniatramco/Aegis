param([ValidateSet('Auto','Cpu','Gpu')][string]$Hardware = 'Auto', [string]$OutputPath = 'work/kubernetes-rendered.yaml')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) { throw 'Install kubectl before rendering Kubernetes manifests.' }
    $taskSelected = 'Cpu'
    if ($Hardware -ne 'Cpu') {
        # Kubernetes must allocate the GPU before starting a container. A laptop GPU
        # is irrelevant here. Auto checks Ready nodes and already allocated GPUs.
        $taskNodesRaw = & kubectl get nodes -o json 2>$null
        $taskNodesOk = $LASTEXITCODE -eq 0
        $taskPodsRaw = & kubectl get pods --all-namespaces -o json 2>$null
        $taskPodsOk = $LASTEXITCODE -eq 0
        if ($taskNodesOk -and $taskPodsOk) {
            $taskNodes = ($taskNodesRaw | ConvertFrom-Json).items
            $taskPods = ($taskPodsRaw | ConvertFrom-Json).items
            foreach ($taskNode in $taskNodes) {
                if ($taskNode.spec.unschedulable) { continue }
                if (-not ($taskNode.status.conditions | Where-Object { $_.type -eq 'Ready' -and $_.status -eq 'True' })) { continue }
                if ($taskNode.spec.taints | Where-Object { $_.effect -in @('NoSchedule','NoExecute') }) { continue }
                $taskCapacity = [int]$taskNode.status.allocatable.'nvidia.com/gpu'
                $taskUsed = 0
                foreach ($taskPod in $taskPods | Where-Object { $_.spec.nodeName -eq $taskNode.metadata.name -and $_.status.phase -notin @('Succeeded','Failed') }) {
                    $taskRegular = 0; $taskInit = 0
                    foreach ($taskContainer in $taskPod.spec.containers) { $taskRegular += [int]$taskContainer.resources.limits.'nvidia.com/gpu' }
                    foreach ($taskContainer in $taskPod.spec.initContainers) { $taskInit = [Math]::Max($taskInit, [int]$taskContainer.resources.limits.'nvidia.com/gpu') }
                    $taskUsed += [Math]::Max($taskRegular, $taskInit)
                }
                if ($taskCapacity - $taskUsed -ge 1) { $taskSelected = 'Gpu'; break }
            }
        } else { Write-Warning 'Cluster GPU inventory unavailable; Auto renders CPU. No cluster resources were changed.' }
        if ($Hardware -eq 'Gpu' -and $taskSelected -ne 'Gpu') { throw 'No usable untainted Ready node with a free NVIDIA GPU was verified. Use Cpu, or configure compatible GPU nodes/device plugins first.' }
    }
    $taskOverlay = if ($taskSelected -eq 'Gpu') { 'deploy/kubernetes/gpu' } else { 'deploy/kubernetes/base' }
    $taskRendered = & kubectl kustomize $taskOverlay
    if ($LASTEXITCODE -ne 0) { throw 'Kubernetes rendering failed.' }
    $taskTarget = [IO.Path]::GetFullPath($OutputPath, $taskRoot)
    [IO.Directory]::CreateDirectory((Split-Path -Parent $taskTarget)) | Out-Null
    [IO.File]::WriteAllText($taskTarget, ($taskRendered -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
    Write-Host "Rendered $taskSelected manifests: $taskTarget. Nothing was deployed. Capacity can change; verify model smoke output after deployment."
} finally { Pop-Location }
