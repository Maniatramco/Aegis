# Aegis live OCI resource inventory

Verified 15 October 2026 at 22:26 IST. Access used the configured OCI identity; no resources were changed.

| OCI resource | Live configuration | Observed state |
| --- | --- | --- |
| Region and tenancy | Mumbai ap-mumbai-1; maniatramco | Authenticated access |
| OKE cluster | ags-aegis-basic; Basic; Kubernetes v1.36.4 | ACTIVE |
| Node pool | ags-aegis-a1-node-pool; 1 node | ACTIVE |
| Compute | VM.Standard.A1.Flex; ARM64; 2 OCPUs; 12 GB RAM | RUNNING / Ready |
| Autonomous AI Database | ags_ora_db / agsora; Oracle 26ai; 1 ECPU; 20 GB | AVAILABLE |
| Database configuration | Free Tier flag true; compute/storage autoscaling off; mTLS required | Read connection verified |
| Object Storage | mk-aegis; Standard; namespace bmyljaecivrj | Read configuration verified |
| Public load balancer | 92.4.67.183; flexible 10 Mbps minimum and maximum | ACTIVE |
| Application state | application-state; 50 Gi claim; 50 GB OCI volume | Bound / AVAILABLE |
| HTTPS state | https-state; 50 Gi claim; 50 GB OCI volume | Bound / AVAILABLE |
| Node boot volume | 50 GB; 10 VPUs per GB | AVAILABLE |
| Private image registry | ags-aegis-web, ags-aegis-backend, ags-aegis-ssh | All private |

## Current deployment placement

| Runs where | Components currently used |
| --- | --- |
| OCI OKE | Next.js web app, Caddy HTTPS, FastAPI, LangGraph agents, durable worker and CPU reranker |
| OCI Autonomous AI Database | Application records, access, durable job queue and Oracle native vector knowledge |
| OCI Object Storage | Original documents, prompts, parsed content and saved JSON / Parquet results |
| Google cloud API | Gemini embeddings, chat, extraction and dataset-aware OCR for all three active datasets |
| Local laptop | Retained Ollama / Qwen / Nomic option; containers stopped and relay endpoint unreachable at the check |

## Container allocation

| Container | CPU and memory request | CPU and memory limit |
| --- | --- | --- |
| api | 250m CPU; 768Mi | 1 CPU; 2Gi |
| worker | 500m CPU; 2Gi | 1500m CPU; 4Gi |
| model-relay | 25m CPU; 32Mi | 100m CPU; 128Mi |
| web | 150m CPU; 512Mi | 1 CPU; 1536Mi |
| https | 50m CPU; 64Mi | 250m CPU; 256Mi |

Values above are requests/limits, not current utilization. The cluster Metrics API was unavailable.

## Running versions

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

## Mapped models

| Role | Mapped model | Where it executes |
| --- | --- | --- |
| Embedding | gemini-embedding-2 | Google Gemini API |
| Chat | gemini-3.5-flash-lite | Google Gemini API |
| Extraction | gemini-3.5-flash-lite | Google Gemini API |
| OCR for mapped datasets | gemini-3.5-flash-lite | Google Gemini API |
| Candidate reranking | Configured CPU reranker | OCI API / worker; model files on shared state |

All three active datasets use these Gemini defaults. The local Ollama container was stopped and its relay endpoint was unreachable. The dataset-aware OCR mapping was inspected without invoking inference.

## Network and durable storage

VCN `ags-aegis-vcn` uses `10.42.0.0/16`. API, worker and LB subnets use `10.42.0.0/24`, `10.42.1.0/24` and `10.42.2.0/24`. The public load balancer uses `92.4.67.183` with HTTP/HTTPS ports 80/443 and 10 Mbps minimum/maximum bandwidth. The internal API service uses port 8000.

Application and HTTPS claims each request 50 Gi, backed by two OCI 50 GB volumes. The node boot volume is another 50 GB. Autonomous Database has a separate 20 GB storage allocation. The database Free Tier flag is true; this is not a statement that every OCI service is free.

Bucket `mk-aegis` currently reports `ObjectRead` public access and `Disabled` versioning; the inspection preserved both settings. Approximate bucket count and size at inspection: 746 objects and 8618494 bytes. These values are point-in-time OCI estimates.

## Deployed image references

### aegis-api-worker

- `api`: `bom.ocir.io/bmyljaecivrj/ags-aegis-backend@sha256:fe2ea263dd76ef2a1b50a56b2b26cab0eb81da43cbf0c852dd270f5b8d046ae5`
- `worker`: `bom.ocir.io/bmyljaecivrj/ags-aegis-backend@sha256:fe2ea263dd76ef2a1b50a56b2b26cab0eb81da43cbf0c852dd270f5b8d046ae5`
- `model-relay`: `bom.ocir.io/bmyljaecivrj/ags-aegis-ssh@sha256:37189e82533c3e893f261b9735880e74f521f2ee6ce15f4490e3087ea1944870`

### aegis-web

- `web`: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:12336119afcca52b7eb9bbc34329cc967279787398406a637b52d2b4740b31fc`
- `https`: `docker.io/library/caddy@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d`

The backend desired image is a multi-platform/index digest; its running container image ID has the platform digest recorded in [the sanitized snapshot](OCI-LIVE-SNAPSHOT.json). Both identify the observed deployment and were left unchanged.

## Inspection boundaries

HTTPS returned 200; both deployments had one ready replica and all five containers were ready with zero restarts. The read-only application catalog query confirmed the OCI database/content/search destinations and the saved model mappings. No new upload, extraction, chat inference, account change, restart or rollout was performed. Credentials, wallet contents and business document payloads are excluded.
