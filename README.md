# Aegis

Aegis turns documents into searchable knowledge and structured, reviewable results. It uses a Next.js interface, FastAPI, LangGraph agents and a durable Python worker.

**Final handover branch: `ags_sprint1`.** The source freeze remains tagged `aegis-freeze-2026-10-15`.

Read the architecture handover in [Word](ags_docs/Aegis_Architecture_and_Deployment_Handover.docx) or [PDF](ags_docs/Aegis_Architecture_and_Deployment_Handover.pdf). It includes the recently finalized Mural diagram, end-to-end workflows, verified OCI resources, deployed technology versions and model placement.

Use the dedicated [OCI Kubernetes deployment guide](ags_docs/Aegis_OCI_Kubernetes_Deployment_Guide.docx) for destination setup requirements, cluster access, registry configuration, application release, verification and rollback.

For Oracle Autonomous AI Database creation, wallet and user setup, schema deployment and verification, follow the [database-only deployment PDF](ags_docs/Aegis_OCI_Database_Deployment_Guide.pdf).

The live inspection on 15 October 2026 at 22:26 IST confirmed OKE hosting the web app, API, worker and CPU reranker; Oracle Autonomous AI Database 26ai storing records, the durable queue and native vectors; and OCI Object Storage holding documents and saved results. The three active datasets use Google Gemini. Laptop Ollama is a retained, stopped alternative.

Application source is under `ags_backend/` and `ags_frontend/`; Oracle scripts under `ags_database/`; OCI release tooling under `ags_deploy/`. Local launchers, Compose profiles, test containers, alternative Kubernetes manifests and manual QA tools are grouped under [ags_local_use](ags_local_use/README.md). Component tests remain beside their application source.

Normal code updates use `ags_deploy/deploy-aegis-code.ps1`. For a fresh schema on another OCI Autonomous Database, follow the [database installation instructions](ags_database/README.md#deploy-the-schema-to-another-oci-database); the installer checks the explicit owner/service and requires an empty schema. Historical resource provisioning and pilot registry setup are consolidated in `ags_deploy/ags_oke/ags_legacy_provisioning.py`.

The reusable [release skill](.agents/skills/aegis-release/SKILL.md) remains discoverable by AI tools. It requires a prepared destination and explicit deployment instructions. Preserve the [Unified Chat workflow](AGENTS.md).

Earlier guides and verification reports remain in Git history at documentation commit `a33d5fb`. `ags_docs/` contains the handover in Word/PDF, the dedicated application deployment guide and one database deployment PDF. The architecture diagram stays embedded in the handover. Reusable QA inputs live under `ags_local_use/ags_qa/ags_fixtures/`. These repository changes do not deploy or change the running application.

## Backend dependencies and manual tests

Use Python 3.12. `ags_backend/requirements.txt` contains the pinned shared runtime, including OCI and CPU reranking. Install `requirements-oracle.txt` for Oracle connectivity, `requirements-models.txt` for optional native cloud providers, or `requirements-local.txt` for CPU local embeddings. Docker keeps the existing `INSTALL_LOCAL_EMBEDDINGS`, `INSTALL_CLOUD_MODELS` and `INSTALL_ORACLE` choices; `INSTALL_OCI` is accepted for compatibility because OCI is already included. Development dependencies are collected in `requirements-dev.txt`. The consolidation preserves the previous final package versions.

To run `ags_backend/ags_tests` manually, open PowerShell at the repository root. If `.venv` does not exist, create it once with `py -3.12 -m venv .venv`. Install the test dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r ags_backend\requirements-dev.txt
```

Then select temporary local state and mock providers in this PowerShell session:

```powershell
$env:AEGIS_STORAGE_ROOT = Join-Path $env:TEMP ("aegis-tests-" + [guid]::NewGuid())
$env:DATA_DIR = $env:AEGIS_STORAGE_ROOT
$env:DATABASE_URL = "sqlite://"
$env:DATABASE_PROVIDER = "sqlite"
$env:AEGIS_CONFIG_PROFILE = ""
$env:AEGIS_CONFIG_FILE = ""
$env:AEGIS_ALLOW_MOCK = "true"
$env:MODEL_PROVIDER = "mock"
$env:EMBEDDING_PROVIDER = "mock"
$env:SEARCH_PROVIDER = "local"
$env:STORAGE_PROVIDER = "local"
Get-ChildItem Env:AEGIS_TEST_* | Remove-Item
Set-Location ags_backend
..\.venv\Scripts\python.exe -B -m pytest ags_tests -q -p no:cacheprovider
```

For one file, replace `ags_tests` with `ags_tests/test_api_documentation.py`; append `::test_documentation_requires_login_and_returns_only_contract` to select one test. Add `-v` for individual test names. `passed` means success, `failed` needs investigation, and `skipped` normally identifies opt-in integrations. Oracle and real model tests require explicit `AEGIS_TEST_*` settings and their separate test services. The commands above use local temporary state and do not deploy or test against live OCI. Close this PowerShell session after testing.
