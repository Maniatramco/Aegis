# Aegis

A document knowledge and structured extraction workspace with a Next.js web app,
FastAPI API, LangGraph agents and a durable Python worker. Administrators configure
local or OCI file storage, database and vector knowledge destinations.

## Project layout

| Directory | Contents |
| --- | --- |
| `backend/app/` | API, agents, worker, authorization and provider/storage adapters |
| `backend/tests/` | Automated backend regression and integration tests |
| `frontend/app/` | Web pages, shared components and styles |
| `frontend/tests/` | Unit tests and Playwright browser scenarios |
| `database/` | Oracle schema, generated DDL, migrations and SQL queries |
| `deploy/` | Kubernetes manifests and deployment preparation |
| `scripts/` | Setup, development, backup, restore and operational utilities |
| `scripts/qa/` | Manual benchmarks and recorded verification helpers |
| `docs/` | Architecture, configuration, runbooks and historical verification |

Compose files stay at the root. Runtime data, credentials, model weights and
generated verification output are ignored by Git.

## Run locally

Requirements: Docker Engine/Desktop with Compose v2 and Python 3 for one-time
secret generation. Windows users can run shell setup in WSL or follow
[the Windows/Ollama guide](docs/OLLAMA.md).

```sh
git clone https://github.com/Maniatramco/Aegis.git
cd Aegis
./scripts/setup.sh
docker compose up --build -d
```

Open **http://localhost:3000**. Read `AEGIS_BOOTSTRAP_TOKEN` from your private `.env`
and create the first administrator. The Oracle/Ollama Compose variant has a
separate [setup guide](docs/ORACLE.md); use that guide's port and Compose arguments.
Credentials are encrypted with `AEGIS_MASTER_KEY`; keep that key and wallet/key
mounts with your private deployment backups.

## Onboard and use a dataset

1. Register Embedding, Chat and Extraction models in **Model → Model Registration**.
2. Create a dataset in **Onboard → Dataset**, then assign its three roles in
   **Model → Model Mapping**.
3. Upload a JSON-schema prompt in **Onboard → Prompt** and documents into the
   dataset. Indexing must finish before retrieval or extraction.
4. Ask questions in **Aegis Agent**, or use `@Onboard`, `@Upload`, `@Extract` and
   `@ReExtract` for explicit workflows. Confirm the proposed inputs; external
   processing approval appears when the configured providers require it.
5. **Review** compares saved fields with the original. Marking a result
   **Reviewed** locks that version. **Extract** displays rows/columns and exports.

Dataset creation, model mapping, prompt setup and upload/extraction can also run
directly from Aegis Agent. See [onboarding](docs/AGENT-ONBOARDING.md) and
[model configuration](docs/MODEL_CONFIGURATION.md).

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
[storage configuration](docs/STORAGE-CONFIGURATION.md),
[unified knowledge](docs/UNIFIED-KNOWLEDGE.md) and [Chat Agent](docs/CHAT-AGENT.md).

## Development and verification

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
(cd backend && pytest -q)
(cd frontend && npm ci && npm run test:unit && npm run typecheck && npm run build)
./scripts/local-smoke.sh
```

CI runs backend tests, all frontend unit tests, type checking/build, a real CPU
embedding image check and isolated Compose/browser scenarios. Mock tests verify
workflow behavior; real-model benchmarks are separate manual checks in
[scripts/qa](scripts/qa/README.md). Historical reports do not guarantee the current
revision passes; consult current CI results.

## Operations and deployment

Use `docker compose stop` and `docker compose start` with the same configuration
arguments to preserve data. The [backup runbook](docs/BACKUP_RESTORE.md) covers
consistent backups and explicit destructive restore. Keep volumes when stopping
an installation you intend to retain.

OCI storage/database/vector adapters are implemented. OKE hosting still requires
operator-provisioned infrastructure, identity policies, shared runtime storage and
an OCI-specific configuration. The existing Kubernetes base includes local
dependencies. AI model hosting remains a separate configuration decision. See
[Kubernetes](docs/KUBERNETES.md) and the [documentation index](docs/README.md).

Do not include passwords, private keys or confidential documents in public issues.
