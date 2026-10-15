# Aegis daily stop and start

For the OCI Console click-by-click procedure, use [Aegis stop and start through the OCI portal](AEGIS_PORTAL_STOP_START.md). That procedure stops the worker VM; the commands below pause application Pods while leaving the VM running. Use one method consistently for each daily stop/start cycle.

Use these commands in the **PowerShell terminal in VS Code on your laptop**. They pause or resume the existing OCI WebUI, FastAPI and worker. Your database, documents, Parquet results, vectors, wallet and configuration remain in place. No resources are deleted or upgraded.

Application: https://aegis.92.4.67.183.sslip.io/

## Stop at the end of the day

Ask other users to finish their work first. Wait for uploads, indexing, extraction and re-extraction to finish. Copy this entire block into PowerShell. It refuses to stop if processing jobs are still queued or running.

```powershell
Set-Location -LiteralPath 'C:\Users\Laya\Documents\Codex\2026-10-09\new-chat\Aegis'
$ErrorActionPreference = 'Stop'
$taskKube = 'ags_runtime/ags_oke/kubeconfig.yaml'

# Check the shared processing queue before stopping its worker.
$taskCount = & kubectl --kubeconfig $taskKube -n aegis-oci exec deployment/aegis-api-worker -c api -- python -c "from ags_app.core import Session,Job; from sqlalchemy import select,func; s=Session(); print(s.scalar(select(func.count()).select_from(Job).where(Job.status.in_(['queued','running'])))); s.close()"
if ($LASTEXITCODE -ne 0) { throw 'Cannot check jobs. Stop here and check the service status.' }
if ([int]($taskCount | Select-Object -Last 1) -ne 0) { throw 'Jobs are still active. Wait for them to finish, then run this block again.' }

# Prevent the laptop tunnel from reconnecting after the cloud Pod stops.
Set-Content -LiteralPath 'ags_runtime/ags_oke/stop-model-relay' -Value 'Daily manual pause'

& kubectl --kubeconfig $taskKube -n aegis-oci scale deployment/aegis-api-worker --replicas=0
if ($LASTEXITCODE -ne 0) { throw 'API/worker pause failed. Check kubectl output.' }
& kubectl --kubeconfig $taskKube -n aegis-oci wait --for=delete pod -l app=aegis-api-worker --timeout=180s
if ($LASTEXITCODE -ne 0) { throw 'API/worker has not stopped yet. Check its Pod before closing Docker.' }

# Remember the API pause for future manifest rendering.
$taskStatePath = Join-Path (Get-Location).Path 'ags_runtime/ags_oke/provision-state.json'
$taskState = Get-Content -LiteralPath $taskStatePath -Raw | ConvertFrom-Json
$taskState.application_paused = $true
[System.IO.File]::WriteAllText($taskStatePath, ($taskState | ConvertTo-Json -Depth 30), [System.Text.UTF8Encoding]::new($false))

& kubectl --kubeconfig $taskKube -n aegis-oci scale deployment/aegis-web --replicas=0
if ($LASTEXITCODE -ne 0) { throw 'WebUI pause failed. Check kubectl output.' }
& kubectl --kubeconfig $taskKube -n aegis-oci wait --for=delete pod -l app=aegis-web --timeout=180s
if ($LASTEXITCODE -ne 0) { throw 'WebUI has not stopped yet. Check its Pod.' }

& kubectl --kubeconfig $taskKube -n aegis-oci get deployments,pods
```

Success means both Deployments show **0 desired replicas**, and no `aegis-web` or `aegis-api-worker` Pods remain. The website will be unavailable while stopped. The tunnel disconnects when the API/worker Pod disappears; the stop flag prevents reconnection.

You may then stop the laptop AI container:

```powershell
docker stop aegis-oracle-ollama-1
```

You can close Docker Desktop or shut down your laptop after the cloud Pods have stopped. Do not start the old laptop API or worker; the OCI app is the active installation.

If you run the stop block again after the API is already stopped, its first check will fail because there is no API Pod. Use the status command below to confirm both replica counts are zero instead.

