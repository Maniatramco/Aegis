# OCI provider readiness and migration contracts

Last documentation review: 2026-10-02. These are migration instructions and acceptance criteria, not evidence of a deployed OCI integration. No OCI resources were provisioned, credentials created, or paid requests made during this build.

## Honest capability boundary

`backend/app/oci_adapters.py` implements OCI Object Storage and Queue SDK operations. `backend/app/oci_models.py` implements OCI Responses and managed vector-store operations. These are real provider paths, with mocked contract tests; no live tenancy was used. The capability registry separates implementation from live readiness, which remains false until a deployment is verified. Configuration alone is not an integration test. Unsupported authentication modes and malformed or missing configuration fail explicitly rather than falling back.

| Capability | Current application state | Deployment verification required |
|---|---|---|
| OCI Object Storage | SDK put/get/delete and JSON content, deterministic keys, checksums, read-only probe | IAM rights, namespace/bucket, round-trip, backups |
| OCI Generative AI chat/extraction | Project-backed Responses adapter | Supported region/model, credential mode, schema and groundedness |
| OCI Enterprise AI vector stores | Managed upload/ingestion/search adapter | Existing store, scope filters, citation round-trip and deletion |
| OCI Queue | SDK publish/receive/ack/lease extension | Live queue endpoint, tenancy crash/redelivery/DLQ drill |
| OCI Database with PostgreSQL | Generic PostgreSQL path | TLS trust, private reachability, grants, failover and restore |
| OKE | Deployment target, unvalidated | Images/manifests, identity, networking, persistent storage and scaling |

### Storage/queue configuration

Install `backend/requirements-oci.txt` in the server environment. Select `STORAGE_PROVIDER=oci` only after setting `OCI_NAMESPACE`, `OCI_BUCKET`, and optional `OCI_OBJECT_PREFIX` (default `aegis`). Logical DB object references remain unchanged; the prefix is added only at the provider boundary. Configuration, encrypted provider secrets and diagnostic artifacts remain on the shared local data volume even when document/content storage is OCI. Back up that volume and the master key separately; moving documents does not migrate secrets. There is no implicit data copy when switching providers. Transfer and checksum existing content first.

`OCI_AUTH_MODE` is `config_file`, `instance_principal`, or `resource_principal`; `OCI_CONFIG_FILE`, `OCI_PROFILE` and `OCI_REGION` configure server-side SDK authentication. Mount an existing profile/key read-only when using config-file authentication. The adapter does not create credentials or buckets. Do not confuse SDK `OCI_AUTH_MODE` with the separate model provider's `oci_auth_mode` setting.

Queue requires `OCI_QUEUE_ID` and `OCI_QUEUE_ENDPOINT`, the queue's HTTPS messages endpoint (from queue details), not its management API endpoint. The adapter sends only job IDs. Its connection probe reads queue statistics; Object Storage's probe heads the bucket. Neither probe proves write permissions or full application readiness. API calls have explicit timeouts and automatic SDK retries disabled; application-level retry must preserve idempotency.

### Model/vector configuration

The implemented model settings include `oci_region`, `oci_project_id`, `oci_auth_mode`, `oci_profile`, `oci_model`, and `oci_vector_store_id`. Model authentication supports API-key and documented IAM modes through `oci-genai-auth`; API keys remain server-side. The model connection test performs a small inference request and can be billed. Vector-store checks read an existing store; provisioning is not implicit. See implementation and current Settings validation for the exact accepted provider names.

## Object Storage

Use a private bucket, scoped IAM access, and a deterministic object key for each immutable content version. Preserve workspace/user ownership in metadata in the application DB. Store original uploads, extracted text/chunks, conversations, template schemas and extraction results as durable objects; the DB retains pointers, status, ownership and checksums. Download through authorization-checked application routes rather than leaking raw object URLs.

The native service addresses an object by namespace, bucket and key. The adapter handles not-found separately from forbidden, transient failures and corrupt/missing content. Upload to a new immutable key, verify size/checksum, then commit the DB reference; reconcile orphaned objects after failed transactions. Never advertise a document as indexed until its referenced artifacts exist. [Object management](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingobjects.htm)

Versioning and retention are separate design choices: OCI does not permit active retention rules and enabled versioning on the same bucket. Replication does not copy historical object versions and is not a substitute for a coordinated backup. Choose a policy before migration. [Versioning constraints](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm)

## Generative AI: chat and structured extraction

Two API families appear in Oracle documentation. Pin the chosen family, SDK version, model and region in integration tests:

