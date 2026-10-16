---
name: aegis-deploy
description: Set up a Windows workstation and build, deploy and verify Aegis releases against an existing prepared OCI environment using the maintained PowerShell scripts and a private destination JSON.
---

# Aegis setup and deployment

Use this skill when a user asks an agent to prepare prerequisites, check readiness or deploy Aegis from Windows. Use the repository's maintained scripts. This skill requires an existing prepared OCI destination; it does not provision a new tenancy, database, OKE installation or initial application configuration.

## Establish the source and destination

Find the user's Aegis Git checkout. Read its `AGENTS.md`, root `README.md`, `ags_deploy/README.md`, `ags_database/README.md` and relevant parts of `ags_docs/Aegis_OCI_Deployment_Guide.pdf`. The architecture and technology reference is `ags_docs/Aegis_Architecture_Handover.pdf`. Resolve these paths from the repository root, not from this installed skill folder. Current repository instructions and script parameters take precedence over copied examples; inspect differences before acting.

Confirm the requested scope: prerequisite setup, checks only, or build and release. Resolve the intended source checkout, destination JSON and component selections from existing trusted records before asking for missing information. Bundle unresolved source/target questions together. Do not infer a colleague's destination from the current laptop's defaults or assume a pilot namespace or architecture applies elsewhere.

For each prepared OCI environment, use its own private non-secret destination JSON and its own authorized authentication, kubeconfig, registry login and wallet as applicable. A new empty cluster is not a prepared Aegis installation. Report missing initial resources and consult the provisioning section of the deployment guide; do not run provisioning as part of this release workflow.

## Prerequisites and private inputs

Have an open Windows PowerShell 5.1 or newer window, a local Aegis Git checkout, internet access and a workstation capable of Docker Desktop Linux containers for application releases. App Installer / WinGet is needed for automatic package installation. Installer/UAC, Docker first-run and restart requirements may need operator action.

The maintained clean template is `ags_deploy/templates/deployment-inputs.example.json`. From the repository's `ags_deploy` directory, a colleague can prepare a private file once:

```powershell
New-Item -ItemType Directory -Path 'C:\aegis-target' -Force
if (-not (Test-Path -LiteralPath 'C:\aegis-target\colleague-oci.json')) {
    Copy-Item -LiteralPath '.\templates\deployment-inputs.example.json' -Destination 'C:\aegis-target\colleague-oci.json'
}
notepad 'C:\aegis-target\colleague-oci.json'
```

Use the user's actual path if different. Fill only maintained template fields:

- `SourcePath`: the local checkout, or blank to use the current repository. `Ref` applies only with `-CommittedSource`.
- `DB_Object`, `DeployFrontend`, `DeployBackend`: explicit `Y` or `N`; at least one component must be selected. Backend covers API and worker.
- Application destination: `Kubeconfig`, `Context`, `Namespace`, `Registry`, `RegistryNamespace`, `Platform`, `AppUrl`. Some blank details can be resolved by authorized preflight; kubeconfig and authentication must already be usable on this workstation.
- Database object releases: `DB_ReleaseFile`, `WalletPath`, `DatabaseOwner`, `DBAdminUser`, `ServiceAlias`, `ExpectedService` as applicable. Verify these against the actual destination.
- `ValidationReference`: truthful test/CI evidence for the selected source. `BackupReference` is optional; do not require or invent a backup.

Keep filled JSON and credentials out of Git and images. Never include passwords, tokens, private keys or wallet contents in JSON, command arguments, chat or logs. Use existing secure credential paths and private prompts. Do not copy another person's authentication material to a new environment.

## 1. Set up and check prerequisites

Change to the actual checkout's `ags_deploy` directory and display the command being run:

```powershell
.\Setup-Aegis.ps1 -Inputs 'C:\aegis-target\colleague-oci.json'
```

If `-Inputs` is omitted, the default is `aegis-oci-inputs.json` beside the scripts. Supply the same explicit `-Inputs` file on setup, checking and deployment whenever choosing another destination.

Normal setup reuses working tools and installs supported missing dependencies as applicable:

- Git, Python 3.12, kubectl and Docker Desktop through WinGet.
- A missing project `.venv`; a broken existing environment stops for repair rather than being overwritten.
- An isolated OCI CLI when the chosen kubeconfig requires it.
- The maintained pinned Oracle driver when `DB_Object` is `Y`.
- Docker engine startup and Linux-container checks. WSL installation may need administrator action and a restart.

Setup checks source/target inputs, authentication prerequisites, application build-drive headroom (at least 10 GiB), builder architecture and authorized target preflight. It can perform a private Docker registry login and check current-image metadata. It does not clone the source, create OCI access, provision resources, run regression tests, build images, prove push permission or guarantee a later rollout.

Obtain permission for read-only remote inspection of the selected account/profile and destination before connecting, unless this release's same discovery scope was already explicitly authorized. Present `CONNECT` to the operator. Do not auto-answer it or treat shared credentials as publication approval. Preserve approved scope and do not repeatedly request unchanged permission.

Complete installer/credential prompts privately. Do not bypass organization execution policies or automatically restart Windows. If setup stops, inspect its exact printed report, resolve the reported prerequisite and rerun the same setup command. Continue only when it exits successfully and prints `AEGIS_PREREQUISITES_READY`.

