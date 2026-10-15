# Aegis architecture and engineering handover

Freeze reference: `aegis-freeze-2026-10-15`. Prepared for Swamy on 15 October 2026.

## Aegis architecture and engineering handover

Prepared for Swamy on 15 October 2026. This handover explains what Aegis does, how its components work together, the versions declared by the frozen source, and how an operator can install, release and support it.

Aegis is a document knowledge and structured extraction workspace. Users upload documents, map models to datasets, extract fields with a saved JSON Schema, review saved results against the original, export them, and ask questions with source citations.

The handover freezes the existing python branch under tag aegis-freeze-2026-10-15. The Git tag identifies the complete source snapshot. Application source hashes are recorded in RELEASE-MANIFEST.json. This repository push does not deploy code or change the running OCI application.

The documented OCI topology runs the web app, API and worker on OKE, with Oracle metadata and vectors and OCI Object Storage outside the cluster. The recorded pilot uses laptop-hosted Ollama models through a private SSH relay. Other registered providers are configuration options, not evidence that those services are deployed.

| Reading order | Purpose |
| --- | --- |
| Architecture diagram and components | Understand hosting boundaries and responsibilities |
| Workflow and version inventory | Understand document processing, answers and dependencies |
| Deployment and operations | Install or release safely and recover failures |
| Release evidence and source map | Inspect validation and find the implementation |

Scope of evidence: source, lockfiles and existing deployment records. This handover does not claim a new live deployment, current cloud billing, current provider availability, or a fresh cloud installation test.

## Application architecture

![Aegis deployment architecture](ags_assets/aegis-architecture.png)

The browser uses the web application. Its same-origin /api proxy forwards to internal FastAPI. Application code, rather than the browser, accesses the database, content storage and model endpoints.

The OCI renderer defines two one-replica Recreate deployments. The web deployment contains Next.js and the Caddy TLS sidecar. The backend deployment contains API, worker and model-relay containers sharing persistent application state. This arrangement is a single-instance pilot and is not a high-availability design.

In the recorded pilot, one ARM64 A1 worker has 2 OCPUs and 12 GB RAM. Application and HTTPS PVCs each request 50 Gi. These are dated deployment facts, not general sizing requirements or confirmation of current live capacity.

## Components and data responsibilities

SQL metadata and durable content are authoritative. A vector hit is a discovery result; the application rehydrates and verifies the current authorized source before using it. Saved result versions and original files remain available for review.

The OCI object cache is bounded to 64 MiB, 2048 entries and 4 MiB per entry. It caches eligible application JSON and guards uncertain writes. Original bytes and Parquet bypass it. It relies on the current shared-volume and single-writer deployment contract.

| Component | Responsibility and boundary |
| --- | --- |
| Next.js web app | Login, workspace navigation, agents, uploads, templates, Review, exports and administration. Server API routes proxy to FastAPI. |
| FastAPI | Authentication, authorization, request validation, dataset and document scope, model registration, workflow planning and persisted result access. |
| LangGraph agents | Coordinate read tools and confirmed processing proposals. Uploaded text cannot grant tool permissions or change system rules. |
| Durable Python worker | Claims persisted jobs, parses or OCRs documents, embeds and indexes content, performs extraction and publishes results. Browser closure does not cancel accepted work. |
| Relational database | Users, sessions, datasets, model mappings, document and prompt references, extraction/review metadata and durable job state. |
| Content storage | Original documents, parsed text, schemas, versioned JSON and Parquet results, conversations and graph checkpoints. Routes pin the destination. |
| Knowledge index | Published document, catalog and saved-result knowledge. Oracle native vectors in the recorded OCI setup; Qdrant in local profiles. |
| Reranker | CPU ONNX inference over retrieved candidates. Production chat requires the configured local model files. |
| Models | Embedding, Chat and Extraction registrations map to each dataset. OCR is separately configured or follows a supported dataset provider path. |
| Shared state and cache | Encrypted configuration, locks, routes, archives, model files and bounded OCI JSON cache. API and worker must share the state volume. |

## End to end document workflow

A ready indexed document means it can be searched; it does not mean extraction has completed. A completed result must have its durable artifacts and knowledge publication saved before the application announces completion.

Independent mode preserves a separate result per document. Combined processing retains source associations and can preserve separate records inside a merged result. Selecting only one original must not expose an unrelated merged result.

