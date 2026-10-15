# Aegis

Aegis turns documents into searchable knowledge and structured, reviewable results. It uses a Next.js interface, FastAPI, LangGraph agents and a durable Python worker.

**Final handover branch: `ags_sprint1`.** The source freeze remains tagged `aegis-freeze-2026-10-15`.

Read the architecture handover in [Word](ags_docs/Aegis_Architecture_and_Deployment_Handover.docx) or [PDF](ags_docs/Aegis_Architecture_and_Deployment_Handover.pdf). It includes the recently finalized Mural diagram, end-to-end workflows, verified OCI resources, deployed technology versions and model placement.

Use the dedicated [OCI Kubernetes deployment guide](ags_docs/Aegis_OCI_Kubernetes_Deployment_Guide.docx) for destination setup requirements, cluster access, registry configuration, application release, verification and rollback.

For a step-by-step code update to an existing OCI installation, use the [backend deployment PDF](ags_docs/Aegis_Backend_Deployment_Guide.pdf). It covers local checks, destination inputs, registry login, the exact release command, verification and recovery. The current script releases the API, worker and frontend together.

For Oracle Autonomous AI Database creation, wallet and user setup, schema deployment and verification, follow the [database-only deployment PDF](ags_docs/Aegis_OCI_Database_Deployment_Guide.pdf).

The live inspection on 15 October 2026 at 22:26 IST confirmed OKE hosting the web app, API, worker and CPU reranker; Oracle Autonomous AI Database 26ai storing records, the durable queue and native vectors; and OCI Object Storage holding documents and saved results. The three active datasets use Google Gemini. Laptop Ollama is a retained, stopped alternative.

Application source is under `ags_backend/` and `ags_frontend/`; Oracle scripts under `ags_database/`; OCI release tooling under `ags_deploy/`. Local launchers, runtime Compose profiles and alternative Kubernetes manifests are grouped under [ags_local_use](ags_local_use/README.md). Tests, fixtures, manual QA tools and test containers are centralized under [ags_testing](ags_testing/README.md).

Retired files are retained for review under the root `delete/` folder with their original relative paths. This archive stays outside application build contexts and active test discovery; generated reports remain ignored by Git.

## Deploy with one command

From the repository root in PowerShell, run:

```powershell
.\ags_deploy\deploy.ps1
```

Answer the prompts, or copy [the non-secret input example](ags_deploy/deployment-inputs.example.json) outside the repository, fill in known values, and run:

```powershell
.\ags_deploy\deploy.ps1 -Inputs C:\aegis-target\target.json
```

The command exports the selected committed source (`ags_sprint1` by default), discovers missing target details through existing access, builds only selected application images locally, and shows the release plan. Type `CONNECT` to permit read-only discovery, then `PUBLISH` to approve the displayed changes. Add `-CheckOnly` for read-only preflight without builds, table creation, publishing or rollout. Uncommitted changes are excluded.

Choose the components in the same JSON file. `DeployFrontend` and `DeployBackend` must be JSON `true`/`false` values, not quoted strings; both default to `true` for existing input files. Backend includes API and worker. Unselected images are not built, pushed or updated.

| Selection | `DatabaseAction` | `DeployFrontend` | `DeployBackend` |
| --- | --- | --- | --- |
| Frontend only | `skip` | `true` | `false` |
| Backend only | `skip` | `false` | `true` |
| Both application components, existing DB | `verify` | `true` | `true` |
| Fresh database tables only | `install` | `false` | `false` |
| Read-only existing database verification | `verify` | `false` | `false` |

`DatabaseAction: "skip"` skips database scripts. A backend release still requires read-only schema compatibility and active-job checks; frontend-only with `skip` makes no Oracle queries. `"verify"` compares all thirteen OCI table definitions and makes no schema changes. `"install"` creates tables in a **prepared empty owner**: also supply `WalletPath`, `DatabaseOwner`, `ServiceAlias` and the full `ExpectedService`. SQLcl privately prompts for the password. With application components selected, schema, saved connection and app readiness checks must pass before publishing images. With both flags `false`, installation runs only the guarded database installer and its schema postchecks; it needs no Docker, Kubernetes, registry or application URL. Existing-schema verification uses the prepared API's saved OCI connection and therefore still requires cluster access. Verification without application components is read-only and has no PUBLISH step. Installing a schema does not migrate an existing schema or copy documents, users or application data. Selecting `skip` with both flags `false` is rejected as an empty selection.