Setup reports are saved under `ags_runtime/deployment-setup/setup-.../result.json` and remain ignored by Git. This marker means applicable checks passed at that time; it does not mean the application was deployed.

For an explicitly requested check without installing, starting Docker or logging into the registry:

```powershell
.\Setup-Aegis.ps1 -Inputs 'C:\aegis-target\colleague-oci.json' -CheckOnly
```

It still writes a local report and requires authorization for remote read-only checks. Missing tools stop the check. Database-only releases need neither Docker nor Kubernetes.

## 2. Build and deploy

Run from the same `ags_deploy` directory with the same destination JSON:

```powershell
.\Deploy-Aegis.ps1 -Inputs 'C:\aegis-target\colleague-oci.json'
```

The shortcut invokes `deploy.ps1`. The main equivalent is:

```powershell
.\deploy.ps1 -Inputs 'C:\aegis-target\colleague-oci.json'
```

Choose one release invocation per run. There is no additional manual application build command before it. The workflow is CONNECT, target preflight, selected image builds, saved plan, PUBLISH, release and verification. `Check-Aegis.ps1` or `deploy.ps1 -CheckOnly` performs release preflight without builds or publication.

### Saved source by default

The Windows scripts snapshot saved local application/database files and the maintained release helper. New non-ignored source files and saved deletions are included. Save and validate intended edits before starting. Existing working-tree changes must be reviewed; do not reset, stash or silently include unrelated work. Private state, credentials, ignored new files, generated output and `delete/` stay outside the snapshot.

No Git commit or JSON `Ref` change is required for this default Windows route. The plan's `source_mode` is `working-tree`; its base commit is metadata, not proof that every snapshot byte is committed. Use `source-manifest.json` and the snapshot fingerprint to identify the approved source. Later edits require another run. Each release invocation runs the selected Docker builds; unchanged layers may use cache. Saving a file alone does not trigger deployment.

For an explicitly requested committed-source release, pass `-CommittedSource` consistently to both setup and deployment. Then the JSON `Ref` selects the exported revision and uncommitted edits are excluded.

### Approval of publication

Complete authorized local preparation and read-only checks before presenting the exact saved plan. Show source mode and fingerprint/commit, source validation evidence, selected image IDs/tags, verified cluster/context/server/namespace and architecture, registry, database identity and actions, public endpoint, preserved configuration, current readiness, expected restart window and result/receipt locations. Clearly label unrun model/inference/write tests.

Wait for the user's approval of that exact plan before image publication, database DDL or workload updates. Have the operator type `PUBLISH`, or relay it only after explicit approval of the unchanged exact plan. Never prefill approval words, pipe them automatically, change helpers to bypass them or reuse another release's approval. If source, artifacts, target or database action changes, review the amended plan again.

A declined or missing approval stops the release. Preparation, source commit, a successful build and `AEGIS_PREREQUISITES_READY` do not mean publication occurred.

## Preserve runtime state and database scope

Preserve existing infrastructure, ConfigMaps, Secrets, application settings, database/storage configuration, model registrations/defaults, wallets, volumes, sidecars/init images, replica counts, resource limits and deployment strategy. Use live-compatible dependency flags and maintained lockfiles; do not upgrade dependencies or change model mappings to make a release pass. The maintained helper permits only selected application image updates and approved database actions.

Do not invoke historical provisioning helpers, `kubectl apply`, Helm, configuration patches or relay/model installation during this code release. Do not provision or repair missing resources implicitly.

`DB_Object=N` performs no DDL. A backend release can still require read-only schema and active-job checks. Frontend-only with database objects disabled makes no Oracle queries. With `DB_Object=Y`, inspect the ordered `DB_ReleaseFile` (normally `ags_database/release.json`): matching objects are preserved, supported listed missing objects may be created, and incompatible existing definitions stop the release. Missing app user/schema creation requires explicit permission in the release file and exact final plan approval. Do not replay the legacy empty-owner installer over an initialized schema, modify existing grants/quotas, drop/truncate objects, import data or invent migrations.

Respect active processing jobs and required provider connectivity. Require a laptop/relay only for operations actually mapped to it; Gemini/GCP connections do not imply a local-model requirement. Optional unavailable providers must be reported accurately rather than remapped.

## Verify, report and handle failure

Use the exact plan/result/receipt paths printed by this invocation. Do not choose a guessed or latest receipt. Confirm the final result, immutable published image digests, rollout readiness, selected/unselected image checks and preserved configuration/schema checks. Verify application reachability within authorized scope. Run upload/extraction/inference smoke tests only when those writes/calls are authorized; readiness is not proof of full application acceptance.

Selected Recreate deployments restart pods and can briefly interrupt service. There is no automatic rollback or retry. On failure, stop dependent steps, report completed phases and inspect the receipt/current images before proposing recovery. Do not rerun partial DDL or change settings to force a pass. Rollback requires an approved compatible recovery plan.

Report source snapshot identity, exact target, database verified/created/skipped status, published image digests, receipt path, checks actually completed and any remaining limitations. State whether this was prerequisite setup, preflight only or a completed release. Keep secrets out of all summaries.