# Windows PowerShell deployment

For a colleague, use **two commands in order**: `Setup-Aegis.ps1`, then `Deploy-Aegis.ps1`. Both are in this `ags_deploy` folder. The first prepares and checks the workstation and selected destination. The second builds and releases the selected Aegis components.

## Prerequisites - read this first

Before running either script, prepare the following for the OCI environment you intend to deploy to:

| Have ready before setup | What is required |
| --- | --- |
| Windows workstation and PowerShell | Use an already-open Windows PowerShell 5.1 or newer window. For application releases, the workstation must support Docker Desktop and Linux containers. |
| App Installer / WinGet and internet access | Needed to install missing workstation packages. If `winget` is unavailable, install Microsoft's App Installer first. Have administrator approval available for installers or WSL setup when requested. |
| Local Aegis Git checkout | Use your colleague's own checkout with Git history and saved, validated source files. Setup installs a missing Git executable; it does not clone or replace the application checkout. |
| Private destination JSON | Fill the component selections, source and destination details in `aegis-oci-inputs.json`, or supply another private file with `-Inputs` on both scripts. Keep passwords and tokens out of JSON. |
| Prepared OCI destination | A compatible existing Aegis installation: required database, OKE workloads, storage, Secrets, configuration, model mappings and HTTPS routing as applicable. Setup does not provision these resources. |
| Destination access for application releases | A usable kubeconfig/context, authorized authentication/profile and any private key or local helper it needs, access to the target and existing registry credentials with release permissions. Use that destination's own files and credentials. |
| Database access when `DB_Object` is `Y` | Destination wallet ZIP, owner/admin account names, service alias, expected service and authorized database credentials. Passwords are entered privately when requested. |
| Source validation evidence | A truthful test/CI reference for the saved source being released. Setup checks prerequisites; it does not execute the application's regression or inference tests. |
| Build space for application releases | Setup requires at least 10 GiB free on the source/work drive. Docker image storage and actual builds may require more space. |

Git, Python, kubectl, Docker Desktop and applicable OCI CLI/Oracle dependencies **do not need to be installed manually first**: normal setup installs missing supported tools as described below. Database-only releases do not require Docker or Kubernetes.

### Prepare the private JSON

Have a local Aegis Git checkout and a filled **private** `ags_deploy\aegis-oci-inputs.json`. On another computer, use that computer's checkout, kubeconfig, existing OCI profile/private key and wallet paths. Software setup cannot grant OCI access, create destination workloads or manufacture test evidence. Keep passwords and tokens out of the JSON.

If the JSON is missing, setup copies `templates\deployment-inputs.example.json` to the default location and stops so you can fill it. See **Prepare the target JSON** below. Windows App Installer (`winget`) and internet access are needed to install missing workstation packages. Installers may request administrator approval. Run in an already-open Windows PowerShell window.

### What setup installs automatically

**Run `Setup-Aegis.ps1` without `-CheckOnly` to enable automatic installation.** You do not need to run the manual installation commands later in this README first. Setup reuses available tools, installs missing supported tools as needed for the selected components, and checks the result before continuing.

| Prerequisite | What normal setup does |
| --- | --- |
| Git | Installs it through WinGet if missing. |
| Python and the project `.venv` | Reuses a supported Python environment; installs Python 3.12 if needed and creates a missing project `.venv`. An existing broken or unsupported `.venv` stops setup for repair. |
| kubectl | Installs it through WinGet if missing and an application release is selected. |
| Docker Desktop | Installs it through WinGet if missing and an application release is selected; starts the engine if needed and checks Linux containers. First-run prompts may need your input. |
| OCI CLI | Installs it in the repository's isolated tool environment if the selected kubeconfig requires it and it is missing. |
| Oracle Python driver | Installs the maintained pinned requirement when missing or different, only when `DB_Object` is `Y`. |
| WSL | If Docker cannot start because WSL is missing, setup can request WSL installation when Windows administrator access and the WSL command are available. Follow the reported instructions, restart if requested and rerun setup. |

You still need to provide the filled destination JSON, authorized kubeconfig/authentication, registry credentials, applicable database wallet and truthful source-validation evidence. The OCI resources and compatible Aegis workloads must already exist. If WinGet is missing, install Microsoft's App Installer first. Complete installer/UAC, Docker first-run, private credential and `CONNECT` prompts yourself.

