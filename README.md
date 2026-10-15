# Aegis

Aegis turns documents into searchable knowledge and structured, reviewable results. It combines a Next.js workspace, a FastAPI API, LangGraph agents and a durable Python worker. Users upload files, extract fields with saved JSON Schema prompts, compare results with originals, export saved data and ask questions with source citations.

**Manager handover:** use branch **`ags_sprint1`** for the updated live OCI architecture, verified 15 October 2026 at 22:26 IST. The original code freeze remains tagged `aegis-freeze-2026-10-15`. Documentation updates do not change the deployed application. See [live resources](ags_docs/OCI-LIVE-RESOURCES.md) and [freeze evidence](ags_docs/RELEASE-FREEZE.md).

## Start here

| Read | What it explains |
| --- | --- |
| [Word architecture handover](ags_docs/Aegis_Architecture_and_Deployment_Handover.docx) | Current cloud/local placement, OCI resources, deployed versions and workflows |
| [Architecture](ags_docs/ARCHITECTURE.md) | Browser to API, worker, data and model boundaries |
| [Running technologies](ags_docs/TECH-STACK.md) | Versions observed in running containers and live model mappings |
| [Live OCI resources](ags_docs/OCI-LIVE-RESOURCES.md) | Cluster, compute, Autonomous AI Database, storage, networking and resource limits |
| [Deployment and onboarding](ags_docs/DEPLOYMENT.md) | Fresh installation prerequisites, local setup, OCI code release and rollback |
| [Maintainer skill](.agents/skills/aegis-release/SKILL.md) | Reusable repository-specific release and support instructions |
| [Source manifest](ags_docs/RELEASE-MANIFEST.json) | Frozen application input hashes |

## Architecture

![Aegis deployment architecture](ags_docs/ags_assets/aegis-architecture.png)

The browser uses Next.js on OCI OKE through the OCI load balancer and Caddy HTTPS. FastAPI, LangGraph agents, the worker and CPU reranker also run on OKE. **Oracle Autonomous AI Database 26ai** (`agsora`) stores application records, the durable job queue and native vectors. OCI Object Storage (`mk-aegis`) stores documents and saved results.

**Current model placement:** all three active datasets use Google Gemini (`gemini-embedding-2` and `gemini-3.5-flash-lite`) for embeddings, chat, extraction and OCR. The retained laptop Ollama container is stopped and its relay endpoint is unreachable. The CPU reranker's `local` mode means execution inside the OCI backend.

The live cluster has one ARM64 A1 node with 2 OCPUs and 12 GB RAM. Both application deployments have one ready replica. See the [verified resource inventory](ags_docs/OCI-LIVE-RESOURCES.md) for allocations and the [snapshot](ags_docs/OCI-LIVE-SNAPSHOT.json) for deployed image references.

## End to end workflow

1. Bootstrap an administrator; create users and dataset assignments.
2. Register Embedding, Chat and Extraction models, then create a dataset and map its roles.
3. Save a JSON Schema prompt and upload documents after confirming the workflow and any required processing consent.
4. The worker saves originals, parses or OCRs content, chunks, embeds and indexes it.
5. Extraction retrieves and reranks evidence, generates schema-conforming fields and saves versioned JSON/Parquet.
6. Review compares fields with the source. Marking **Reviewed** saves and locks that result. Re-extract preserves earlier results.
7. Export saved results or ask a cited question over authorized knowledge.

**Unified Chat contract:** access and scope → hybrid vector/keyword retrieval → CPU reranking → model answer → answer and citation validation. This applies to every question, including Aegis help and catalog questions. Exact counts require complete authorized catalog facts. Questions do not authorize processing. See [AGENTS.md](AGENTS.md).

## Technologies observed live

| Running technology | Observed version | Location |
| --- | --- | --- |
| Oracle Autonomous AI Database | 26ai | OCI managed database |
| OKE Kubernetes | v1.36.4 | OCI Mumbai |
| Node.js | 22.23.3 | OCI web container |
| Next.js | 15.5.27 | OCI web container |
| Python | 3.12.15 | OCI API and worker image |
| FastAPI | 0.142.2 | OCI API container |
| LangGraph | 1.2.14 | OCI backend agent runtime |
| Caddy | 2.10.2 | OCI HTTPS sidecar |

These versions were read from the running deployment. See [running technologies and models](ags_docs/TECH-STACK.md).

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

Runtime limits and profiles live in [runtime.toml](ags_backend/ags_app/ags_config/runtime.toml), explained in [runtime configuration](ags_docs/RUNTIME-CONFIG.md). Model registrations remain authoritative for model-specific limits. Keep encryption keys, bootstrap tokens, wallets and credentials outside Git and images. The retained laptop model option requires its relay; the three currently active datasets use cloud Gemini mappings.

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