1. **Create access.** Create the first administrator with the installation bootstrap token. Administrators create users and dataset assignments; ordinary users see authorized datasets.

2. **Register and map models.** Test and save Embedding, Chat and Extraction registrations. Create a dataset and assign its roles. Registration identity, limits and provider settings determine execution.

3. **Save a prompt.** Upload or edit a prompt with a valid JSON Schema. Uploading the same filename saves a new version. A prompt file is distinct from a document to process.

4. **Confirm processing.** Select dataset, documents, prompt and independent or combined mode. Review the workflow proposal and any required external-processing consent before submitting.

5. **Persist and index.** Save unchanged original bytes, create job metadata and let the worker parse text or perform configured OCR. Preserve page and source references, chunk text, embed and publish knowledge.

6. **Extract fields.** Retrieve and rerank evidence for the saved schema, call the mapped Extraction model, validate the response, and save versioned JSON and Parquet with result and provenance references.

7. **Review and export.** Open saved fields alongside the original. Correct values and mark Reviewed to save and lock that result. Export saved JSON, CSV, Excel or Parquet. Unsaved edits are not export data.

8. **Reextract or recover.** Re-extract creates a separate result and retains earlier versions. Retry accepted processing instead of submitting duplicate work. Stale embeddings require a rebuild before reuse.

## How Unified Chat answers a question

Question answering does not authorize uploads, extraction, onboarding or other writes. Processing proposals keep the existing confirmation and consent boundaries. Conversation text is not published as unified knowledge.

Hybrid ranking is not a complete catalog. A ranked subset cannot establish an exact total. The current production chat contract in AGENTS.md takes precedence over older design documents describing earlier answer routes.

The runtime file sets application ceilings of 262144 context tokens, 1000000 UTF-8 evidence bytes and 1024 answer tokens. A saved model registration may impose smaller limits. These ceilings do not enlarge the provider model context window or guarantee that every maximum fits one request.

1. **Resolve access and scope.** Authenticate, determine question intent and enforce dataset, document and current user access before retrieving anything.

2. **Retrieve hybrid evidence.** Search published unified knowledge with both semantic vectors and keyword ranking. Aegis help also retrieves application guidance through this path.

3. **Rerank candidates.** Run configured CPU reranking while retaining access and scope filters. If required retrieval or reranking is unavailable, return the actual failure.

4. **Generate a grounded answer.** Pass the current question and required authorized evidence to the mapped model. Supplement exact lists and counts with complete authorized catalog facts.

5. **Validate and show sources.** Validate the generated answer and citations, resolve source identity and revision, and show recorded evidence. Do not invent field coordinates, stages or successful processing.

## Frontend and core backend versions

These are source-declared versions from package-lock.json, requirements.txt and the Dockerfiles. They are not a report of packages introspected from the running production containers. Use npm ci and the committed Python lockfiles for a release build.

The frontend package version is 1.0.0 and backend package version is 0.1.0. Neither package version alone identifies this release; use the Git freeze tag and the immutable image digest created by a future deployment.

| Layer | Version or release | Role |
| --- | --- | --- |
| Frontend package | 1.0.0 | Workspace UI |
| Node.js | 22.x Alpine base | Frontend build and server; patch floats |
| Next.js | 15.5.27 | App Router and API proxy |
| React and React DOM | 19.3.0 | Interactive screens |
| TypeScript | 5.9.3 | Static checking |
| Lucide React | 0.468.0 | Icons |
| PostCSS | 8.5.28 | CSS processing |
| Playwright | 1.63.0 | Browser checks |
| Backend package | 0.1.0 | API and durable worker |
| Python | 3.12 slim base; project >=3.11 | Backend runtime; image patch floats |
| FastAPI | 0.142.2 | HTTP API |
| Uvicorn | 0.54.0 | ASGI server |
| SQLAlchemy | 2.1.2 | Relational persistence |
| Pydantic | 2.13.5 | Input and response validation |
| LangGraph | 1.2.14 | Agent orchestration |
| LangGraph Checkpoint | 4.2.0 | Agent checkpoints |
| LangChain Core | 1.6.9 | Model and message contracts |
| PyArrow | 26.0.0 | Parquet artifacts and export |
| JSON Schema | 4.26.0 | Extraction contract validation |

## Storage platform and model versions