Setup never restarts Windows automatically. If installation or a readiness check fails, it stops and prints the reason and saved result path. Resolve the reported issue and rerun the **same setup command with the same target JSON**. Run deployment only after `AEGIS_PREREQUISITES_READY` appears. With `-CheckOnly`, setup checks existing prerequisites and does **not** install missing software, start Docker or log into the registry.

## Each deployment builds your saved local files

The Windows scripts now use **saved local source by default**. No Git commit or JSON `Ref` update is required for an ordinary local deployment. Each time you save code and want to release it, run:

```powershell
.\Deploy-Aegis.ps1
```

Each invocation snapshots the current saved source from `SourcePath` (or this checkout when blank), checks the destination, runs Docker builds for the selected components, presents the plan, and deploys after `PUBLISH` approval. New non-ignored source files and saved deletions are included. Save files **before** starting; edits made after the snapshot are included on the next run.

The snapshot includes application/database source and the release helper. Git-ignored new files, private credentials, local runtime data, build output and the `delete` archive are excluded. Docker may reuse unchanged cached layers; the build command still runs every time. Runtime configuration, JSON target settings and unselected components retain their existing deployment rules. This command does not watch for changes or deploy automatically when you press Save.

The plan records `source_mode: working-tree`, a base Git commit, the snapshot fingerprint and `source-manifest.json` with file hashes. The base commit is background information; the saved files in the snapshot are the build inputs. JSON `Ref` is ignored in this default Windows mode. The release still requires `CONNECT`, validation evidence for those files and `PUBLISH` approval.

For an explicitly pinned committed release instead, pass `-CommittedSource` consistently:

```powershell
.\Setup-Aegis.ps1 -CommittedSource
.\Deploy-Aegis.ps1 -CommittedSource
```

Only this opt-in mode exports the JSON `Ref` and excludes uncommitted edits. Alternate destination JSON files continue to work with `-Inputs` on both commands.

## 1. Run prerequisite setup

On this laptop:

```powershell
Set-Location "C:\Users\Laya\Documents\Codex\2026-10-09\new-chat\Aegis\ags_deploy"
.\Setup-Aegis.ps1
```

