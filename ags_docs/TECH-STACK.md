# Aegis running technology and model placement

Verified 15 October 2026 at 22:26 IST through live OCI and container inspection.

| Running technology | Observed version | Location |
| --- | --- | --- |
| Oracle Autonomous AI Database | 26ai | OCI managed database |
| OKE Kubernetes | v1.36.4 | OCI Mumbai |
| Worker operating system | Oracle Linux Server 9.8 | OCI ARM64 node |
| Node.js | 22.23.3 | OCI web container |
| Next.js | 15.5.27 | OCI web container |
| React | 19.3.0 | OCI web container |
| Python | 3.12.15 | OCI API and worker image |
| FastAPI | 0.142.2 | OCI API container |
| LangGraph | 1.2.14 | OCI backend agent runtime |
| Caddy | 2.10.2 | OCI HTTPS sidecar |

## Current placement

| Runs where | Components currently used |
| --- | --- |
| OCI OKE | Next.js web app, Caddy HTTPS, FastAPI, LangGraph agents, durable worker and CPU reranker |
| OCI Autonomous AI Database | Application records, access, durable job queue and Oracle native vector knowledge |
| OCI Object Storage | Original documents, prompts, parsed content and saved JSON / Parquet results |
| Google cloud API | Gemini embeddings, chat, extraction and dataset-aware OCR for all three active datasets |
| Local laptop | Retained Ollama / Qwen / Nomic option; containers stopped and relay endpoint unreachable at the check |

## Models mapped to the three active datasets

| Role | Mapped model | Where it executes |
| --- | --- | --- |
| Embedding | gemini-embedding-2 | Google Gemini API |
| Chat | gemini-3.5-flash-lite | Google Gemini API |
| Extraction | gemini-3.5-flash-lite | Google Gemini API |
| OCR for mapped datasets | gemini-3.5-flash-lite | Google Gemini API |
| Candidate reranking | Configured CPU reranker | OCI API / worker; model files on shared state |

The local Ollama container is stopped and its relay endpoint is unreachable. The OCI CPU reranker runs on the OKE backend. No new inference call was made.
