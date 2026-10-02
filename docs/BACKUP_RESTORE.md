# Coordinated backup and restore

Aegis has more than one state store. A PostgreSQL-only dump is incomplete: original documents and content artifacts live in the data volume. Conversely, a data-volume copy does not preserve users, ownership, job states and object references in PostgreSQL.

## What to preserve

- PostgreSQL metadata dump, including ownership mappings and job/extraction status.
- Complete application `/data` volume, including document originals, parsed/chunk artifacts, conversations, template schemas and extraction outputs.
- Application version/image digest, configuration choices, schema version and embedding/chunking model versions.
- Original `.env`, authentication secret and any master/encryption key, in a separate protected recovery system. Do not commit or package these into a public repository. Losing an encryption key can make the data backup unusable.

The root backup script deliberately excludes Qdrant. Its index is derived and must be rebuilt after restore. Restoring metadata that says "indexed" does not populate an empty Qdrant collection.

## Backup procedure (local storage provider only)

These bundled scripts check the active storage provider and refuse OCI-mode backup or restore. They do not download OCI Object Storage objects. When OCI storage is active, create a separately verified remote-object snapshot/manifest coordinated with the database. Do not treat a `/data` archive as a complete OCI-mode backup.

1. Announce a maintenance window and stop user writes.
2. Run the repository `scripts/backup.sh` according to the root README. The script stops `web`, `api` and `worker` before taking a PostgreSQL logical dump and an archive of `/data`. Do not manually restart writers between these steps.
3. Confirm the command succeeded, both components exist, and their file sizes are plausible. Record a UTC recovery timestamp and application/configuration versions. Record SHA-256 hashes of the backup artifacts in a manifest stored with the backup.
4. Keep the whole bundle together and encrypt it in an access-controlled backup destination. Transfer to a different failure domain; an archive on the same disk is not disaster recovery.
5. Store the matching secrets separately with restricted, auditable recovery access. Verify their recoverability without printing them to logs.
6. Check the script's exit status. The backup script restarts writers through an exit trap, including after a backup failure, because backup does not modify source data. Restart does not mean the backup succeeded: inspect and retry failures, and never label a partial bundle recoverable. Restore has different behavior and leaves writers stopped on failure.

This is a cold application backup, so it is intentionally disruptive. `pg_dump` alone provides a database snapshot but cannot atomically snapshot unrelated content files. Stopping every writer is what provides cross-store consistency. An independent uploader, administrative job or second deployment writing the same stores must also be paused.

## Restore procedure

Prefer a clean isolated deployment. Restoring over live data discards changes since the backup. Obtain explicit operator approval and keep a fresh safety backup of the destination before overwriting it.

1. Verify backup origin, integrity hashes, completeness and compatible application/database versions. Never restore an untrusted SQL/archive file.
2. Restore the corresponding environment configuration and required encryption/authentication keys through the deployment's secret mechanism. Do not paste credentials into shell history.
3. Follow the root README's `scripts/restore.sh` invocation. The script requires `--confirm-overwrite` and stops application writers while restoring metadata and content.
4. On any restore failure, leave writers stopped. Repair in the isolated target or restart the restore from a verified backup; do not expose a partially restored application.
5. Rebuild Qdrant from the restored durable sources using the supported ingestion/reindex mechanism. If no bulk reindex command exists in the shipped release, use documented per-document reingestion or implement and test a dedicated recovery command before adopting the release for production. Never claim the index was recovered merely because metadata rows were restored.
6. Preserve original embedding model/dimensions, collection scope and chunking version for the rebuild, or explicitly create a new index version. Do not mix vectors with different dimensions/model semantics.
7. Complete the verification below, then reopen user access. Keep the old deployment and backup untouched until cutover is accepted.

The scripts' exact arguments and service names are defined in the repository scripts and README. This document does not imply a remote/cloud restore has been rehearsed.

## Required restore drill

Run in an isolated environment and retain an evidence report:

- Validate metadata row counts and referential integrity.
- Sample users across ownership boundaries; unauthorized users must not read another user's documents, conversations, schemas or extraction results.
- Download original documents and compare stored checksums/byte sizes with the pre-backup manifest.
- Read saved conversations, template versions and extraction results, including any encrypted artifacts.
- Rebuild and query the retrieval index; confirm cited document IDs/pages resolve to restored originals.
- Recover an interrupted job without duplicate visible results; confirm completed jobs are not inadvertently billed again.
- Test login and session behavior with the restored auth configuration.
- Measure elapsed recovery time and data gap. Record actual RTO/RPO; do not substitute vendor DB availability targets for application recovery measurements.
- Confirm backups and plaintext temporary restores are accessible only to intended operators and retained/deleted under the approved policy.

## OCI notes

OCI managed PostgreSQL backups cover the database service, not Aegis Object Storage or an external index. Oracle supports scheduled and manual backups and cross-region copies; choose retention for the business requirement and test restoration. A restore can lose newer data, so create a pre-restore safety backup. [Database backups](https://docs.oracle.com/en-us/iaas/Content/postgresql/backups.htm), [restore warning](https://docs.oracle.com/en-us/iaas/Content/postgresql/restore-db-from-backup.htm)

For an Object Storage migration, retain a manifest mapping each DB object reference to an immutable object key, checksum and version. Versioning is useful protection but replication does not carry all historical versions; do not call replication alone a complete backup. [Object versioning](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm)