Default local Docker uses PostgreSQL and Qdrant. The Oracle local profile uses Oracle AI Database Free and Qdrant. The recorded OCI pilot uses an external Oracle database for metadata, the database job queue and native vectors; content lives in OCI Object Storage.

The recorded Ollama models are qwen3:4b for chat and extraction, nomic-embed-text for embeddings, and qwen2.5vl:3b for vision OCR. Model names and tags can move. Preserve each model registration, model digest, embedding dimension and indexing profile when reproducing results.

Optional local embeddings declare sentence-transformers 6.1.0, torch 2.14.1 and transformers 5.18.0. Optional native model adapters declare boto3 1.43.109 and google-auth 2.61.0. Build flags determine which optional packages enter the image.

Node 22 Alpine and Python 3.12 slim are moving image tags. Caddy and deployed app images are selected by digest in the private deployment release record. Capture digests and runtime patch versions during the next authorized release for byte-for-byte image provenance.

| Layer | Version or release | Role |
| --- | --- | --- |
| Oracle Python driver | 26.0.1 | Optional thin Oracle connectivity |
| OCI SDK | 2.187.2 | Optional OCI adapters |
| ONNX Runtime and tokenizers | 1.30.0 and 0.23.2 | Local CPU reranking |
| PostgreSQL local image | 17.11 Alpine | Default local metadata and queue |
| Qdrant local image | 1.19.1 | Local vector index |
| Oracle Free local image | 23.26.3.0 | Optional Oracle 26ai local profile |
| Ollama local image | 0.35.1 | Local model server |
| OKE pilot Kubernetes | v1.36.4 recorded 14 Oct | Historical platform record; verify before a future rollout |
| Caddy and SSH relay | Deployment digest / Alpine 3.23 relay base | TLS entry and restricted model tunnel |

## Local setup and first onboarding

1. **Choose one isolated environment.** For default local Docker, use local/compose.yaml. For the Windows Oracle and Ollama profile, run local/ags_scripts/start-oracle.ps1. Do not point a test installation at the deployed database or storage.

2. **Create private installation settings.** The default setup.sh creates a private .env with unique database, session, encryption and bootstrap secrets. The Oracle launcher creates its own .env.oracle and private credential files. Never commit those values.

3. **Start and inspect services.** Use the same Compose files, project directory and env file for every command. The default app listens on localhost:3000; the Oracle launcher defaults to localhost:3003. Check API, worker and database readiness.

4. **Configure real processing.** Supply a reachable supported model endpoint and local reranker files. Default generic reranking is disabled; local and oci runtime profiles expect /data/models/reranker. Test provider connections before a real document run.

5. **Bootstrap the administrator.** On the empty initialized application database, use the installation bootstrap token to create the first administrator. An existing sign-in page means users may already exist; verify the destination before changing state.

6. **Complete one onboarding check.** Register models, create and map a dataset, save a small schema prompt, upload harmless test content, wait for indexing, extract, review, export and ask a cited question.

```text
git clone --branch python https://github.com/Maniatramco/Aegis.git
cd Aegis
git checkout aegis-freeze-2026-10-15
# POSIX shell or WSL for the default local profile
./local/ags_scripts/setup.sh
docker compose --project-directory . --env-file .env -f local/compose.yaml up --build -d
```

The commands above start a separate local environment. They are documented instructions only; they were not executed against the existing deployment during this handover.

## OCI installation and application releases

A new OCI environment needs an explicit platform and application installation handoff before the release script can be used. Required items include cluster access, namespace, registry and pull credentials, database/schema, bucket, application encryption and bootstrap secrets, wallet, reranker files, persistent state and an HTTPS endpoint.

The historical ags_oke provisioning and rendering helpers are specific to the recorded pilot. They contain Mumbai and resource assumptions, read private runtime records, and the renderer verifies seeded existing OCI state. They are not a portable empty-cluster installer. Do not run them unchanged for a new tenancy.

For a prepared destination, ags_deploy/deploy-aegis-code.ps1 checks kubeconfig/context and expected deployments, builds the web and backend images for the selected architecture, pushes them, records previous image references, then rolls backend and frontend out by immutable digest. API and worker use the same backend digest.

