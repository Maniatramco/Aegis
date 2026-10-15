---
name: aegis-deploy
description: "Deploy Aegis frontend, API and worker code to an existing OCI OKE installation while preserving configuration; verify its Oracle schema, or install the supplied schema into an explicitly requested empty owner. Use for Aegis release execution and deployment preflight, excluding infrastructure provisioning."
---

# Aegis deployment to prepared OCI

Use the repository's maintained deployment helpers. The user wants AI to perform
the release, with existing OCI resources, settings, credentials, model mappings
and stored data preserved. Creating this skill, explaining it, or requesting a
preflight does not authorize a deployment. An explicit deployment request for a
clear destination authorizes the code release; do not repeatedly ask for the same
permission. Ask only for a missing destination/input or an actual scope change.

## Resolve the release

Find the Aegis repository from the active project or the user's supplied path;
confirm it contains `ags_deploy/deploy-aegis-code.ps1` and `ags_database/install.sql`.
Use all paths below relative to that repository. Read `AGENTS.md`, the root README
and `ags_database/README.md`. The existing backend deployment PDF in `ags_docs/`
documents the helper's parameters, receipts and rollback procedure.

Resolve these inputs once from the user or existing trusted destination records:
source commit/branch, kubeconfig, Kubernetes context and server, namespace, OCIR
host and registry namespace, image architecture, public application URL, and DB
owner/service identity. Do not infer a new destination from the OCI tenant alone.
The current handover branch is `ags_sprint1`; the pilot namespace is `aegis-oci`
and its platform is `linux/arm64`. Confirm these against the selected destination.
Credentials and wallet files stay outside Git and prompts/logs. Use existing
authentication and registry login; obtain missing secrets through a private
credential mechanism. Do not create users, grants, Secrets or pull credentials.

Select the exact approved source commit. Preserve unrelated working-tree changes;
use a separate clean checkout or `git archive` export of that commit for builds
when needed. Do not reset, stash or include untracked files without instruction.
Keep `delete/`, test reports, private state and wallet/secret files outside images.

## Scope and database decision

| Destination | Database action | Application action |
| --- | --- | --- |
| Existing Aegis schema; ordinary code release | Read-only schema verification | Update web, API and worker images |
| Explicit fresh schema request; DB and empty owner already prepared | Run the guarded schema installer once, then verify | Release only when the existing OKE app state is also prepared |
| Existing schema differs from the supplied scripts | Report exact differences; stop the release | Wait for an explicitly reviewed migration |
| Missing infrastructure, credentials, volumes, wallet or app configuration | Report the missing prerequisite | Stop; do not provision or repair configuration |

The thirteen `ags_tables/*.sql` files are a **fresh-schema installer**, not
incremental migrations. Never replay them against an initialized database, drop
objects, truncate data, regenerate them from local SQLAlchemy tools, or invent
migration SQL. This repository currently has no versioned OCI upgrade migrations.
An existing database that matches the release needs no DDL during a code update.

For existing schemas, run `ags_database/ags_schema/verify_live_schema.sql` in a
read-only connection as the existing owner, checking the actual owner/service,
thirteen PRESENT tables, 165 columns, constraints/indexes and native vectors.
Compare the returned definitions with `ags_database/ags_tables/`, including types,
defaults, nullability, keys and indexes; table counts alone are insufficient.
Use existing SQLcl/wallet access, or the deployed backend's saved OCI connection
with the installed thin driver in a separate `python -B` inspection process.
For the latter, read `/data/configuration/database.json` (respect the configured
storage root), its contained `active_connection` and encrypted `secret_ref` through
the existing master key. Keep resolved secret paths within the storage root.
Import only driver/crypto/standard libraries, never the application: imports or
startup can initialize live state. Start `SET TRANSACTION READ ONLY`; execute only
the verification SELECTs/metadata reads and roll back. Do not print credentials,
model keys, application rows or decrypted state. Missing access is a prerequisite
failure, not authorization to change accounts or configuration.

Only for an explicitly requested **new, empty owner**, use the existing installer:

```powershell
.\ags_database\deploy-oci-database.ps1 -WalletPath $WalletPath -UserName $DbOwner -ServiceAlias $ServiceAlias -ExpectedService $FullService -CheckOnly
```

When the fresh installation is authorized for this exact destination, run:

```powershell
.\ags_database\deploy-oci-database.ps1 -WalletPath $WalletPath -UserName $DbOwner -ServiceAlias $ServiceAlias -ExpectedService $FullService
```

The first command is local-only. The second creates the schema and must return
the `AEGIS_SCHEMA_INSTALL_OK` marker. SQLcl prompts privately for the password.
DDL can commit before a later failure: stop and report a partial install; never
blindly rerun, automatically roll back the schema or modify the existing owner.
Schema creation does not provision the DB or seed application configuration/data.

## Code release with configuration preserved

Preserve ConfigMaps, Secrets, runtime TOML, saved database/storage configuration,
wallets, model registrations/defaults, relay setup, sidecars/init containers,
storage, services, replica counts, resource limits and rollout strategy. Do not
run `ags_legacy_provisioning.py`, `ags_render.py`, `ags_runtime_config.py`, local
setup/migration scripts, `kubectl apply`, Helm, scale, configuration patch or
registration endpoints during this workflow. The release helper's permitted
cluster mutations are image updates for `web`, `api` and `worker` only.

