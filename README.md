# Aegis

Aegis turns documents into searchable knowledge and structured, reviewable results. It uses a Next.js interface, FastAPI, LangGraph agents and a durable Python worker.

**Final handover branch: `ags_sprint1`.** The source freeze remains tagged `aegis-freeze-2026-10-15`.

Read the architecture handover in [Word](ags_docs/Aegis_Architecture_and_Deployment_Handover.docx) or [PDF](ags_docs/Aegis_Architecture_and_Deployment_Handover.pdf). It includes the recently finalized Mural diagram, end-to-end workflows, verified OCI resources, deployed technology versions and model placement.

Use the dedicated [OCI Kubernetes deployment guide](ags_docs/Aegis_OCI_Kubernetes_Deployment_Guide.docx) for destination setup requirements, cluster access, registry configuration, application release, verification and rollback.

For Oracle Autonomous AI Database creation, wallet and user setup, schema deployment and verification, follow the [database-only deployment PDF](ags_docs/Aegis_OCI_Database_Deployment_Guide.pdf).

The live inspection on 15 October 2026 at 22:26 IST confirmed OKE hosting the web app, API, worker and CPU reranker; Oracle Autonomous AI Database 26ai storing records, the durable queue and native vectors; and OCI Object Storage holding documents and saved results. The three active datasets use Google Gemini. Laptop Ollama is a retained, stopped alternative.

Application source is under `ags_backend/` and `ags_frontend/`; Oracle scripts under `ags_database/`; OCI release tooling under `ags_deploy/`. Local launchers, runtime Compose profiles and alternative Kubernetes manifests are grouped under [ags_local_use](ags_local_use/README.md). Tests, fixtures, manual QA tools and test containers are centralized under [ags_testing](ags_testing/README.md).

Normal code updates use `ags_deploy/deploy-aegis-code.ps1`. For a fresh schema on another OCI Autonomous Database, follow the [database installation instructions](ags_database/README.md#deploy-the-schema-to-another-oci-database); the installer checks the explicit owner/service and requires an empty schema. Historical resource provisioning and pilot registry setup are consolidated in `ags_deploy/ags_oke/ags_legacy_provisioning.py`.

The reusable [release skill](.agents/skills/aegis-release/SKILL.md) remains discoverable by AI tools. It requires a prepared destination and explicit deployment instructions. Preserve the [Unified Chat workflow](AGENTS.md).

Earlier guides and verification reports remain in Git history at documentation commit `a33d5fb`. `ags_docs/` contains the handover in Word/PDF, the dedicated application deployment guide and one database deployment PDF. The architecture diagram stays embedded in the handover. Reusable QA inputs live under `ags_testing/qa/ags_fixtures/`. These repository changes do not deploy or change the running application.

## Backend dependencies and manual tests

Use Python 3.12. `ags_backend/requirements.txt` contains the pinned shared runtime, including OCI and CPU reranking. Optional Oracle, native cloud-provider and local-embedding dependencies remain in their named runtime requirements files. The existing Docker build choices and pinned package versions are preserved. Test dependencies live in `ags_testing/backend/requirements.txt`.

Run backend tests from the repository root in PowerShell (`py -3.12 -m venv .venv` once if needed):

```powershell
.\.venv\Scripts\python.exe -m pip install -r ags_testing\backend\requirements.txt
.\.venv\Scripts\python.exe -B ags_testing\run_backend_tests.py
```

The runner selects temporary SQLite storage and mock providers in a child process, clearing inherited cloud settings and opt-in integration flags. For one file, append `backend/test_api_documentation.py -v`. Frontend unit/browser checks retain their `npm run test:*` commands. See the single [testing guide](ags_testing/README.md) for the folder layout, all commands and opt-in integrations. Application startup checks remain with runtime code. These commands do not deploy or access live OCI.
