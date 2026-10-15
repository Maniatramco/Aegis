# Oracle database scripts

Use the single [final OCI deployment PDF](../ags_docs/Aegis_OCI_Deployment_Guide.pdf) for target inputs, database-only or combined releases, approvals and verification. The supported handover entry point is `ags_deploy/deploy.ps1` with the non-secret destination JSON. This folder is a script/reference package, not a separate deployment guide.

`DB_Object: "Y"` and `DB_ReleaseFile: "ags_database/release.json"` select the ordered object release. Set `DeployFrontend` and `DeployBackend` to `"N"` for database-only execution. The manifest can permit a missing application user/schema inside an existing OCI database. Matching definitions are skipped, missing supported objects are created, and incompatible definitions stop the release. Existing users, grants, quotas, objects and rows are preserved. No physical database, tablespace or OCI infrastructure is provisioned.

The maintained native Oracle SQL was compared read-only with the live OCI `agsora` schema on 16 October 2026: 13 tables, 165 columns, 49 foreign keys and 20 explicit indexes matched. The service is Autonomous AI Database 26ai; the connected server reported `23.26.4.1.0`. These scripts contain no application data or credentials.

| File or folder | Purpose |
| --- | --- |
| `release.json` | Ordered list of 13 committed SQL files and explicit missing-schema permission |
| `ags_tables/` | Native CREATE TABLE and CREATE INDEX definitions, including Oracle vectors |
| `ags_schema/verify_live_schema.sql` | Read-only owner/service, tables, columns, constraints and vector verification |
| `ags_queries/` | Read-only workflow/account/dataset-access inspection |
| `deploy-oci-database.ps1` and `install.sql` | Retained guarded SQLcl fresh empty-owner installer used for legacy support; not the current Y/N handover entry point |

Object releases support the maintained table/index definitions, not arbitrary migrations, ALTER/DROP or DML. The legacy installer requires an empty owner and is not safe to replay over an initialized schema. Oracle DDL can commit partially; inspect the exact release record and completed objects before an approved retry. No automatic rollback is provided.

Local Oracle Free setup and the local schema generator are under [ags_local_use/ags_database](../ags_local_use/ags_database/). SQLAlchemy remains part of the live backend's Oracle access layer. Do not regenerate the maintained OCI scripts using the local generator.

Keep wallets and credentials outside Git. Use private terminal prompts; never add passwords to the manifest, JSON, SQL or command arguments. Creating an empty application schema does not import the original workspace or initialize saved application configuration.