Do not apply deployment manifests while paused: the current renderer preserves the API pause, but its WebUI default is one replica and would resume the WebUI.

## Start the next day

The inspected live datasets use Gemini; Docker Desktop and laptop Ollama are not required for those mappings. Run from the configured operator laptop with its existing kubeconfig. Copy the block below into PowerShell.

```powershell
Set-Location -LiteralPath 'C:\Users\Laya\Documents\Codex\2026-10-09\new-chat\Aegis'
$ErrorActionPreference = 'Stop'
$taskRoot = (Get-Location).Path
$taskRuntime = Join-Path $taskRoot 'ags_runtime/ags_oke'
$taskKube = Join-Path $taskRuntime 'kubeconfig.yaml'

$taskStatePath = Join-Path $taskRuntime 'provision-state.json'
$taskState = Get-Content -LiteralPath $taskStatePath -Raw | ConvertFrom-Json
$taskState.application_paused = $false
[System.IO.File]::WriteAllText($taskStatePath, ($taskState | ConvertTo-Json -Depth 30), [System.Text.UTF8Encoding]::new($false))

& kubectl --kubeconfig $taskKube -n aegis-oci scale deployment/aegis-api-worker --replicas=1
if ($LASTEXITCODE -ne 0) { throw 'API/worker start failed. Check kubectl output.' }
& kubectl --kubeconfig $taskKube -n aegis-oci scale deployment/aegis-web --replicas=1
if ($LASTEXITCODE -ne 0) { throw 'WebUI start failed. Check kubectl output.' }

& kubectl --kubeconfig $taskKube -n aegis-oci rollout status deployment/aegis-api-worker --timeout=300s
if ($LASTEXITCODE -ne 0) { throw 'API is still starting or has failed. Check status and logs below.' }
& kubectl --kubeconfig $taskKube -n aegis-oci rollout status deployment/aegis-web --timeout=180s
if ($LASTEXITCODE -ne 0) { throw 'WebUI is still starting or has failed. Check status and logs below.' }
& kubectl --kubeconfig $taskKube -n aegis-oci get deployments,pods
```

Allow time for both deployments to become ready. Success means `aegis-api-worker` is **3/3 Running**, `aegis-web` is **2/2 Running**, and both Deployments are **1/1 Ready**. Open the application URL and sign in.

## Check status or troubleshoot

Run from the same project folder:

```powershell
kubectl --kubeconfig ags_runtime/ags_oke/kubeconfig.yaml -n aegis-oci get deployments,pods
kubectl --kubeconfig ags_runtime/ags_oke/kubeconfig.yaml -n aegis-oci logs deployment/aegis-api-worker -c api --tail=30
```

The retained laptop Ollama option needs its container and [existing relay launcher](../../local/ags_scripts/start-oke-model-relay.ps1) only when a dataset is deliberately mapped to it. Restore that optional relay separately if needed. The three active datasets inspected on 15 October 2026 use Gemini and the laptop container is stopped; see [live resources](../ags_architecture/OCI-LIVE-RESOURCES.md).

## What stopping saves

Pausing the application stops its background worker activity and application-generated storage requests. It **does not stop the OKE node or release the load balancer, disks, bucket, registry or database**. Allocated resources can still consume allowances or trial credits according to their service pricing. This procedure does not promise zero overnight cost. [Oracle service pricing](https://www.oracle.com/cloud/price-list/).

Stopping a Standard Compute VM through the OCI Console/API is a separate operation that pauses its Compute billing; it does not remove its stored data or other allocated services. These daily commands leave the managed OKE node running and avoid terminating or resizing it. [Oracle billing for stopped instances](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resource-billing-stopped-instances.htm).

Your SGD 400 promotion is trial credit, not a permanent monthly allowance. Its recorded end is **11 November 2026 at approximately 05:30 IST**. No account upgrade is included in these instructions.

Prepared 14 October 2026; laptop prerequisites clarified against the 15 October live snapshot. Commands were checked against the existing deployment names, tunnel script and runtime paths. Their PowerShell syntax was validated without executing a shutdown; services remain running.
