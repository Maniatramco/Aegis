# File storage configuration

Admins configure file destinations in **Manage workspace → Storage**.

The same screen also contains **Database & knowledge**. Local uses the existing laptop Oracle database and Qdrant. OCI uses the configured Oracle 26ai database and native Oracle vector search. File destinations remain independently selectable.

## Database and vector configuration

The current OCI database is `agsora` (`ags_ora_db`), region `ap-mumbai-1`. Its downloaded wallet is held at `C:/Users/Laya/.oci/database/wallet` and mounted read-only into API and worker as `/run/aegis-db/wallet`. Only `tnsnames.ora` and `ewallet.pem` are needed for the configured Thin-mode mTLS connection. The service alias is `agsora_low`; server certificate identity checking remains enabled.

Enter an existing database username, its database password, and the separate password chosen when downloading the wallet. Database passwords cannot be retrieved from the OCI console. Password fields are masked; saved passwords are encrypted using the application master key in local storage and never returned in API responses or copied into images, metadata tables or vector payloads. Changing the destination identity does not silently reuse another connection's password.

1. **Test database connection** verifies connectivity and native vector support without creating tables or activating the database.
2. **Save database configuration** saves the verified draft and encrypted credentials without activating it.
3. **Create Aegis tables** creates missing Aegis tables in the selected schema: the 12 application metadata tables plus `aegis_knowledge_vectors`.
4. **Activate OCI database** copies and verifies the current catalog and compatible vectors before publishing the new shared destination. Existing users and sessions are copied so sign-in continues. Both API and worker read the shared routing configuration for subsequent sessions.

The single native vector table stores logical document/unified-knowledge namespaces, point IDs, source types, owner/dataset/document/entity IDs, versions, text/metadata payloads and vector embeddings. Primary-key and scope indexes support filtered exact cosine search. This implementation does not yet provision an approximate HNSW/IVF index; larger deployments need workload-specific performance testing. Permission filters precede ranking, and returned knowledge hits are revalidated against current canonical records.

Switching back to Local copies the current catalog and vectors to the laptop backend, retaining current data rather than reopening an outdated catalog. Existing destination rows must belong to the same workspace; activation refuses an unrelated workspace. Target catalog snapshots and superseded target vectors are retained locally for recovery. Original PDFs and result files keep their individually pinned destinations. Re-activating the same OCI connection is idempotent. Processing jobs and recorded active tool runs block switching.

Storage also contains a collapsed **Advanced connections** section for provider defaults, queue and retrieval processing settings, OCI generation, encrypted connection profiles, safe exports and connection diagnostics. Model registrations and dataset mappings remain in their respective Model screens. Processing settings do not submit file or vector destination fields; those are configured by the dedicated sections above. Old Connections and Services & migration links redirect here. The mounted wallet files and encryption master key must remain available to both services across restarts.

## Destinations

Select Local or OCI Object Storage, enter the destination, test it, then save. Changing destinations is blocked while queued/running processing jobs exist. A test does not save the configuration. OCI testing checks bucket read access; the new resume onboarding verified actual object PUT and GET operations.

Local paths refer to the API/worker's mounted server root. On this Docker installation that root is `/data`, backed by the `aegis-oracle_storage` Docker volume on the laptop. Subdirectories such as `/data/resumes` are configurable. An arbitrary Windows directory must first be mounted into both API and worker; entering `C:\...` in the container path field does not mount it.

OCI configuration includes namespace, bucket, region, prefix, authentication mode, profile, config path and private-key path. The current destination is `bmyljaecivrj / mk-aegis`, region `ap-mumbai-1`, prefix `aegis`.

The deployment overlay `local/compose.oci-storage.yaml` installs the OCI SDK and mounts existing credential files read-only:

| Host file | Server path |
| --- | --- |
| `C:/Users/Laya/.oci/config` | `/run/oci/config` |
| `C:/Users/Laya/.oci/aegis_api_key.pem` | `/run/oci/aegis_api_key.pem` |

`AEGIS_OCI_CONFIG_HOST_PATH` and `AEGIS_OCI_KEY_HOST_PATH` in the ignored `.env.oracle` control these deployment mounts. Changing host mount locations requires recreating the two services. The UI can select available mounted server paths and config profiles. Existing credentials are used; no key is copied into an image, uploaded to a bucket, or returned in API responses.

Run the deployment with its OCI overlay:

```powershell
docker compose --project-directory . --env-file .env.oracle -f local/compose.oracle.yaml -f local/compose.gpu.yaml -f local/compose.oracle-client.yaml -f local/compose.agents-low-memory.yaml -f local/compose.oci-storage.yaml up -d --build --wait
```

## Existing files and revisions

Changing a destination does not migrate existing files. Local route descriptors pin every logical object and its dataset/document/extraction entity to its original destination. Original PDFs, derived text/index artifacts, prompt revisions and result revisions remain readable after switching providers or buckets. Legacy local files remain local; existing per-object OCI routes anchor later entity files as well.

New entities use the newly selected destination. A failed write does not silently fall back to another provider. Original uploads retain their bytes; validated extraction results use versioned JSON and checksum-verified Parquet. Dataset metadata remains authoritative in Oracle, with rebuildable semantic discovery in Qdrant. New application artifacts such as workflow checkpoints and conversation files also follow routed file storage. Configuration, secrets, diagnostics, registered model profiles, installed model weights and recovery archives remain local.

## Fresh start and recovery

Type `START FRESH` to archive and clear the active workspace. The operation archives canonical records and grants, jobs, local originals and derived files, prompts, extracted results, conversations, execution/checkpoint files and Aegis Qdrant collections before clearing the active catalog and indexes. Custom local storage roots within `/data` are included. Users, sign-in, registered models, credentials, storage configuration and installed model weights are retained.

Archives live under `/data/workspace-archives/<archive-id>`. Restore is available in the same screen when the active workspace is empty; type `RESTORE` and select its archive. Checksums are verified before restoring. An interrupted clear attempts automatic restoration after the verified archive is published.

This is an active-workspace reset, not a permanent purge. Already cloud-backed objects are retained for recovery and are never bulk deleted from the bucket. Restoring their references requires the original destination and credentials to remain accessible. Unrelated bucket objects are untouched. A fresh start never uploads old local files to OCI.

## Verified fresh resume workspace

The 2026-10-12 fresh start archived 31 datasets, 91 documents, 86 extraction results, 33 prompts and 152 conversations, along with their derived state and 39 Qdrant collections. The local recovery archive contains 2,083 files. The bucket prefix was empty before and immediately after the reset.

The replacement workspace has only `Resume Extraction`, one fictional resume PDF, one JSON Schema prompt and one completed extraction. See [live verification](ags_testing/OCI-STORAGE-2026-10-12.md).
## Active destination footer

Every signed-in workspace page shows a compact footer with the active **Files**, **Database** and **Knowledge** destinations (Local or OCI). Desktop labels also show the bucket, database name and search backend; hovering shows the region. File storage describes the destination for new files; existing objects retain their saved locations.

The footer reads `/api/storage/status`, a credential-free, authenticated summary of active routing. Saved drafts and connection tests do not affect these labels. It refreshes after activation, on browser focus and once per minute while visible. A failed status read displays “Status unavailable” rather than assuming Local. These labels describe routing, not continuous connectivity health checks.

