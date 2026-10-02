# Staged OCI migration runbook

## Scope and stopping condition

This is a proposed path from the shipped local/container deployment to an OCI-hosted deployment. OCI storage, model, retrieval and queue adapters are implemented, but no live-tenancy integration was run. A migration is complete only when the chosen services pass acceptance tests, restored content remains accessible with correct permissions, application behavior is verified, and rollback is rehearsed. These documents do not authorize provisioning or spending.

## 1. Inventory and design approval

Record content count/bytes, metadata size, current schema, dependency versions, vector dimensions, collection scopes, largest document and job duration. Classify data permitted to reach each model service. Select region based on every needed service/model and any residency obligations, rather than assuming a single region supports all features.

Choose the target network, private endpoints/routes, DNS, TLS trust, secret mechanism, minimum IAM permissions, backup retention, cost budget and operational owners. Decide which components remain self-hosted initially. Moving containers to OCI does not require moving all providers in one release.

## 2. Verify adapters before configuration cutover

Use [OCI_READINESS.md](OCI_READINESS.md) as the acceptance checklist. Test each implemented boundary independently with synthetic content in the intended tenancy. Verify failures and denied access as well as happy paths. Keep readiness false for untested capabilities. Do not route an unsupported provider name to a local or mock substitute.

A lower-risk first stage can retain Qdrant and the current model provider while validating OCI-hosted application containers and PostgreSQL. That stage is an infrastructure migration, not an Enterprise AI integration.

## 3. Prepare deployment safely

Build pinned images and run tests before deploying. Separate API and worker lifecycles. Start with one writer if the current filesystem/job implementation lacks shared-storage or concurrency guarantees. Configure durable storage, ingress TLS, restricted service exposure and secrets outside images.

For OKE, validate the chosen node architecture against Python/native parsing dependencies. Workload identity requires an enhanced cluster and service-account-scoped policies; simply moving a pod to OKE does not give an SDK working credentials. [OKE identity guide](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm)

## 4. Migrate metadata and content