- OCI-native inference APIs use OCI request models and signing.
- The current Enterprise AI OpenAI-compatible base is `https://inference.generativeai.${region}.oci.oraclecloud.com/openai/v1`. Project-backed Responses and Chat Completions have their own supported model/tool matrix. Authentication uses OCI credentials, not an OpenAI account key. [Endpoint reference](https://docs.oracle.com/en-us/iaas/Content/generative-ai/openai-compatible-api.htm), [project setup](https://docs.oracle.com/en-us/iaas/Content/generative-ai/use-project.htm)

Oracle also documents an API-key route under `/20231130/actions/v1`. Do not mix its examples or model matrix with project-based endpoints. Check the intended endpoint's current support table. Data residency must be checked for the chosen model: Oracle explicitly states that xAI models on its API-key page can call externally hosted xAI locations. [API-key route and external-model caveat](https://docs.oracle.com/en-us/iaas/Content/generative-ai/api-keys.htm)

For extraction, use an explicitly supported structured-output schema and validate the result server-side against the saved template version. Valid JSON does not guarantee schema compliance or factual correctness. Preserve source-document and page/chunk references, model identifier and schema version. Treat document text as untrusted data; it cannot grant tools or override extraction instructions. Reject malformed output or label extraction failed rather than returning invented fields. [Structured output guidance](https://docs.oracle.com/en-us/iaas/Content/generative-ai/get-started-agents.htm)

## Enterprise AI vector stores

This managed retrieval service is not Qdrant and is not Oracle Database AI Vector Search. Plan an adapter at the retrieval boundary rather than copying Qdrant requests. Oracle's vector-store guide separates management/control-plane work from data-plane search and recommends an Object Storage connector for document sources. Poll ingestion to completion before making a source searchable. Persist remote IDs, source versions and operation status. [Using vector stores](https://docs.oracle.com/en-us/iaas/Content/generative-ai/use-vector-store.htm)

Search compatibility is partial: the documented vector-store API does not support query rewriting or arbitrary custom rankers. Implement only supported options. Enforce application ownership/collection filters even when the cloud API supports broader search. Test deletion, permission changes, stale chunks, empty results and citation resolution. A file accepted for upload is not proof its chunks are searchable. [Vector-store concepts](https://docs.oracle.com/en-us/iaas/Content/generative-ai/vector-stores.htm)

## Queue

Publish only job IDs and object references, not entire documents. Use the service's messages endpoint and receipt-based acknowledgments. Delete a message only after durable job state and output have committed. Extend visibility for long work, and make processing idempotent because redelivery can occur. Lease expiry, worker crashes and concurrent redelivery must not duplicate final extraction outputs or corrupt indexing. [Queue overview](https://docs.oracle.com/en-us/iaas/Content/queue/overview.htm)

Production deployment additionally needs retry limits, exponential backoff, correlation IDs, DLQ inspection/replay, cancellation checks and a recovery path from DB state. Queue retention is finite, so it cannot be the authoritative job history. [DLQ behavior](https://docs.oracle.com/en-us/iaas/Content/queue/deadletterqueues.htm), [receipt/visibility updates](https://docs.oracle.com/en-us/iaas/Content/queue/update-messages.htm)

## Managed PostgreSQL

Retain the PostgreSQL metadata schema and migrate using native dump/restore into a separately provisioned target. Review roles, extensions and privileges; the managed admin is not a superuser. Check row counts, constraints, permissions and application reads after restore. [Oracle migration guidance](https://docs.oracle.com/en-us/iaas/Content/postgresql/import-export-migrate.htm)

Use a private network path and certificate-verified TLS (`sslmode=verify-full` with the correct CA and matching hostname). Never downgrade verification to work around connection errors. OCI PostgreSQL requires encrypted connections; deployment-specific certificates must be mounted securely. [SSL configuration](https://docs.oracle.com/en/learn/oci-pgsql-ssl/index.html)

Managed DB backups do not contain Aegis object files or its external vector index. Coordinate them with the storage recovery point. Rehearse the selected backup policy and restore procedure in an isolated environment. [Backups](https://docs.oracle.com/en-us/iaas/Content/postgresql/backups.htm)

## OKE production gate

Separate API and worker deployments; run migrations once per release. Use readiness/liveness probes, termination grace periods, resource requests/limits, restricted network access and an ingress with TLS. Do not scale a local-filesystem deployment across nodes unless all replicas share a suitable durable volume; prefer the completed Object Storage adapter before horizontal scaling.

Use pod-scoped workload identity where supported. OCI workload identities require an enhanced cluster and IAM rules scoped to cluster, namespace and service account. Do not place long-lived OCI signing keys in an image. These controls still require implementation and verification in the application SDK path. [OKE workload identity](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm)

## Enablement acceptance record

For each capability, record commit/image digest, SDK version, region, model or service type, test fixture hashes, account used, minimum IAM policy, successful and denied operation tests, timeout/retry tests, backup/restore result, cost limit and date. Use non-sensitive fixtures first. A reviewer should mark a capability ready only after successful integration tests in the intended tenancy. Keep feature-specific flags; one working service must not turn all OCI indicators green.

## Reproducible checks

From `backend`, install `requirements-dev.txt` plus `requirements-oci.txt`, then run `python -m pytest tests/test_oci_adapters.py tests/test_oci_models.py` (use the shipped model-test filename if it differs). The Object Storage/Queue suite includes real SDK-generated argument and request-model validation with a mocked transport, so it neither needs credentials nor invokes the network. Passing those tests does not verify IAM policy, a bucket, a queue or a model subscription.

An operator with an already authorized deployment can run `python -m app.oci_adapters storage` or `python -m app.oci_adapters queue` for read-only connection probes. Both return a small JSON result and a nonzero exit on error. They do not create resources, write probe objects, publish jobs or validate write rights.

Storage destination fields in Settings are separate from inference authentication: `oci_storage_namespace`, `oci_storage_bucket`, `oci_storage_prefix`, `oci_storage_region`, `oci_storage_auth_mode`, and `oci_storage_profile`. `OCI_CONFIG_FILE` remains a server-controlled mounted path, not an editable UI field. Changing destination metadata on populated storage requires the operator migration workflow; changing a bucket alone cannot relocate existing objects. A different region/bucket/project is a different data destination and must be reviewed before stored credentials are reused there.

The worker queue helper in `app/queue_transport.py` uses `QUEUE_PROVIDER=database` by default and `oci` for OCI notifications. Database job state remains authoritative and workers reconcile it even if publication or receipt handling fails; inspect the shipped worker integration and tests before scaling. The queue's server-side credentials/destination are independent of the model API key.

Queue transport diagnostics are process-local. API and worker run separately, so a successful stats probe or configured flag cannot establish a cross-process publish/consume/terminal-ack round trip. Persisted `queue_provider` controls runtime selection; `QUEUE_PROVIDER` supplies its initial default.
