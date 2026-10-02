# Aegis architecture

## Storage-first design

The application separates three concerns:

1. **Durable content storage** holds document originals, extracted text/chunks, conversations, template schemas and extraction outputs. The local provider uses the configured `DATA_DIR`; the OCI Object Storage adapter implements the same logical-key content interface.
2. **Relational metadata** holds identifiers, user/workspace ownership, object references, processing states and timestamps. PostgreSQL is the deployment database; SQLite is for isolated tests. Content bodies must not quietly migrate into relational columns.
3. **Retrieval index** is a derived search representation. Qdrant is the normal vector-store option, and embeddings come from an explicitly configured provider. An index is rebuildable from durable sources but model and chunker versions must be recorded.

Browser → authenticated API → ownership check → metadata + content provider.

Upload → durable original → job state → worker parsing/chunking → embeddings/index → terminal status.

Chat → authorized source scope → retrieval → grounded model call → saved conversation artifact.

Extraction → saved schema version + source version → model → server-side schema validation → durable result + metadata pointer.

These are the intended boundaries; API route names and implemented behavior are authoritative in the backend code. A feature is not operational merely because a screen or configuration field exists.

## Provider choices and failure semantics

The deployment defaults to Qdrant search, OpenAI models/embeddings and PostgreSQL. A sentence-transformers embedding option can run locally where its model dependencies are installed. Explicit mock/test modes are for deterministic tests and demos; their outputs are not real model inference and must not be represented as such.

OCI adapters provide real SDK/compatible-API paths but have not been live-tenancy validated; see [OCI readiness](OCI_READINESS.md). Provider validation should reject unsupported names and missing dependencies without silently selecting a mock. Credential-free status can say "configured" but must not say "verified". Service health and integration readiness are different signals.

Keep provider credentials in server-side environment/secret facilities only. Never include API keys, database passwords or signed object URLs in browser payloads, job logs or capability responses.

## Consistency and job processing

Object storage and relational transactions are not one atomic transaction. Favor immutable versioned artifacts, write-then-reference ordering, and a reconciler for orphaned/missing artifacts. Jobs need stable identifiers, durable states and idempotency at their externally visible effects. Worker success must mean its outputs are committed, not simply that a function returned.

A queue is a transport, not a record of truth. Preserve enough job metadata to recover interrupted work and distinguish retriable failures from permanently invalid input. Do not blindly replay completed model calls after a crash without checking their persisted result, especially when inference is billable.

## Security and production limitations

The bundled authentication and tenant checks must be exercised before wider deployment. Production approval additionally requires TLS, secret rotation, rate/upload limits, malware and parser isolation appropriate to the document sources, audit retention, least-privilege access, and backup restoration tests. Model input/output can contain confidential data, so provider selection is also a data-sharing decision.

Retrieved documents are untrusted input. Their text may be quoted or extracted but must never redefine system instructions, choose tools or grant permission. Cite only authorized, persisted sources that can be resolved to the actual document/version.

## Operations

See [backup and restore](BACKUP_RESTORE.md) for a coordinated recovery procedure and [OCI migration](OCI_MIGRATION.md) for staged cutover. Local process success is not proof of remote PostgreSQL, Qdrant, model or OCI readiness. Record separate test results for each integration.
