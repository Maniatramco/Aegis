# Aegis

A document knowledge and structured extraction workspace with a Next.js web app,
FastAPI API, LangGraph agents and a durable Python worker. Administrators configure
local or OCI file storage, database and vector knowledge destinations.

## Project layout

| Directory | Contents |
| --- | --- |
| `ags_backend/ags_app/` | API, agents, worker, authorization and provider/storage adapters |
| `ags_backend/ags_tests/` | Automated backend regression and integration tests |
| `ags_frontend/app/` | Web pages, shared components and styles |
| `ags_frontend/ags_tests/` | Unit tests and Playwright browser scenarios |
| `ags_database/` | Oracle schema, generated DDL, migrations and SQL queries |
| `ags_deploy/` | Kubernetes manifests and deployment preparation |
| `ags_scripts/` | Setup, development, backup, restore and operational utilities |
| `ags_scripts/ags_qa/` | Manual benchmarks and recorded verification helpers |
| `ags_docs/` | Architecture, configuration, runbooks and historical verification |

Compose files stay at the root. Runtime data, credentials, model weights and
generated verification output are ignored by Git.

Custom source folders use `ags_` prefixes. Next.js `app`, `public` and URL route
folders, `.github/workflows` and dependency/cache directories retain their required
names. New screenshots go under ignored `ags_runtime/ags_screenshots`; existing
local data, credentials, caches and historical evidence stay in their original
locations. This reorganization does not change saved storage references.

## Component branches and integration

All three component branches contain this complete repository:

| Branch | Primary responsibility |
| --- | --- |
| `database` | `ags_database`: schema, indexes, migrations and SQL administration |
| `python` | `ags_backend`: FastAPI, agents, worker and database/provider access |
| `webui` | `ags_frontend`: screens, components and FastAPI proxy |

Merge component changes into `feat/aegis-assistant-oracle-docker` before an
integrated release. Shared Compose, CI, deployment and documentation changes must
be reconciled there. Branch names do not limit which folders Git contains; use
the component Docker build contexts below to separate application images.

```sh
docker build -t aegis-api ./ags_backend
docker build -t aegis-worker ./ags_backend
docker build -t aegis-web ./ags_frontend
```

API and worker share the Python image and run different commands (`uvicorn
ags_app.main:app --host 0.0.0.0 --port 8000` and `python -m ags_app.worker`).
Neither image includes `ags_database` installation scripts. Oracle drivers,
connections, ORM mappings, runtime queries and existing automatic schema setup
remain in Python. Storage's table-creation action remains available.

The connection boundary stays WebUI → FastAPI → OCI Oracle. OKE application
hosting should use the external OCI database, object storage and vectors; do not
deploy the local database services from the development Kubernetes base to OKE.
Cloud provisioning and schema migration remain separate operator actions.

## Run locally

Requirements: Docker Engine/Desktop with Compose v2 and Python 3 for one-time
secret generation. Windows users can run shell setup in WSL or follow
[the Windows/Ollama guide](ags_docs/OLLAMA.md).

```sh
git clone https://github.com/Maniatramco/Aegis.git
cd Aegis
./ags_scripts/setup.sh
docker compose up --build -d
```

Open **http://localhost:3000**. Read `AEGIS_BOOTSTRAP_TOKEN` from your private `.env`
and create the first administrator. The Oracle/Ollama Compose variant has a
separate [setup guide](ags_docs/ORACLE.md); use that guide's port and Compose arguments.
Credentials are encrypted with `AEGIS_MASTER_KEY`; keep that key and wallet/key
mounts with your private deployment backups.

## Onboard and use a dataset

1. Register Embedding, Chat and Extraction models in **Manage workspace → Model Registration**.
2. Create a dataset in **Onboard → Dataset**, then assign its three roles in
   **Manage workspace → Model Mapping**.
3. Upload a JSON-schema prompt in **Onboard → Prompt** and documents into the
   dataset. Indexing must finish before retrieval or extraction.
4. Ask questions in **Aegis Agent**, or use `@Onboard`, `@Upload`, `@Extract` and
   `@ReExtract` for explicit workflows. Confirm the proposed inputs; external
   processing approval appears when the configured providers require it.
5. **Review** compares saved fields with the original. Marking a result
   **Reviewed** locks that version. **Extract** displays rows/columns and exports.

Dataset creation, model mapping, prompt setup and upload/extraction can also run
directly from Aegis Agent. See [onboarding](ags_docs/AGENT-ONBOARDING.md) and
[model configuration](ags_docs/MODEL_CONFIGURATION.md).

## Data and agents

The workspace has eleven menu pages: Home, Aegis Agent, Dataset, Prompt, Extract,
Review, Model Registration, Model Mapping, Storage, Users & passwords, and
Jobs & activity. The separate results/PDF Review detail is the twelfth screen.
Login and password recovery remain available outside the workspace. Old Document
Chat links open Aegis Agent; Connections and Services & migration links open
Storage, whose Advanced connections section retains required provider and
processing controls. Dashboard links open Home.

SQL holds control/access metadata and file references. Originals, parsed text,
prompts and extraction JSON/Parquet artifacts use their pinned file destination.
Published unified knowledge contains metadata, source chunks and extracted values,
with embedding vectors in Oracle native vectors or Qdrant. Chat retrieves scoped
evidence with current authorization and revision checks. Only the current question
and required evidence enter the model.

Write workflows save artifacts and publish knowledge before announcing completion.
Embedding model changes require reindexing. File/database/knowledge destinations
are configured in **Manage workspace → Storage**. See
[storage configuration](ags_docs/STORAGE-CONFIGURATION.md),
[unified knowledge](ags_docs/UNIFIED-KNOWLEDGE.md) and [Chat Agent](ags_docs/CHAT-AGENT.md).

## Development and verification

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r ags_backend/requirements-dev.txt
(cd ags_backend && pytest -q)
(cd ags_frontend && npm ci && npm run test:unit && npm run typecheck && npm run build)
./ags_scripts/local-smoke.sh
```

CI runs backend tests, all frontend unit tests, type checking/build, a real CPU
embedding image check and isolated Compose/browser scenarios. Mock tests verify
workflow behavior; real-model benchmarks are separate manual checks in
[manual QA tools](ags_scripts/ags_qa/README.md). Historical reports do not guarantee the current
revision passes; consult current CI results.

## Operations and deployment

Use `docker compose stop` and `docker compose start` with the same configuration
arguments to preserve data. The [backup runbook](ags_docs/BACKUP_RESTORE.md) covers
consistent backups and explicit destructive restore. Keep volumes when stopping
an installation you intend to retain.

OCI storage/database/vector adapters are implemented. OKE hosting still requires
operator-provisioned infrastructure, identity policies, shared runtime storage and
an OCI-specific configuration. The existing Kubernetes base includes local
dependencies. AI model hosting remains a separate configuration decision. See
[Kubernetes](ags_docs/KUBERNETES.md) and the [documentation index](ags_docs/README.md).

Do not include passwords, private keys or confidential documents in public issues.