On your colleague's computer, replace the `Set-Location` path with their checkout's `ags_deploy` folder. If PowerShell blocks local scripts under the current execution policy, and your organization's policy permits it, enable locally created scripts **for this window only**, then retry:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\Setup-Aegis.ps1
```

Setup automatically:

1. Validates the non-secret target JSON, selected components, local handoff files, Git ignore rules and the selected saved-source snapshot (or committed Ref with `-CommittedSource`).
2. Reuses working tools and installs missing Git, Python 3.12, kubectl and Docker Desktop through WinGet as applicable. Creates the repository `.venv`; installs the maintained Oracle driver only for database object releases, and an isolated OCI CLI only when the kubeconfig needs it.
3. Starts Docker Desktop when needed, verifies a Linux engine, at least 10 GiB free on the source/work drive and builder support for the selected architecture. Docker image storage and actual builds can require more space.
4. Displays the destination and asks you to type **CONNECT** before remote checks. Runs the existing read-only Aegis preflight for the selected target, authentication, workload/configuration and schema checks as applicable.
5. For application releases, runs `docker login` for the resolved registry, using existing credentials or private prompts, and checks matching current-image metadata. Registry push permission is only proven by a real publication.
6. Saves an individual JSON result under `ags_runtime\deployment-setup\setup-...\result.json` (ignored by Git). It displays each check and the exact result path.

Complete any installer, Docker first-run or credential prompts. If Windows/WSL requires a restart, setup stops: restart and rerun the **same** setup script. It never reboots automatically. It stops on a failed check and does not claim readiness.

Continue only when setup prints:

```text
AEGIS_PREREQUISITES_READY
```

This means the prerequisite checks passed for the selected source and destination at that time. It is not proof that an application image builds, registry push permission exists, regression/inference tests pass or a later rollout will succeed. Provide truthful `ValidationReference` evidence in the JSON. Setup does not build or publish images, apply database DDL, change workloads or create infrastructure.

## 2. Build and deploy Aegis

In the same folder:

```powershell
.\Deploy-Aegis.ps1
```

This runs **CONNECT -> preflight -> selected Docker image builds -> saved plan -> PUBLISH -> release -> verification**. There is no extra manual application build command. At the prompts, type `CONNECT` to permit read-only inspection; review the saved release plan, then type `PUBLISH` only to approve that exact release. A declined approval stops the release. Neither script supplies approval words automatically.

Selected Recreate deployments restart pods and can briefly interrupt the app. Existing infrastructure, configuration, model mappings and stored data are preserved; there is no automatic retry or rollback. Keep the printed plan, result and receipt paths.

## Check again without installing

```powershell
.\Setup-Aegis.ps1 -CheckOnly
```

This still asks for `CONNECT` and performs remote read-only target/image metadata checks. It does not install software, create a virtual environment, start Docker or log into the registry. Missing prerequisites or unverifiable registry access stop the check. It writes local result files.

## Deploy to a different prepared OCI environment

The scripts can target a different OCI tenancy, region or OKE cluster when it already has the compatible Aegis installation and required resources. Keep a separate private target JSON for each destination; use the **same file for both commands**. Changing the JSON selects the destination; the scripts do not create OCI infrastructure or install initial Aegis workloads.

Create a destination file once, from the clean template rather than someone else's filled configuration. From `ags_deploy`:

```powershell
New-Item -ItemType Directory -Path "C:\aegis-target" -Force
if (-not (Test-Path -LiteralPath "C:\aegis-target\colleague-oci.json")) {
    Copy-Item -LiteralPath .\templates\deployment-inputs.example.json -Destination "C:\aegis-target\colleague-oci.json"
}
notepad "C:\aegis-target\colleague-oci.json"
```

Fill the destination's own values:

| Setting | Use for this destination |
| --- | --- |
| `SourcePath`, `Ref`, `ValidationReference` | Colleague's local checkout (or blank `SourcePath`) and evidence for the saved files. `Ref` is used only with `-CommittedSource`. |
| `Kubeconfig`, `Context`, `Namespace` | Destination-specific kubeconfig with the authorized OCI profile and region in its authentication configuration, exact context and Aegis namespace. |
| `Registry`, `RegistryNamespace` | Destination OCIR registry hostname and tenancy namespace, plus that destination's private Docker login. |
| `Platform`, `AppUrl` | Prepared target's node architecture and existing application URL; blank values may be discovered during preflight. |
| Database fields when `DB_Object` is `Y` | Destination wallet ZIP, owner/admin account names, service alias and expected database service. Passwords remain private prompts. |
| `DB_Object`, `DeployFrontend`, `DeployBackend` | Components intended for this particular environment, each `Y` or `N`. |

Obtain that environment's authorized kubeconfig, OCI profile/key, registry login and database wallet as applicable. A kubeconfig referring to another laptop's authentication helper is not portable; setup stops if it cannot use it. Do not copy another person's credentials or reuse the first environment's wallet/registry details for a different destination.

Your colleague then runs only these two scripts:

```powershell
.\Setup-Aegis.ps1 -Inputs "C:\aegis-target\colleague-oci.json"
# Continue only after AEGIS_PREREQUISITES_READY:
.\Deploy-Aegis.ps1 -Inputs "C:\aegis-target\colleague-oci.json"
```

Setup prints the exact next deploy command with the same absolute JSON path. The deploy script displays that path and reruns target preflight before showing the release plan and requesting approval. Without `-Inputs`, either script uses the adjacent private `aegis-oci-inputs.json`; supply `-Inputs` on **both** commands whenever selecting an alternate file. No remembered global destination is used.

For checks only:

```powershell
.\Setup-Aegis.ps1 -Inputs "C:\aegis-target\colleague-oci.json" -CheckOnly
.\Check-Aegis.ps1 -Inputs "C:\aegis-target\colleague-oci.json"
```

## Existing deployment invocation options

The normal colleague workflow above is sufficient. These Windows invocation options remain available after prerequisites are ready:

| Invocation | Read-only release preflight | Build and release |
| --- | --- | --- |
| Main script directly | `.\deploy.ps1 -CheckOnly` | `.\deploy.ps1` |
| Shortcut scripts | `.\Check-Aegis.ps1` | `.\Deploy-Aegis.ps1` |

The shortcuts call `deploy.ps1`; choose one release command per run. `Check-Aegis.ps1` performs the existing target preflight, while `Setup-Aegis.ps1` also handles workstation preparation. A successful check is not a deployment.

The following sections provide manual installation and troubleshooting commands if automated setup stops. Skip manual installation for tools that already work.

## Documents, agent skill and application version

Use the [architecture handover PDF](../ags_docs/Aegis_Architecture_Handover.pdf) for technology versions, workflows, resources and model placement. The [OCI deployment guide](../ags_docs/Aegis_OCI_Deployment_Guide.pdf) covers provisioning/initial handoff on pages 2-7, Windows prerequisites on pages 10-11 and the saved-source release on page 15. These scripts require the prepared destination described there; workstation setup is not infrastructure provisioning.

The repository includes the [Aegis deployment agent skill](../.agents/skills/aegis-deploy/SKILL.md). Ask your agent to use it with your actual checkout and private destination JSON paths to prepare prerequisites, verify the destination and deploy after approval of the exact release plan. It uses the same PowerShell scripts. Read-only connection permission and publication approval remain separate; credentials stay in private prompts. The [root README](../README.md) provides a colleague quick start from cloning through release.

The displayed base version is `v26.1.0.0`, maintained in [application-version.json](../ags_frontend/app/application-version.json). The compact Connections footer exposes service details on hover, focus or click. AI hosting labels follow authorized dataset defaults, including GCP for Gemini and Local / GCP for mixed connections; this is metadata, not a provider health check. Build and deploy the saved frontend changes to update the running UI.

## Manual reference: install missing workstation tools

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

## Manual reference: open the project and prepare Python

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

The launcher uses this `.venv` automatically. Application Python and Node dependencies are installed inside the Docker images by the snapshot Dockerfiles and lockfiles.

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

This follows Oracle's [virtual-environment installation method](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/climanualinst.htm). The manual PATH addition applies to this window. Setup and the deployment launcher discover this isolated tool environment automatically in later windows. Keep your existing authorized OCI profile, private key and kubeconfig. The current pilot kubeconfig also depends on local authentication-helper paths; another computer needs its own usable destination kubeconfig and authentication setup from the operator.

## Prepare the target JSON

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
| `Ref` | Used only with `-CommittedSource`: tested branch, tag or commit to export. Default Windows runs build saved local files and ignore this field. |
| `DB_Object`, `DeployFrontend`, `DeployBackend` | Each is `"Y"` or `"N"`. Backend includes API and worker. |
| `Kubeconfig`, `Context`, `Namespace` | The existing destination kubeconfig and exact target. Required for application releases. |
| `Registry`, `RegistryNamespace` | Destination registry hostname and its tenancy namespace. Fill `Registry` before the login command below. |
| `Platform` | The prepared nodes' image architecture, such as `linux/arm64`. |
| `AppUrl` | Existing HTTPS URL, or blank for discovery from prepared routing. |
| `ValidationReference` | Truthful test/CI evidence for the saved snapshot, or the exact revision with `-CommittedSource`. The release script does not execute regression tests. |
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

## Manual reference: start Docker and sign in to the registry

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

**There is no separate build command to run first.** The main script manages the saved-source snapshot, build flags and image tags (`-CommittedSource` selects a committed export instead). `-CheckOnly` skips builds. If you decline `PUBLISH`, locally built images can remain, but the release stops before publication.

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
| Setup approval prompt appears only after `Not approved` | Use the updated setup scripts, then rerun the same `Setup-Aegis.ps1` command. The interactive prompt must be visible before you type `CONNECT`; press Enter after the word. A failed setup check does not undo an earlier completed deployment. |
| Docker daemon unavailable | Start Docker Desktop, wait for the engine, and confirm `docker info` works. |
| Target JSON not found | Confirm `aegis-oci-inputs.json` is beside the PowerShell entry scripts, or pass `-Inputs` to the main script. |
| Kubeconfig/authentication error | Verify the selected file, context, authorized profile and local authentication helper. Do not change the destination or credentials just to bypass a failure. |
| Window closes too quickly | Run from an already-open PowerShell window, or use the shortcut scripts, which pause at the end. |
| Failure after PUBLISH | Inspect the exact result/receipt and completed phases before an approved retry. DDL or workload updates can be partial; no automatic retry or rollback is provided. |

The release preserves existing infrastructure, configuration, model mappings and stored data. Selected Recreate workload updates restart pods and can briefly interrupt the application. For detailed destination and database requirements, see the [OCI deployment guide](../ags_docs/Aegis_OCI_Deployment_Guide.pdf) and [database reference](../ags_database/README.md).
