# Aegis

Aegis turns documents into searchable knowledge and structured, reviewable results. It combines a Next.js workspace, a FastAPI API, LangGraph agents and a durable Python worker. Users upload files, extract fields with saved JSON Schema prompts, compare results with originals, export saved data and ask questions with source citations.

**Manager handover:** prepared for Swamy on 15 October 2026. Use tag **`aegis-freeze-2026-10-15`** for this complete source snapshot. Publishing this snapshot does not deploy it or change the running application. See [freeze and validation](ags_docs/RELEASE-FREEZE.md).

## Start here

| Read | What it explains |
| --- | --- |
| [Word handover](ags_docs/Aegis_Architecture_and_Deployment_Handover.docx) | End to end architecture, workflows, versions, installation, release and support |
| [Architecture](ags_docs/ARCHITECTURE.md) | Browser to API, worker, data and model boundaries |
| [Technology versions](ags_docs/TECH-STACK.md) | Exact source-declared versions and image/model reproducibility limits |
| [Deployment and onboarding](ags_docs/DEPLOYMENT.md) | Fresh installation prerequisites, local setup, OCI code release and rollback |
| [Maintainer skill](.agents/skills/aegis-release/SKILL.md) | Reusable repository-specific release and support instructions |
| [Source manifest](ags_docs/RELEASE-MANIFEST.json) | Frozen application input hashes |

## Architecture

![Aegis deployment architecture](ags_docs/ags_assets/aegis-architecture.png)

The browser talks to Next.js. Its same-origin API proxy calls internal FastAPI; the API enforces access and delegates confirmed processing to the worker. The recorded OCI pilot places web/API/worker on OKE, metadata and native vectors in external Oracle, and durable content in OCI Object Storage. Laptop-hosted Ollama models are reached through a restricted private SSH relay. Local Docker uses PostgreSQL/Qdrant, or the optional Oracle profile.

The recorded OKE deployment is a single-instance pilot with shared state and Recreate rollouts. Cloud services, model providers and model registrations are configuration choices; a supported adapter does not prove that service is currently deployed.

## End to end workflow

1. Bootstrap an administrator; create users and dataset assignments.
2. Register Embedding, Chat and Extraction models, then create a dataset and map its roles.
3. Save a JSON Schema prompt and upload documents after confirming the workflow and any required processing consent.
4. The worker saves originals, parses or OCRs content, chunks, embeds and indexes it.
5. Extraction retrieves and reranks evidence, generates schema-conforming fields and saves versioned JSON/Parquet.
6. Review compares fields with the source. Marking **Reviewed** saves and locks that result. Re-extract preserves earlier results.
7. Export saved results or ask a cited question over authorized knowledge.

**Unified Chat contract:** access and scope → hybrid vector/keyword retrieval → CPU reranking → model answer → answer and citation validation. This applies to every question, including Aegis help and catalog questions. Exact counts require complete authorized catalog facts. Questions do not authorize processing. See [AGENTS.md](AGENTS.md).

## Technology at this freeze

| Area | Declared versions |
| --- | --- |
| Web | Node 22.x, Next.js 15.5.27, React 19.3.0, TypeScript 5.9.3 |
| API and agents | Python 3.12 image, FastAPI 0.142.2, LangGraph 1.2.14, SQLAlchemy 2.1.2 |
| Data | Oracle driver 26.0.1; local PostgreSQL 17.11, Qdrant 1.19.1; PyArrow 26.0.0 |
| Models | Recorded pilot: qwen3:4b, nomic-embed-text, qwen2.5vl:3b via Ollama |
| Verification | pytest 9.1.1, Node unit tests, Playwright 1.63.0, TypeScript and Next build |

Use lockfiles for exact dependencies. Base-image tags do not pin runtime patch versions; future release receipts must record image digests and actual model identities. See the [full inventory](ags_docs/TECH-STACK.md).

## Run a separate local installation

Requires Docker with Compose v2 and Python 3 for the default secret-generation helper. Use a POSIX shell or WSL:

```sh
git clone --branch python https://github.com/Maniatramco/Aegis.git
cd Aegis
git checkout aegis-freeze-2026-10-15
./local/ags_scripts/setup.sh
docker compose --project-directory . --env-file .env -f local/compose.yaml up --build -d
```

Open `http://localhost:3000` and create the first administrator using the private installation bootstrap token. Configure reachable models and a reranker before real processing. Generic default reranking is disabled; the `local` and `oci` runtime profiles expect local reranker files. For the Windows Oracle/Ollama option, follow [Oracle setup](ags_docs/ORACLE.md); its launcher defaults to port 3003. Keep any new installation isolated from deployed data.

## Deployment and operations

Read [DEPLOYMENT.md](ags_docs/DEPLOYMENT.md) before running commands. `ags_deploy/deploy-aegis-code.ps1` updates already prepared OKE application workloads. It is not an empty-cluster installer. The historical provisioning/renderer helpers are pilot-specific and require private state; do not reuse them unchanged for another tenancy.

Runtime limits and profiles live in [runtime.toml](ags_backend/ags_app/ags_config/runtime.toml), explained in [runtime configuration](ags_docs/RUNTIME-CONFIG.md). Model registrations remain authoritative for model-specific limits. Keep encryption keys, bootstrap tokens, wallets and credentials outside Git and images. The laptop relay must remain online for the recorded local models.

Use the same Compose configuration arguments for stop/start operations and preserve volumes. [Backup and restore](ags_docs/BACKUP_RESTORE.md) explains coordinated recovery; its local scripts are not a cloud Oracle backup system. Image rollback does not roll back data or schema changes.

## Repository map

| Path | Responsibility |
| --- | --- |
| `ags_backend/ags_app/` | FastAPI, authorization, agents, worker and provider/storage adapters |
| `ags_backend/ags_tests/` | Backend regression and opt-in integration checks |
| `ags_frontend/app/` | Next.js screens, components, styling and API proxy |
| `ags_frontend/ags_tests/` | Frontend unit and browser checks |
| `ags_database/` | Oracle schema, migrations and SQL administration |
| `ags_deploy/` | Image release script, Kubernetes and recorded OKE pilot tooling |
| `ags_scripts/` | Backup, restore, smoke and QA utilities |
| `ags_docs/` | Architecture, Word handover, deployment and operating guides |
| `local/` | Laptop Compose profiles, environment templates and launchers |

The `python`, `webui` and `database` branches contain the full repository; their names do not filter folders. This handover freezes `python`. It does not merge component branches or change `main`.

## Development checks

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r ags_backend/requirements-dev.txt
(cd ags_backend && pytest -q)
(cd ags_frontend && npm ci && npm run test:unit && npm run typecheck && npm run build)
```

Compose/browser and real-model tests require a separate authorized environment. Current CI auto-runs on `main` pushes and pull requests; a direct `python` push is not a fresh CI result. Consult [freeze evidence](ags_docs/RELEASE-FREEZE.md) for this snapshot's checks and [all documentation](ags_docs/README.md) for deeper references.
