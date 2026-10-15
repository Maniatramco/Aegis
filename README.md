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

Use three `"Y"`/`"N"` switches and a database release-file path in the same input JSON:

```json
{
  "DB_Object": "Y",
  "DB_ReleaseFile": "ags_database/release.json",
  "DeployFrontend": "Y",
  "DeployBackend": "Y"
}
```

These are the selection fields; keep the destination/access values from the input template too. Backend includes API and worker. Unselected images are not built, pushed or updated.

| Selection | `DB_Object` | `DeployFrontend` | `DeployBackend` |
| --- | --- | --- | --- |
| Database release + application code | `Y` | `Y` | `Y` |
| Frontend only | `N` | `Y` | `N` |
| Backend only | `N` | `N` | `Y` |
| Both application components, no DB scripts | `N` | `Y` | `Y` |
| Database release only | `Y` | `N` | `N` |

`DB_Object: "Y"` reads [the database release file](ags_database/release.json). Its `Scripts` array is the execution order; only listed scripts participate, with no folder scanning or extra provisioning scripts. The supplied file lists the thirteen maintained Oracle table scripts in dependency order. Paths are relative to the repository root and refer to the selected committed source. Point `DB_ReleaseFile` to another repository-relative manifest or an absolute manifest path; an external manifest is frozen into the private release record and still selects SQL from the committed source. Current object releases support the maintained `ags_database/ags_tables/` CREATE TABLE/INDEX definitions; arbitrary migrations need separate review.

The release file's `CreateSchemaIfMissing: "Y"` permits a missing application user/schema inside the **existing OCI database**. The plan lists that account, `CREATE SESSION`/`CREATE TABLE` grants, existing `DATA` tablespace and a 256 MB quota for the new account (`SchemaTablespace`/`SchemaQuotaMB` can select different existing-space settings). Existing users, passwords, grants and quotas are preserved. Matching tables/indexes are skipped; missing objects are created in the listed order; incompatible existing definitions stop the release. No object is dropped or altered and no application rows are copied or changed by this object release. Oracle creates the schema with its user; see [Oracle schema documentation](https://docs.oracle.com/en/database/oracle/oracle-database/26/admin/managing-schema-objects.html).

Supply `WalletPath`, `DatabaseOwner`, `ServiceAlias`, full `ExpectedService` and existing `DBAdminUser` (default `ADMIN`). Wallet/admin/owner passwords are prompted privately in an interactive terminal and never saved in JSON, argv, generated SQL or receipts. A new schema password is confirmed privately; the database enforces its password rules. Read-only preflight discovers exactly what is missing before PUBLISH approval. Database-only execution needs no Docker, Kubernetes, registry or application URL. If everything listed already matches and no images are selected, it completes read-only without a PUBLISH prompt. With images selected, saved database connection, schema and application checks must pass before image publication.

`DB_Object: "N"` skips the release file and database DDL. A backend release still performs read-only schema compatibility and active-job checks. Frontend-only with DB_Object N makes no Oracle queries. All three N is rejected as an empty selection. Older boolean frontend/backend values and `DatabaseAction` remain supported for existing input files; do not mix legacy DatabaseAction with DB_Object.

Prerequisites: PowerShell, Python 3.10+ (3.12 recommended; the repository `.venv` is preferred), Git and existing destination access. DB_Object Y needs `python-oracledb` from the existing `ags_backend/requirements-oracle.txt`, the destination wallet and an existing inspection/admin account; missing-schema creation requires account-creation/grant privileges. It does not create the physical database or tablespaces. Application releases also need Docker, kubectl, registry login, prepared OKE Deployments, persistent state, database connection, routing and credentials. This code/object-only release does not import application data or alter existing object definitions. A backup reference is optional and is not prompted for; releases still request validation/CI evidence for the exact source. The command records this operator evidence; it does not run regression or inference tests. For application releases it discovers an existing HTTPS URL, without creating routing or changing configuration. Selective application releases require a source commit containing the component-aware release helper.

The application Dockerfiles pin Python 3.12.15 and Node.js 22.23.3 to the same immutable base-image digests used by the current live OCI images. Keep these digests and the committed dependency lockfiles when reproducing this release. The OCI backend build includes the existing Oracle, AWS and Google native protocol SDKs, with their live versions pinned in requirements-models.txt; local in-process embeddings remain disabled, matching live.

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