Before release, verify the approved source's backend tests, frontend unit tests,
type checks and production build using `ags_testing/README.md`. Reuse completed
evidence only when it applies to the exact unchanged source. Build with the
committed lockfiles and the existing OCI feature profile; do not upgrade packages
or change build flags to fix unrelated failures. The helper currently builds
with Oracle/OCI enabled and optional in-process embeddings/native cloud model
SDKs disabled. Ollama and OpenAI-compatible Gemini use their existing remote
endpoints; their model files/registrations are not installed or replaced here.
Confirm any selected native provider's SDK is present before using this helper.

Check existing authenticated read access, registry login/pull access, node
architecture, schema, persistent state and reranker assets. Let active jobs finish
and confirm the existing backup/restore point. Do not cancel jobs or overwrite
backups. The pilot uses one replica and `Recreate`, so image updates restart pods
and can cause a brief service interruption. Do not change that strategy or promise
zero downtime. Check model reachability using read-only metadata endpoints; require
the laptop/relay only for operations actually mapped to laptop Ollama. Retain an
unavailable optional local provider and report its status. Never start or retarget
the relay, pull models or substitute another provider to make a check pass.

Set `$SourcePath`, `$Kubeconfig`, `$Context`, `$Namespace`, `$Registry`,
`$RegistryNamespace`, `$Platform` and a unique `$Release` from the resolved inputs.
Use unique private files under `ags_deploy/deployment-records/` for `$Baseline`.
`python` below means the available trusted Python runtime, not a newly installed
global package environment. The check helper uses the standard library and kubectl.

```powershell
python -B .\ags_deploy\check-code-release.py snapshot --source-path $SourcePath --kubeconfig $Kubeconfig --context $Context --namespace $Namespace --output $Baseline
if ($LASTEXITCODE -ne 0) { throw 'Release baseline check failed.' }
```

This only reads Kubernetes resources and hashes configuration files in existing
API/worker containers. It stops on unready deployments, API/worker configuration
differences or source runtime TOML drift. Its saved output contains fingerprints,
identities and images rather than configuration/secret values. It does not verify
the schema or models; perform those separate checks above. Missing read permission
must be resolved outside this code-only deployment, not bypassed.

Present the resolved target/commit, DB action, images-only scope and restart window
briefly. If the user already requested this deployment, proceed without another
generic confirmation. For a preflight-only request, finish here and report readiness.
Immediately before mutation, recheck that the source and destination are unchanged:

```powershell
python -B .\ags_deploy\check-code-release.py verify --source-path $SourcePath --kubeconfig $Kubeconfig --context $Context --namespace $Namespace --baseline $Baseline
if ($LASTEXITCODE -ne 0) { throw 'Pre-release configuration check failed; no release started.' }
.\ags_deploy\deploy-aegis-code.ps1 -SourcePath $SourcePath -Kubeconfig $Kubeconfig -Context $Context -Namespace $Namespace -Registry $Registry -RegistryNamespace $RegistryNamespace -Platform $Platform -Release $Release
```

The deployment helper builds/pushes both images, records previous image references,
updates API+worker first and web second, and waits for rollouts. `-SkipBuild` still
pushes and deploys; it is not a dry run. There is no backend-only switch or automatic
rollback. Do not edit the helper, manifests, configuration or source during execution.

Capture the **exact receipt path printed by that invocation** as `$Receipt`; never
choose a receipt by "latest file" or a guessed timestamp. Then run:

```powershell
python -B .\ags_deploy\check-code-release.py verify --source-path $SourcePath --kubeconfig $Kubeconfig --context $Context --namespace $Namespace --baseline $Baseline --receipt $Receipt
if ($LASTEXITCODE -ne 0) { throw 'Post-release verification failed; inspect the receipt and actual deployment.' }
```

The check binds the receipt to the original destination and images; verifies the
three new application images and unchanged sidecars/init images; compares deployment
settings and ConfigMap/Secret/service/PVC fingerprints; and checks the active TOML,
saved database/storage configuration, effective backend environment and readiness.
A mismatch stops success reporting;
inspect whether it came from this release or concurrent activity. Do not overwrite
configuration to force a match. This is drift detection, not a cluster-wide lock.

Verify HTTPS and authenticated read-only screens, existing dataset/model mappings,
retrieval/reranker readiness and required provider connectivity. Prefer synthetic
upload/extraction/cited-chat smoke work in a prepared test workspace only when that
workflow write is included in the deployment authorization. Otherwise report those
write/inference tests as unrun; readiness alone is not an end-to-end model test.

## Failure and completion

On build, push, rollout, schema or drift-check failure, stop dependent steps and
report the exact completed phases. Inspect the existing receipt/current images;
do not automatically rerun the release, use rollout undo, reset configuration, or
claim success for a partial deployment. Image rollback needs authorization (unless
already included), the same destination, and compatible data/schema. Restore only
the previous images that actually changed; leave all configuration untouched.

Report source commit, target, DB verified/installed/skipped, new/previous image
digests, receipt path, readiness and configuration-check results, tests actually run,
model availability, and any partial failure. Keep sensitive values out of the report.

Reference behavior: [Kubernetes image updates and rollouts](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
and [Oracle SQLcl commands](https://docs.oracle.com/en/database/oracle/sql-developer-command-line/25.1/sqcug/index.html).
