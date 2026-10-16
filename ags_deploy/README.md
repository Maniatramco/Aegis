# Windows PowerShell deployment: two methods

Both methods use the same local Docker build and release workflow. Complete the **common setup** once, then choose **Method 1 or Method 2** for each release. Run commands one at a time and stop if a command reports an error.

| Method | Readiness check | Build and release |
| --- | --- | --- |
| **1. Main script directly** | `.\deploy.ps1 -CheckOnly` | `.\deploy.ps1` |
| **2. Shortcut scripts** | `.\Check-Aegis.ps1` | `.\Deploy-Aegis.ps1` |

All three scripts are in this `ags_deploy` folder. The shortcuts call the main script; you do not need to run all three scripts for one deployment.

## Common setup A: prerequisites

| Requirement | Purpose |
| --- | --- |
| Windows PowerShell 5.1 or newer | Runs the deployment scripts and interactive prompts. |
| Git | Exports the exact committed source selected in the JSON. |
| Python 3.12 recommended | Runs the deployment checks and workflow. |
| Docker Desktop using Linux containers | Builds and publishes the selected frontend/backend images. |
| kubectl and the destination kubeconfig | Reads and updates the existing Aegis workloads. |
| Existing OCI authentication and registry access | Authenticates to the selected target and private image registry. |
| Existing Aegis installation | Workloads, database, storage, Secrets, models and HTTPS routing must already be prepared. |
| Oracle Python driver, wallet and account access when `DB_Object` is `Y` | Supports the selected database object release. |

**On your already-configured laptop, reuse the installed tools and existing credentials.** Skip installation steps for tools that already work. Database-only releases do not require Docker or Kubernetes. The commands below install workstation tools; they do not provision OCI infrastructure.

## Common setup B: install missing workstation tools

Run these in PowerShell **only when the corresponding tool is missing**. Follow installer prompts. Close and reopen PowerShell after installation so its PATH is refreshed.

```powershell
winget --version
```

If `winget` is unavailable, install Microsoft's **App Installer** from the Microsoft Store first.

```powershell
winget install --id Git.Git --exact --source winget
winget install --id Python.Python.3.12 --exact --source winget
winget install --id Docker.DockerDesktop --exact --source winget
winget install --id Kubernetes.kubectl --exact --source winget
```