Prerequisites: PowerShell, Python 3.10+ (3.12 recommended; the repository `.venv` is preferred), Git and existing destination access. Application releases also need Docker, kubectl, registry login, prepared OKE Deployments, persistent state, database connection, routing and credentials. Fresh table installation needs SQLcl and the destination wallet. The OCI database instance, owner, privileges/quota and application configuration must already exist. Existing code releases require a backup/restore reference; code releases and schema installations request validation/CI evidence for the exact source. The command records this operator evidence; it does not run regression or inference tests. For application releases, it discovers an existing HTTPS URL; it does not create one. Selective application releases require a source commit containing the updated component-aware release helper; older commits stop before target access.

Infrastructure, configuration, models and existing data are preserved. The current `Recreate` strategy can cause a brief restart window when you actually release. Private plans/results and the exact release receipt are stored under ignored `ags_deploy/deployment-records/`. On any failure, inspect the reported phase and receipt before retrying: schema DDL can commit partially, and no automatic rollback is attempted. Missing prerequisites stop the command.

The existing `ags_deploy/deploy-aegis-code.ps1` and guarded database installer remain the underlying helpers. For database preparation, follow the [database installation instructions](ags_database/README.md#deploy-the-schema-to-another-oci-database). Historical resource provisioning and pilot registry setup are consolidated in `ags_deploy/ags_oke/ags_legacy_provisioning.py`; the one-command release does not run them.

The reusable [release skill](.agents/skills/aegis-release/SKILL.md) remains discoverable by AI tools. It requires a prepared destination and explicit deployment instructions. Preserve the [Unified Chat workflow](AGENTS.md).

For AI-assisted code deployment, use [the `aegis-deploy` skill](.agents/skills/aegis-deploy/SKILL.md):
"Use $aegis-deploy to deploy `ags_sprint1` to my existing OCI environment. Verify
the existing database, deploy frontend/API/worker code, and preserve all configuration.
Do not provision infrastructure." Supply the existing destination and access once.
The skill uses `ags_deploy/deploy-aegis-code.ps1` and the read-only
`ags_deploy/check-code-release.py` before/after check. Routine releases verify the
database; `ags_database/deploy-oci-database.ps1` is only for an explicitly requested
fresh schema in a prepared empty owner. Current `Recreate` deployments can have a
brief restart window. Creating or checking the skill does not deploy anything.

Earlier guides and verification reports remain in Git history at documentation commit `a33d5fb`. `ags_docs/` contains the handover in Word/PDF, the dedicated application deployment guide, and the backend code release and database deployment PDFs. The architecture diagram stays embedded in the handover. Reusable QA inputs live under `ags_testing/qa/ags_fixtures/`. These repository changes do not deploy or change the running application.

## Backend dependencies and manual tests

Use Python 3.12. `ags_backend/requirements.txt` contains the pinned shared runtime, including OCI and CPU reranking. Optional Oracle, native cloud-provider and local-embedding dependencies remain in their named runtime requirements files. The existing Docker build choices and pinned package versions are preserved. Test dependencies live in `ags_testing/backend/requirements.txt`.

Run backend tests from the repository root in PowerShell (`py -3.12 -m venv .venv` once if needed):

```powershell
.\.venv\Scripts\python.exe -m pip install -r ags_testing\backend\requirements.txt
.\.venv\Scripts\python.exe -B ags_testing\run_backend_tests.py
```

The runner selects temporary SQLite storage and mock providers in a child process, clearing inherited cloud settings and opt-in integration flags. For one file, append `backend/test_api_documentation.py -v`. Frontend unit/browser checks retain their `npm run test:*` commands. See the single [testing guide](ags_testing/README.md) for the folder layout, all commands and opt-in integrations. Application startup checks remain with runtime code. These commands do not deploy or access live OCI.
