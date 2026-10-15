# Unified Aegis knowledge

Current placement was verified on 15 October 2026: Oracle Autonomous AI Database 26ai holds native vectors and metadata, OCI Object Storage holds originals and results, and the active datasets use Gemini embeddings. See [live resources](OCI-LIVE-RESOURCES.md). The publication mechanism below began on 12 October; local Qdrant and Nomic configurations are retained development alternatives.

Publication version 3 preserves auxiliary metadata floats (audit timestamps and
OCR timings) as lossless decimal strings. JSON transport can otherwise round a
float and invalidate an intact payload's content digest. Extracted business values
retain their numeric types in canonical JSON text; read-only assembly decodes that
text. Integrity verification remains exact, and latest-workflow selection compares
timestamps numerically. Existing manifests are republished by the normal worker
reconciliation/write workflows; originals, Parquet and database timestamps stay
unchanged.

Oracle records and persistent originals, JSON and Parquet are authoritative. The configured vector index is derived from those sources. Live OCI uses native Oracle vectors; a separate local installation can use Qdrant. A saved extraction has both a canonical result file and derived vectors; editing a result publishes a new file revision and replaces its indexed revision.

## Sources and scope

| Source type | Indexed content | Authoritative read |
| --- | --- | --- |
| dataset | Name, description, active state, model role IDs | Dataset catalog/status |
| document | Filename, size, version, indexing state | Document catalog/status |
| document_chunk | Parsed/OCR text, page and chunk provenance | Original document/chunks |
| extraction | Result metadata and saved field records | Verified Parquet read and Review |
| prompt | Filename, schema and instruction | Saved template version |
| model | Public provider/model identity, capabilities, context/output limits | Public model mapping/configuration |
| workflow | Owner's persisted tool step/status summary | Current workflow/goal status |
| application | Seven maintained built-in guidance topics | Built-in application documentation |

Conversation messages, original user goal text, responses, credentials, endpoints and arbitrary configuration bodies are excluded. Workflow summaries contain public step/status information, not the conversation. Uploaded/source content is untrusted evidence and cannot authorize an action.

Unified Chat enforces access and scope, runs hybrid semantic and keyword retrieval, reranks evidence on the OCI CPU, generates the model answer, then validates the answer and citations. This applies to all questions, including help and catalogs. Dataset discovery can search accessible dataset/model metadata and application guidance across datasets. Documents and extracted values retain the selected dataset/document scope. Exact lists, counts, equality/skill predicates and live status use complete authoritative facts as supplementary evidence. Ranked candidate count is never a verified matching record count. Questions do not execute onboarding, uploads or extraction.

## Index and synchronization

The dataset's saved embedding registration supplies the embedding space. Compatible profiles use one `aegis_knowledge_<20-character fingerprint>` namespace with cosine distance; embedding configuration/schema changes produce a separate namespace. Oracle stores namespaced vectors in the database; the local Qdrant alternative uses collections. The current active datasets map to `gemini-embedding-2`; the retained Nomic mapping is a local alternative.

Each point records source type, entity/dataset/owner IDs, source version, part, title, canonical excerpt, content digest and relevant page/document/result provenance. IDs are deterministic UUIDs derived from source identity, version and part. Text fragments are bounded to 2400 UTF-8 bytes. Embeddings are submitted in batches of 24.

A durable manifest under `knowledge/<collection>/manifest.json` tracks entity stamps and point IDs. A filesystem lock on the shared persistent volume serializes API and worker synchronization. The worker schedules reconciliation every 60 seconds in a separate thread; search also synchronizes its scope before retrieval. The background pass targets 256 points, committing complete entities (a single large entity may exceed this target). Repeat upserts use the same IDs. The ledger is published after upserts and removal of superseded IDs; interrupted work can be replayed. Deleted source entries are purged on reconciliation.

Search filters by currently authorized IDs before vector retrieval. Every hit and every source link rechecks access and reconstructs its current canonical source. A stale version/digest, missing file or revoked access fails closed. Stored vector payload text alone cannot establish an answer. Result integrity is checked by the existing Parquet loader. Versions of canonical result files remain preserved.

## API and user experience

- `POST /api/knowledge/search`: authenticated question, optional dataset/document/source-type filters and top limit (1–12). Returns ranked, canonically hydrated sources plus index statistics. It is not a complete catalog.
- `GET /api/knowledge/sources/{knowledge_id}?collection=...`: authenticated current canonical source; unavailable, stale or inaccessible sources return 404.
- Agent citations retain existing document and extraction rendering; other knowledge types show their type/version, canonical excerpt and Open source link.
- Answer progress uses the existing compact shared workflow and actual tool stage. Existing colors and animations are unchanged.

## Operational limits

A nearest neighbor is not proof of relevance. The composing agent must use supported evidence and canonical records for exact conditions. Each accessible dataset must map a supported, reachable embedding registration and compatible search destination. Providers are not silently substituted. The current Gemini mapping sends embedding input to Google's configured API; document and result storage remains in OCI.

Large entity backfills can take time, including the first query after changes. This implementation does not add an administrator index-monitoring screen, distributed outbox or multi-host lock. The persistent-volume lock applies to the current deployment. Preserve coordinated Oracle, Object Storage and shared-state recovery; the vector index can be rebuilt from compatible durable sources. See [deployment and recovery](../ags_deployment/DEPLOYMENT.md).
