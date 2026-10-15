# Aegis technology and version inventory

Recorded from the frozen source on 15 October 2026. Versions describe committed build inputs, not a new inspection of running OCI containers.

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
| Oracle Python driver | 26.0.1 | Optional thin Oracle connectivity |
| OCI SDK | 2.187.2 | Optional OCI adapters |
| ONNX Runtime and tokenizers | 1.30.0 and 0.23.2 | Local CPU reranking |
| PostgreSQL local image | 17.11 Alpine | Default local metadata and queue |
| Qdrant local image | 1.19.1 | Local vector index |
| Oracle Free local image | 23.26.3.0 | Optional Oracle 26ai local profile |
| Ollama local image | 0.35.1 | Local model server |
| OKE pilot Kubernetes | v1.36.4 recorded 14 Oct | Historical platform record; verify before a future rollout |
| Caddy and SSH relay | Deployment digest / Alpine 3.23 relay base | TLS entry and restricted model tunnel |

Default local Docker uses PostgreSQL and Qdrant. The Oracle local profile uses Oracle AI Database Free and Qdrant. The recorded OCI pilot uses an external Oracle database for metadata, the database job queue and native vectors; content lives in OCI Object Storage.

The recorded Ollama models are qwen3:4b for chat and extraction, nomic-embed-text for embeddings, and qwen2.5vl:3b for vision OCR. Model names and tags can move. Preserve each model registration, model digest, embedding dimension and indexing profile when reproducing results.

Optional local embeddings declare sentence-transformers 6.1.0, torch 2.14.1 and transformers 5.18.0. Optional native model adapters declare boto3 1.43.109 and google-auth 2.61.0. Build flags determine which optional packages enter the image.

Node 22 Alpine and Python 3.12 slim are moving image tags. Caddy and deployed app images are selected by digest in the private deployment release record. Capture digests and runtime patch versions during the next authorized release for byte-for-byte image provenance.

Source of truth: `ags_frontend/package-lock.json`, backend `requirements*.txt` and `requirements*.lock`, component Dockerfiles, local Compose manifests and the dated OCI deployment record. The requirements lockfiles contain the full transitive inventory.
