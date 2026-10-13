# Chat Agent

LangGraph performs one model-based handoff for the current request: Onboard & Extract, Re-extract, or Chat. The routing model receives the current selection and verified reference IDs, not the conversation archive or full workspace catalog.

Chat answers use published unified knowledge. The production path reads Oracle native vector payloads when OCI is active, or Qdrant payloads when configured locally. SQL remains necessary for authorization, model configuration and revision checks. The local publication ledger verifies vector payload identity, completeness and freshness; it is not a second business answer source in Oracle/Qdrant mode.

The typed query plan determines the lookup:

| Question | Published source | Lookup |
| --- | --- | --- |
| Document count or filenames | Document metadata | Complete authorized catalog |
| Dataset list or model mapping | Dataset/model metadata | Complete authorized catalog |
| Saved fields, skills, exact predicates | Extraction records | Complete scoped payloads and field projection |
| Original document content | Document chunks | Direct chunks for a small single source; otherwise semantic retrieval |
| Meaning-based discovery | Requested knowledge types | One embedding and filtered similarity search |
| Workflow progress | Private workflow metadata | Authorized published workflow records |
| Aegis capabilities | Application guidance | Published application records |

The Chat Agent exposes one `query_unified_knowledge` trace and does not select additional tools. Exact catalogs produce deterministic answers where appropriate. Other answers use one model call with bounded evidence and no mutation tools. Numeric citations refer to the retrieved vector records; extracted records include Review actions. Source previews also read published vectors.

Queries never rebuild the index, load business source files or hydrate Parquet. Missing, stale, incomplete or altered publication fails with a scoped error. Existing files and results remain intact. Counts and complete lists never use semantic top-k results.

Publication belongs to the write workflows. Onboard & Extract independently saves JSON/Parquet and publishes metadata, source chunks and extracted fields before announcing completion. Workflow revision changes invalidate older progress vectors. A pending final publication is recoverable after worker restart.

Only the current question, required evidence and verified references enter the model. Chat answer context is capped at 8,192 tokens with at most 1,024 output tokens, subject to smaller registered limits. The context packer rejects oversized required evidence instead of silently truncating it. Very broad requests must be narrowed.

On this laptop, embedding/chat weight switching can still add latency because Ollama keeps one model resident. Metadata catalogs and small exact document questions avoid query embeddings, reducing those switches without changing GPU concurrency or memory settings.