1. Perform an isolated rehearsal from a coordinated backup.
2. Restore PostgreSQL metadata to a fresh target using compatible native tools. Review managed-service role restrictions, missing extensions, schema errors, row counts and grants. [Oracle PostgreSQL import/export](https://docs.oracle.com/en-us/iaas/Content/postgresql/import-export-migrate.htm)
3. Copy content under immutable destination keys with a manifest of source path, destination key/version, byte count and SHA-256 digest. Verify all content, not only a sample, before marking copy complete.
4. Map DB pointers to the destination without changing logical document/owner IDs. Keep the original source intact. Test missing objects and unauthorized reads.
5. Use verified TLS and the target's matching CA/hostname for database connectivity. [OCI PostgreSQL SSL](https://docs.oracle.com/en/learn/oci-pgsql-ssl/index.html)

No cross-store atomic cutover is assumed. Freeze writers for final copy/metadata snapshot, or implement a separately tested change-capture protocol. Do not invent zero-downtime guarantees.

## 5. Rebuild retrieval and validate model behavior

Re-index from source artifacts into a new collection/vector store. If changing embeddings, use a fresh collection with the correct dimensions; never reuse incompatible vectors. Preserve old retrieval until the new one passes representative relevance and permission tests.

For Enterprise AI, wait for ingestion to complete and translate remote results into Aegis citations that resolve to the original document/version. Use only documented search options. [OCI vector-store workflow](https://docs.oracle.com/en-us/iaas/Content/generative-ai/use-vector-store.htm)

If changing inference providers, run a representative extraction corpus against saved schema versions. Measure schema validity, groundedness, missing fields, latency and cost. Human-review consequential extraction outputs. Confirm streaming/cancellation and failure reporting before enabling chat.

## 6. Queue and worker cutover

Drain or pause existing workers and inventory pending/running jobs. Move durable job identities, not transport-specific receipt handles. Start the new consumer with idempotent result commits and lease renewal. Verify crash recovery, duplicate delivery and dead-letter handling before increasing concurrency. Do not let old and new workers independently process the same paid inference job.

## 7. Final cutover and rollback

- Freeze writes; take a final coordinated backup and record the recovery point.
- Complete final content/metadata transfer and index reconciliation.
- Validate login, ownership, upload, parse, search, cited chat, template editing, extraction, export and audit records.
- Switch application traffic using an approved deployment/DNS process; observe error rates, latency, queue age, storage errors and costs.
- Preserve the old environment read-only. If rollback is needed before accepting new writes, switch back to the preserved consistent source. If the target has accepted writes, first reconcile those changes or explicitly accept their loss; blind rollback is unsafe.
- Accept the migration only after a target-environment backup/restore drill and operational sign-off. Record all remaining unvalidated capabilities explicitly.

## Acceptance evidence

Keep an operator-facing report with release/image digest, migration times, checksum/count comparisons, representative end-to-end results, permission-denial tests, job recovery results, model/region settings, observed cost and restore measurements. Do not include secrets or sensitive document text in the report.

## Shipped cold migration CLI

`scripts/migrate_storage.py` implements three explicit phases. It supports local-to-OCI and OCI-to-local; it never removes source objects, provisions a bucket, copies provider secrets or restarts writers. It includes all current content roots, historical template versions, jobs, conversations, extraction artifacts and document index manifests. It checks every nonempty database content reference and every job-consent object exists in the source. Named configuration profiles referenced under `configuration/profiles/` remain local, along with credentials and diagnostics; they are deliberately excluded from the content-copy completeness check. An unknown database reference root stops migration rather than being silently skipped.

The script requires `--writers-stopped` as an explicit operator assertion. It cannot prove that no separate deployment is writing the same bucket or database. Stop **all** API/web/worker processes and other writers first; keep them stopped across all phases. Its file lock only prevents two migration scripts from running concurrently. Run a coordinated backup before migration.

Use the same `/data` volume, database, secrets and OCI identity as the application. From a host with backend dependencies and those resources mounted, the CLI shape is:

```sh
python scripts/migrate_storage.py plan \
  --manifest /protected/migration.json --writers-stopped --to oci \
  --dest-region us-chicago-1 --dest-namespace YOUR_NAMESPACE \
  --dest-bucket YOUR_PRIVATE_BUCKET --dest-prefix aegis \
  --dest-auth-mode config_file --dest-profile DEFAULT

python scripts/migrate_storage.py copy \
  --manifest /protected/migration.json --writers-stopped \
  --confirm-destination 'us-chicago-1/YOUR_NAMESPACE/YOUR_PRIVATE_BUCKET/aegis'

python scripts/migrate_storage.py activate \
  --manifest /protected/migration.json --writers-stopped \
  --confirm-destination 'us-chicago-1/YOUR_NAMESPACE/YOUR_PRIVATE_BUCKET/aegis'
```

For Compose, run the script in a one-off API container **without** starting dependencies or application writers. Mount the repository scripts read-only at `/app/scripts` and a protected, UID-10001-writable manifest directory at `/migration`, then invoke `python /app/scripts/migrate_storage.py ...`. Keep the existing database service available. Include the same profile override as the deployment if using config-file OCI authentication. Do not put a migration manifest beneath a content root being migrated.

Planning reads source content and produces an owner-only JSON manifest containing key, byte count, checksum and destination metadata. Review the exact destination confirmation printed by planning. Copy refuses conflicting existing destination content, re-reads every destination object and marks the manifest verified only after all checks succeed. Rerunning copy safely accepts already copied identical content. Source inventory, settings and checksums must still match the plan. Activation rechecks both stores and then atomically replaces only local storage settings. No secrets are migrated. A failure leaves source content and provider selection intact unless activation already completed; inspect settings and the manifest before retrying an uncertain activation.

For OCI-to-local, plan with `--to local` and confirm `local-content-volume`. Existing local content with a different checksum is a conflict; resolve it through a reviewed recovery process, never by deleting the original blindly. After activation, start the application and perform the acceptance checks above. Retain the old source until the recovery window has passed.

## Optional config-file deployment

The repository's `compose.oci-profile.yaml` adds a read-only `${AEGIS_OCI_PROFILE_DIR}:/run/oci` mount for API and worker. Use it alongside the normal Compose file. Set `OCI_CONFIG_FILE=/run/oci/config`; the profile's `key_file` should point to `/run/oci/private_key.pem`. Both files must be readable by the backend's UID 10001 using appropriate ownership and restrictive permissions. Do not make private keys world-readable or bake them into images.

Alternatively set server-side `OCI_AUTH_MODE=instance_principal` or `resource_principal` in a supported OCI runtime with appropriately scoped identity. This adapter does not claim that arbitrary OKE workload identity is automatically covered by those modes. OCI model authentication has separate `oci_auth_mode` settings and its own supported signers. See [provider readiness](OCI_READINESS.md).
