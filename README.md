# Aegis

A storage-first document knowledge and structured extraction workspace. Aegis runs on your laptop using Docker Compose: Next.js, FastAPI, a durable Python worker, PostgreSQL control records, Qdrant vectors, and persistent file storage.

## Run locally

Requirements: Docker Engine/Desktop with Compose v2, Python 3 for one-time secret generation, and enough memory/disk for the optional local embedding model. Docker Desktop may require virtualization enabled. Windows users can run these commands in WSL.

```sh
git clone https://github.com/Maniatramco/Aegis.git
cd Aegis
./scripts/setup.sh
docker compose up --build -d
```

Open **http://localhost:3000**. Read `AEGIS_BOOTSTRAP_TOKEN` from your private `.env`, then create the first administrator in the setup screen. Choose a strong unique password. In Settings, enter your own OpenAI API key to enable answering and extraction. Keys are encrypted in server-side storage using `AEGIS_MASTER_KEY`; they are never returned to the browser after saving. Keep `.env` safe and back it up separately: losing the master key makes stored credentials unrecoverable.

Only the web app is published, bound to `127.0.0.1`. PostgreSQL and Qdrant have no published ports. Do not expose this local-first application to the Internet without a TLS reverse proxy and an independent security review.

### First dataset

1. Configure provider connections and save a named connection profile. Register the chat, extraction, and embedding models you want to use.
2. Onboard a dataset, map its eligible models, and choose the default chat/extraction models and indexing configuration.
3. Upload text-based PDF, DOCX, or TXT documents from Datasets, or use the attachment button / drag-and-drop in Ask Aegis after selecting a dataset. Both entry points use the same storage-first upload and indexing workflow. Review files and any external-processing notice, then choose Upload. Watch indexing progress; documents become available to questions only when ready. The local embedding model downloads on first use.
4. In Ask Aegis, select the dataset and an eligible model. With multiple mapped models, the model dropdown lets you choose which one answers. Sources link answers to stored chunks.
5. In Extract, select the dataset, mapped extraction model, documents, and JSON-schema template. Review the structured output and export JSON/CSV.

See [dataset configuration and existing-workspace migration](docs/DATASETS.md). A dataset with no eligible mapped model gives configuration guidance instead of silently using a global model.

Scanned/image-only PDFs require OCR first. Aegis does not silently invent OCR text. OpenAI chat/extraction sends the selected source content and your prompt to OpenAI after the UI's external-processing acknowledgment. OpenAI embeddings also send chunks when selected. API use is billed separately by the provider. Local embeddings keep document text local during indexing; downloading model weights still requires network access.

### Free local inference with Ollama

For native Windows development with local chat, extraction, and embeddings, see
[the Ollama setup guide](docs/OLLAMA.md). It uses SQLite and local file search,
with cloud features and paid providers disabled. Ollama model downloads are separate
from application dependencies; no OpenAI API key or subscription is required.

## Storage-first architecture

Originals, parsed text, chunks, conversations, templates and extraction artifacts live in persistent filesystem storage. SQL stores only control/access metadata and references. Qdrant stores vectors plus identifiers/filter metadata; retrieved source text is read from storage. Configuration export excludes credentials. Indexes are disposable and rebuildable; changing embedding models requires reindexing.

See [architecture](docs/ARCHITECTURE.md), [provider capability and migration guide](docs/OCI_READINESS.md), and the runbooks in `docs/`.

## Operations

```sh
docker compose logs -f api worker
docker compose stop                 # Preserve all data
docker compose start
./scripts/backup.sh                 # Cold, consistent backup; briefly stops writers
# Destructive restore: use only against a deployment you intend to replace
./scripts/restore.sh backups/TIMESTAMP --confirm-overwrite
```

Never run `docker compose down -v` unless you intend to destroy all deployment volumes. Restore requires the original master key and reindexing all documents; see the backup runbook. Keep backups private: they contain original documents and conversation contents.

## Development and verification

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
(cd backend && pytest -q)
(cd frontend && npm ci && npm run typecheck && npm run build)
./scripts/local-smoke.sh  # Mock providers, SQLite + file search, no paid API calls
```

GitHub Actions runs backend tests, frontend type checking/build, and a Compose-backed integration smoke test using the explicitly gated mock model and embedding providers plus real PostgreSQL/Qdrant. Mock mode is for testing only and does not demonstrate model answer quality or live API access. The ordinary deployment defaults to OpenAI generation and local Sentence Transformers embeddings. For a lighter test build, CI sets INSTALL_LOCAL_EMBEDDINGS=false; the default laptop image installs CPU-only PyTorch. Runtime transitive dependencies are pinned in backend/requirements.lock and backend/requirements-local.lock.

See [the verification record](docs/VERIFICATION.md) for passed checks and explicit unrun stages.

## OCI migration status

This release's supported deployment is local Compose. OCI migration is **not an endpoint-only switch**. It requires provisioned services, service-specific adapters, identity policies, migration validation and reindexing. Implemented adapters cover OCI Object Storage, Queue, and Enterprise AI Responses and managed vector stores. Settings expose provider and destination configuration; credential-free SDK/HTTP contracts are tested. Existing content is moved with a checksum-verified, writer-stopped migration tool before activation. OCI PostgreSQL uses the configured SQLAlchemy database URL; OKE deployment still needs operator-provisioned infrastructure and secrets. No live OCI tenancy or OpenAI API account is claimed as tested. See [migration steps](docs/OCI_MIGRATION.md).

## Security reporting

Do not post secrets or confidential documents in public issues. Rotate any accidentally exposed API key immediately. This project does not include production Internet-hosting hardening or compliance certification.
