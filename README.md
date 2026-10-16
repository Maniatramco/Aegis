# Aegis

Aegis turns documents into searchable knowledge and structured, reviewable results. It uses a Next.js interface, FastAPI, LangGraph agents and a durable Python worker.

**Final handover branch: `ags_sprint1`.** The original source freeze remains tagged `aegis-freeze-2026-10-15`.

Read the architecture handover in [Word](ags_docs/Aegis_Architecture_Handover.docx) or [PDF](ags_docs/Aegis_Architecture_Handover.pdf) for the approved Mural diagram, end-to-end workflows, observed OCI resources, running technology versions and model placement.

Use the single [final OCI deployment PDF](ags_docs/Aegis_OCI_Deployment_Guide.pdf) in order: **Section 1 Resource provisioning (pages 2-7)** covers OCI/model prerequisites and their purposes, the recorded Mumbai pilot example and initial installation handoff. **Section 2 Code deployment (pages 8-18)** includes the workflow diagram on page 9, the AI skill, Windows PowerShell and OCI Cloud Shell routes, component flags, approvals, verification and recovery. Windows automatic setup is on pages 10-11 and saved-file deployment on page 15; Cloud Shell setup and execution are on pages 16-17. It replaces the separate database, backend and Kubernetes deployment guides. Provisioning and initial configuration remain separate from the code/object release command and AI deployment skill.

## Deploy with one command

Copy [the non-secret input template](ags_deploy/templates/deployment-inputs.example.json) outside Git, fill the destination values, and run from the repository root in an interactive PowerShell terminal:

```powershell
.\ags_deploy\deploy.ps1 -Inputs C:\aegis-target\target.json
```

With a private `ags_deploy/aegis-oci-inputs.json` beside the script, `-Inputs` can be omitted. That file is ignored by Git. Supporting implementations are under `ags_deploy/scripts/`; the private target is not a distributable template.

To build inside OCI without Docker Desktop, use the same Y/N inputs with Linux paths in the correct tenancy's **Cloud Shell**:

```bash
bash ./ags_deploy/cloud_shell/deploy-cloud-shell.sh --inputs ~/aegis-private/target.json
```

Add `--check-only` for read-only preflight. This uses Podman and existing Cloud Shell storage, with native architecture and remaining free-hour checks. Python 3.12 is supplied by Cloud Shell; DB object creation also needs the pinned Oracle driver in a private tool environment. See pages 15-16 of the final PDF for source checkout, kubeconfig, private wallet/registry login and input preparation. This is the OCI Cloud Shell route; OCI DevOps managed build runners are not enabled. Cloud Shell compute is free within the tenancy allowance; existing hosting and registry storage retain their own pricing and limits. No paid fallback or new infrastructure is created.

**Current Mumbai limitation (16 October 2026):** the existing OKE API access rules reject Cloud Shell's public connection. The user chose to keep all network settings unchanged. The route therefore cannot complete a release to this cluster from the current Cloud Shell session; a successful target preflight remains mandatory. No firewall exception, registry push, database DDL or workload rollout was performed while preparing this route.

The JSON controls each component with `"Y"` or `"N"`: `DB_Object`, `DeployFrontend`, and `DeployBackend`. Backend includes API and worker. `DB_ReleaseFile` selects the ordered database manifest, normally [ags_database/release.json](ags_database/release.json). Matching objects are skipped, missing supported objects are created, and incompatible existing definitions stop the release. The manifest can explicitly permit a missing application user/schema inside the existing database; existing accounts and settings are preserved. This does not create the physical Oracle database, provision OCI infrastructure, import data or run arbitrary migrations.

Type `CONNECT` to permit read-only target discovery, then review the exact source, target, missing DB objects and selected images before typing `PUBLISH`. Add `-CheckOnly` for read-only preflight without builds, DDL, pushes or rollout. The Windows command snapshots saved local application/database source by default, including new non-ignored source files; no Git commit or JSON `Ref` update is required. Add `-CommittedSource` to use the committed JSON `Ref` instead. See the [Windows setup and deployment README](ags_deploy/README.md) for the two-script colleague workflow. OCI Cloud Shell continues to use committed source. Keep secrets out of JSON and use private password prompts. A backup reference is optional and is not prompted for. Tests are not run by this command; supply truthful source validation evidence.

For AI-assisted deployment, use [aegis-deploy](.agents/skills/aegis-deploy/SKILL.md), supply the same target inputs and selected components, and approve discovery and the detailed release plan separately. The final PDF contains the complete request to give the AI. The [aegis-release skill](.agents/skills/aegis-release/SKILL.md) covers source freezes and handover maintenance.

Existing Deployments, database access, state, storage, Secrets, reranker/model assets and HTTPS routing must already be prepared. An empty tenancy or bare OKE cluster is insufficient. The release preserves configuration and model registrations; the existing Recreate strategy can briefly interrupt service when images change. Inspect the exact printed record/receipt after failure; no automatic retry or rollback is provided.

## Source and documentation

Application source is under `ags_backend/` and `ags_frontend/`; native Oracle scripts are under [ags_database](ags_database/README.md); maintained release/authentication tools are under `ags_deploy/`. Local launchers and alternative runtime manifests are grouped under [ags_local_use](ags_local_use/README.md). Tests, fixtures and manual QA tools are centralized under [ags_testing](ags_testing/README.md). Preserve the [Unified Chat workflow](AGENTS.md).

`ags_docs/` contains one deployment PDF and the architecture handover in Word/PDF with its approved diagram. Superseded guides are archived under root `delete/` with their original paths. This archive stays outside application builds and active test discovery. Private state, generated reports, wallets and release records stay out of Git.

The release Dockerfiles retain immutable live-matching Python 3.12.15 and Node.js 22.23.3 base digests and committed dependency locks. The OCI backend profile includes the existing Oracle/OCI and native AWS/Google SDKs, with local in-process embeddings disabled. Model files, mappings, endpoints and runtime configuration are preserved. Documentation and branch pushes do not deploy the running application.

## Backend dependencies and manual tests

Use Python 3.12. `ags_backend/requirements.txt` contains the pinned shared runtime, including OCI and CPU reranking. Optional Oracle, native cloud-provider and local-embedding dependencies remain in their named runtime requirements files. Test dependencies live in `ags_testing/backend/requirements.txt`.

Run backend tests from the repository root in PowerShell (`py -3.12 -m venv .venv` once if needed):

```powershell
.\.venv\Scripts\python.exe -m pip install -r ags_testing\backend\requirements.txt
.\.venv\Scripts\python.exe -B ags_testing\run_backend_tests.py
```

The runner uses temporary SQLite storage and mock providers in a child process, clearing inherited cloud settings and opt-in integration flags. For one file, append `backend/test_api_documentation.py -v`. Frontend checks retain their `npm run test:*` and `typecheck` commands. See the [testing guide](ags_testing/README.md) for all commands and opt-in integrations. Application startup checks stay with runtime code. These isolated tests do not deploy or access live OCI.