The deployment script updates existing workloads. It does not create infrastructure, install secrets, initialize an empty application or run schema migrations. Its backend build disables local embedding and optional cloud-model packages, and enables Oracle/OCI packages. A native provider requiring additional model adapters needs a separately verified image build.

The backend uses Recreate, so an authorized future release can interrupt service. Finish active jobs and take a coordinated backup first. A failed release stops; it does not automatically undo earlier successful changes. Use the recorded previous image references for a compatible rollback.

```text
# From repository root, after destination preparation
$taskSource = (Get-Location).Path
$taskKubeconfig = 'C:\secure\destination-kubeconfig.yaml'
$taskContext = 'DESTINATION_CONTEXT'
# Full copyable deployment and rollback commands:
# ags_docs/DEPLOYMENT.md
```

Current handover constraint: preserve the deployed installation. No release script, kubectl apply/set image/scale, runtime apply, service restart, infrastructure provisioning or data mutation is part of this freeze.

## Configuration security and operations

Operational defaults live in ags_backend/ags_app/ags_config/runtime.toml. It defines units, bounds and default/local/oci profiles for chat, retrieval, reranking, OCR, uploads and worker retries. Saved per-model settings and explicit environment overrides can take precedence. Inspect effective values before a future configuration change.

Model registrations and dataset mappings are saved application settings. Encryption keys, database passwords, OCI credentials, wallets, session secrets and bootstrap tokens remain outside Git and images. Keep the installation master key stable across releases so saved credentials remain decryptable.

Account changes require administrator authorization and confirmation in the application. Deletion revokes sessions and dataset access, protects the current account and last administrator, retains shared content, and archives private history references under the protected shared state directory.

The laptop model relay pins the SSH host key and permits restricted reverse forwarding. The recorded destination is the internal ollama service on port 11434. Laptop Docker/Ollama and the tunnel must remain online for those models. Do not expose an unauthenticated model port publicly.

Back up relational state, durable objects, shared runtime state, model and route configuration, and separately protected encryption material. The local backup.sh script supports the local PostgreSQL/file profile; it is not an OCI Oracle restore solution. Test cloud recovery in an isolated destination.

An image rollback restores code only. It does not reverse schema, configuration or content changes. Restore only a compatible code and data combination. Preserve embedding profiles and rebuild derived indexes from verified durable sources when needed.

| Symptom | First diagnostic |
| --- | --- |
| Image pull or startup error | Check target architecture, registry pull secret, pod events and image digest |
| API or worker not ready | Check DB/wallet, encryption key, shared state and reranker mount |
| Model unavailable | Check registration, protocol, limits, endpoint and laptop relay |
| Document not searchable | Check indexing job, OCR and embedding profile; ready is separate from extraction |
| Result saved but workflow incomplete | Inspect publication failure; retry knowledge publication before rerunning inference |

## Release evidence and source navigation

The release evidence document records the actual checks for this snapshot. Historical screenshots and OCI deployment notes are dated observations, not a claim that this freeze was deployed. This handover does not run live extraction, user management, cloud rollout or restore drills.

A source freeze is represented by an immutable Git tag, not by preventing future development on the branch. Future work can advance the branch while this tag remains the handover reference. The source manifest fingerprints application and deployment inputs without including credentials or runtime data.

| Repository entry | What to inspect |
| --- | --- |
| README.md | Manager introduction, diagrams, workflow and documentation links |
| ags_docs/ARCHITECTURE.md | Text companion to this Word document |
| ags_docs/TECH-STACK.md | Exact declared dependencies and reproducibility limits |
| ags_docs/DEPLOYMENT.md | Fresh destination handoff, code release, onboarding and rollback |
| .agents/skills/aegis-release/SKILL.md | Reusable workflow for future Aegis maintainers |
| ags_docs/RELEASE-FREEZE.md | Freeze scope and actual validation results |
| ags_docs/RELEASE-MANIFEST.json | Source file hashes and aggregate fingerprint |
| ags_backend/ags_app/ags_agent/ | Chat graph, evidence, retrieval and validation |
| ags_backend/ags_app/worker.py | Durable processing execution |
| ags_database/ | Schema, migrations and relational model |
| ags_deploy/ags_oke/ | Existing OCI pilot tooling and runtime-config adapter |

Share the GitHub link with the freeze tag selected. Read the README first, then open the diagram and this Word document. Keep private installation configuration and deployment receipts in the operator handoff rather than the repository.