Package references: [Git installation](https://git-scm.com/install/windows), [Python WinGet package](https://github.com/microsoft/winget-pkgs/tree/master/manifests/p/Python/Python/3/12), [Docker WinGet package](https://github.com/microsoft/winget-pkgs/tree/master/manifests/d/Docker/DockerDesktop), and [kubectl installation](https://kubernetes.io/docs/tasks/tools/install-kubectl-windows/). Keep an existing tested kubectl installation; on a new machine choose a client version compatible with the destination cluster.

### If Docker requires WSL setup

Check WSL:

```powershell
wsl --version
```

If WSL is missing, run this in **PowerShell as Administrator**, then restart Windows if requested:

```powershell
wsl --install --no-distribution
```

If WSL is already installed but Docker requests an update, use this instead:

```powershell
wsl --update
```

Follow the [Docker Windows requirements](https://docs.docker.com/desktop/setup/install/windows-install/) and [Microsoft WSL instructions](https://learn.microsoft.com/en-us/windows/wsl/basic-commands) for your Windows version. This setup is needed only for the selected Docker backend.

### Verify the installed commands

In a newly opened PowerShell window:

```powershell
$PSVersionTable.PSVersion
git --version
py -3.12 --version
kubectl version --client
```

Stop and resolve a missing command before continuing. Do not upgrade working application dependencies as a deployment workaround.

## Common setup C: open the project and prepare Python

### Your existing checkout

```powershell
Set-Location "C:\Users\Laya\Documents\Codex\2026-10-09\new-chat\Aegis"
```

### On a new computer only

If you do not already have an Aegis checkout, clone into a new directory instead of overwriting an existing checkout:

```powershell
New-Item -ItemType Directory -Path "C:\AegisWork" -Force
Set-Location "C:\AegisWork"
git clone --branch ags_sprint1 https://github.com/Maniatramco/Aegis.git
Set-Location .\Aegis
```

For either checkout, continue from its **repository root**:

```powershell
$taskRepo = (Get-Location).Path
if (-not (Test-Path -LiteralPath .\.venv\Scripts\python.exe)) {
    py -3.12 -m venv .venv
}
.\.venv\Scripts\python.exe --version
git rev-parse HEAD
```

The launcher uses this `.venv` automatically. Application Python and Node dependencies are installed inside the Docker images by the committed Dockerfiles and lockfiles.

**Only when selecting database object releases (`DB_Object: "Y"`):** install the repository's pinned Oracle driver into the deployment Python environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\ags_backend\requirements-oracle.txt
```

### OCI CLI, if your kubeconfig uses it

Reuse the existing OCI CLI installation and profile on a configured machine:

```powershell
oci --version
```

If OCI CLI is missing and the destination kubeconfig requires the `oci` command, install it in a separate tool environment. Run from the **repository root**:

```powershell
$taskOciTools = Join-Path (Get-Location).Path 'ags_runtime\oci-cli'
if (-not (Test-Path -LiteralPath "$taskOciTools\Scripts\oci.exe")) {
    if (-not (Test-Path -LiteralPath "$taskOciTools\Scripts\python.exe")) {
        py -3.12 -m venv $taskOciTools
    }
    & "$taskOciTools\Scripts\python.exe" -m pip install oci-cli
    if ($LASTEXITCODE -ne 0) { throw 'OCI CLI installation failed.' }
}
$env:Path = "$taskOciTools\Scripts;" + $env:Path
oci --version
```

This follows Oracle's [virtual-environment installation method](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/climanualinst.htm). The PATH addition applies to this window; repeat it in a new window if this isolated installation is used. Keep your existing authorized OCI profile, private key and kubeconfig. The current pilot kubeconfig also depends on local authentication-helper paths; another computer needs its own usable destination kubeconfig and authentication setup from the operator.

## Common setup D: prepare the target JSON

Run from the **repository root**. Create the private JSON from the example only if it does not already exist:

```powershell
if (-not (Test-Path -LiteralPath .\ags_deploy\aegis-oci-inputs.json)) {
    Copy-Item -LiteralPath .\ags_deploy\templates\deployment-inputs.example.json -Destination .\ags_deploy\aegis-oci-inputs.json
}
notepad .\ags_deploy\aegis-oci-inputs.json
```

Fill or review these fields before a release:

| JSON field | Value to check |
| --- | --- |
| `SourcePath` | This repository's absolute path, or blank to use the current repository. |
| `Ref` | The tested branch, tag or exact commit to export and build. Uncommitted edits are excluded. |
| `DB_Object`, `DeployFrontend`, `DeployBackend` | Each is `"Y"` or `"N"`. Backend includes API and worker. |
| `Kubeconfig`, `Context`, `Namespace` | The existing destination kubeconfig and exact target. Required for application releases. |
| `Registry`, `RegistryNamespace` | Destination registry hostname and its tenancy namespace. Fill `Registry` before the login command below. |
| `Platform` | The prepared nodes' image architecture, such as `linux/arm64`. |
| `AppUrl` | Existing HTTPS URL, or blank for discovery from prepared routing. |
| `ValidationReference` | Truthful test/CI evidence for this exact source revision. The release script does not execute regression tests. |
| Database fields when `DB_Object` is `Y` | `DB_ReleaseFile`, `WalletPath`, `DatabaseOwner`, `DBAdminUser`, `ServiceAlias` and `ExpectedService`. |

Common component selections:

| Release | `DB_Object` | `DeployFrontend` | `DeployBackend` |
| --- | --- | --- | --- |
| Frontend and backend code; no DB DDL | N | Y | Y |
| Frontend only | N | Y | N |
| Backend API and worker only | N | N | Y |
| Database objects only | Y | N | N |

All N is rejected. With `DB_Object` N, a backend release still performs read-only compatibility and active-job checks. With Y, matching database objects are skipped; reviewed missing objects require `PUBLISH`. Keep passwords, registry tokens and private keys out of JSON. The private `aegis-oci-inputs.json` is ignored by Git.

Inspect the selected non-secret values:

```powershell
$taskInputs = Get-Content -LiteralPath .\ags_deploy\aegis-oci-inputs.json -Raw | ConvertFrom-Json
$taskInputs | Select-Object Ref, DB_Object, DeployFrontend, DeployBackend, Registry, Platform
```

For application releases, confirm the kubeconfig file and its local contexts:

```powershell
Test-Path -LiteralPath $taskInputs.Kubeconfig
kubectl --kubeconfig $taskInputs.Kubeconfig config get-contexts
```

`Test-Path` must return `True`. The script's later `CONNECT` stage checks actual remote access. Software installation does not grant OCI access or prepare application resources; those must already be handed over.

## Common setup E: start Docker and sign in to the registry

For frontend/backend releases, start Docker Desktop and wait until the engine is ready:

```powershell
docker desktop start
docker version
docker info --format '{{.OSType}}'
```

The final command must print `linux`. If your installed Docker version does not provide `docker desktop start`, open Docker Desktop from the Start menu. Select Linux containers if necessary. See [Docker Desktop startup](https://docs.docker.com/reference/cli/docker/desktop/start/).

Use the existing registry login, or log in interactively when needed:

```powershell
if ([string]::IsNullOrWhiteSpace($taskInputs.Registry)) {
    throw 'Fill Registry in aegis-oci-inputs.json before registry login.'
}
docker login $taskInputs.Registry
```

Enter the destination's existing registry username and auth token at Docker's private prompts. Do not add the token to the command or JSON. Database-only releases skip this Docker section.

## Method 1: invoke deploy.ps1 directly

Open the deployment folder. On your laptop:

```powershell
Set-Location "C:\Users\Laya\Documents\Codex\2026-10-09\new-chat\Aegis\ags_deploy"
```

On another computer, use that checkout's `ags_deploy` folder instead.

### 1A. Check readiness without building or deploying

```powershell
.\deploy.ps1 -CheckOnly
```

Review the displayed destination. At `Type CONNECT to continue:`, type **CONNECT** and press Enter. Supply private database passwords if prompted for the selected database action.

Successful completion prints:

```text
Read-only preflight completed; no release attempted
Aegis deployment process exited with code 0.
```

### 1B. Build and release

```powershell
.\deploy.ps1
```

This command automatically reads `aegis-oci-inputs.json` beside it and runs the following sequence:

1. Ask for **CONNECT**; run read-only preflight.
2. Ask for missing source test/CI evidence if `ValidationReference` was not supplied.
3. **Build selected images locally using Docker.** Build output appears in this PowerShell window. This can take time.
4. Print the exact source/target/image/database plan and save `plan.json`.
5. Ask for **PUBLISH**. Review the plan, then type `PUBLISH` in uppercase and press Enter only if you approve it.
6. Apply approved database actions, if selected; push selected images; update existing workloads; verify the result.

**There is no separate build command to run first.** The main script manages the committed source export, build flags and image tags. `-CheckOnly` skips builds. If you decline `PUBLISH`, locally built images can remain, but the release stops before publication.

To use a different JSON explicitly:

```powershell
.\deploy.ps1 -Inputs "C:\aegis-target\target.json"
```

Add `-CheckOnly` to that invocation for read-only preflight instead of a release.

## Method 2: invoke the shortcut scripts

Use the **same common setup, JSON and deployment folder** as Method 1.

### 2A. Check readiness

```powershell
.\Check-Aegis.ps1
```

This calls the main script with `-CheckOnly`. Type `CONNECT` when prompted. It does not build, publish or deploy.

### 2B. Build and release

```powershell
.\Deploy-Aegis.ps1
```

This calls the main script for the full release: **CONNECT -> preflight -> local Docker builds -> plan -> PUBLISH -> release -> verification**. Use the same approval instructions as Method 1. Both shortcuts pause at `Press Enter to finish` so you can read their output before closing the window.

The readiness check is optional before a full release because the full release runs preflight again. Choose one full-release command, either `deploy.ps1` or `Deploy-Aegis.ps1`, for a given run.

## Confirm the outcome

A completed application release prints:

```text
Release completed; configuration checks passed
Application: ...
Receipt: ...
Record: ...
Aegis deployment process exited with code 0.
```

A successful `-CheckOnly` run is **not a deployment**. Database-only releases have their own final database result and do not claim an application rollout.

Keep the exact `plan.json`, `result.json` and receipt paths printed by your invocation. Records are under `deployment-records/`; a rollout receipt can be inside that run's exported source. To inspect a specific saved result, replace the quoted placeholder with its exact printed path:

```powershell
Get-Content -LiteralPath 'PASTE_EXACT_RESULT_JSON_PATH_HERE' -Raw | ConvertFrom-Json
```

## If a run stops

| Output or symptom | What to do |
| --- | --- |
| `Not approved. No dependent action was started` | An approval prompt did not receive the exact requested word. Blank or different input stops the run with exit 1. Review that run's record before starting a new attempt. |
| Docker daemon unavailable | Start Docker Desktop, wait for the engine, and confirm `docker info` works. |
| Target JSON not found | Confirm `aegis-oci-inputs.json` is beside the three scripts, or pass `-Inputs` to the main script. |
| Kubeconfig/authentication error | Verify the selected file, context, authorized profile and local authentication helper. Do not change the destination or credentials just to bypass a failure. |
| Window closes too quickly | Run from an already-open PowerShell window, or use the shortcut scripts, which pause at the end. |
| Failure after PUBLISH | Inspect the exact result/receipt and completed phases before an approved retry. DDL or workload updates can be partial; no automatic retry or rollback is provided. |

The release preserves existing infrastructure, configuration, model mappings and stored data. Selected Recreate workload updates restart pods and can briefly interrupt the application. For detailed destination and database requirements, see the [OCI deployment guide](../ags_docs/Aegis_OCI_Deployment_Guide.pdf) and [database reference](../ags_database/README.md).
