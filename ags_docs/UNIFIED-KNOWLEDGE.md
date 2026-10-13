# Unified Aegis knowledge

Publication version 3 preserves auxiliary metadata floats (audit timestamps and
OCR timings) as lossless decimal strings. JSON transport can otherwise round a
float and invalidate an intact payload's content digest. Extracted business values
retain their numeric types in canonical JSON text; read-only assembly decodes that
text. Integrity verification remains exact, and latest-workflow selection compares
timestamps numerically. Existing manifests are republished by the normal worker
reconciliation/write workflows; originals, Parquet and database timestamps stay
unchanged.

Implemented 2026-10-12. Oracle records and persistent originals, JSON and Parquet are authoritative. Qdrant is a rebuildable semantic discovery index. A saved extraction has both a canonical result file and derived vectors; editing a result publishes a new file revision and replaces its indexed revision.

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

The Agent's `search_knowledge` tool supports meaning-based discovery. Dataset discovery can search accessible dataset/model metadata and application guidance across datasets. Documents and extracted values use the selected dataset/document scope. Exact lists, counts, equality/skill predicates and live status continue to use the existing authoritative tools. Ranked candidate count is never a verified matching record count. Questions do not execute onboarding, uploads or extraction.

## Index and synchronization

Local registered embedding configuration supplies the embedding space. Compatible profiles use one `aegis_knowledge_<20-character fingerprint>` collection with cosine distance; embedding configuration/schema changes produce a separate collection. Existing document collections and their retrieval/reranking remain intact. The verified laptop deployment uses Nomic embeddings, dimension 768.

Each point records source type, entity/dataset/owner IDs, source version, part, title, canonical excerpt, content digest and relevant page/document/result provenance. IDs are deterministic UUIDs derived from source identity, version and part. Text fragments are bounded to 2400 UTF-8 bytes. Embeddings are submitted in batches of 24.

A durable manifest under `knowledge/<collection>/manifest.json` tracks entity stamps and point IDs. A filesystem lock on the shared persistent volume serializes API and worker synchronization. The worker schedules reconciliation every 60 seconds in a separate thread; search also synchronizes its scope before retrieval. The background pass targets 256 points, committing complete entities (a single large entity may exceed this target). Repeat upserts use the same IDs. The ledger is published after upserts and removal of superseded IDs; interrupted work can be replayed. Deleted source entries are purged on reconciliation.

Search filters by currently authorized IDs before Qdrant retrieval. Every hit and every source link rechecks access and reconstructs its current canonical source. A stale version/digest, missing file or revoked access fails closed. Stored vector payload text alone cannot establish an answer. Result integrity is checked by the existing Parquet loader. Versions of canonical result files remain preserved.

## API and user experience

- `POST /api/knowledge/search`: authenticated question, optional dataset/document/source-type filters and top limit (1–12). Returns ranked, canonically hydrated sources plus index statistics. It is not a complete catalog.
- `GET /api/knowledge/sources/{knowledge_id}?collection=...`: authenticated current canonical source; unavailable, stale or inaccessible sources return 404.
- Agent citations retain existing document and extraction rendering; other knowledge types show their type/version, canonical excerpt and Open source link.
- Answer progress uses the existing compact shared workflow and actual tool stage. Existing colors and animations are unchanged.

## Operational limits

This is semantic discovery, not proof that every nearest neighbor is relevant. The composing agent must use only supported candidates. Full saved records and exact conditions still need canonical tools. Cloud-only embedding profiles are not silently substituted; an accessible dataset must map a supported local embedding/search profile. There is no hosted tracing or external knowledge upload introduced by this feature.

Large entity backfills can take time, including the first query after changes. This implementation does not add an administrator index-monitoring screen, distributed outbox or multi-host lock. The persistent-volume lock applies to the current deployment. Keep the SQL/file store and Qdrant volumes backed up; the derived index can be rebuilt.
