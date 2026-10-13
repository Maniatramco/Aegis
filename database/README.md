# Aegis database

The local Oracle application schema is **AGS_OWNER**. The core schema has **12 custom tables**:
8 workflow tables, model configuration, dataset/model mappings and one internal
compatibility catalog, plus user/dataset assignments. These are Aegis tables, not Oracle built-in tables.

OCI/native Oracle vector storage additionally creates `aegis_knowledge_vectors`
through `backend/app/oracle_vectors.py`, giving 13 application tables in that mode.
Its native `VECTOR` DDL is separate from the SQLAlchemy table generator below.

| Folder/file | Purpose |
| --- | --- |
| `schema/` | Owner provisioning and owner verification |
| `tables/` | Twelve table scripts, foreign keys, checks and indexes |
| `install.sql` | Ordered SQLcl/SQL Developer installation for an empty schema |
| `migrations/` | Existing AEGIS data-copy procedure and rollback boundaries |
| `queries/oracle-queries.sql` | Read queries for datasets, models, jobs, extractions and reviews |
| `docs/DATA-MODEL.md` | Relationships, columns, audit semantics and storage boundaries |
| `docs/VALIDATION.md` | Local verification and remaining deployment checks |

The application creates tables automatically on a fresh installation. Alternatively,
connect as AGS_OWNER and run `@database/install.sql` from the project root on an empty
schema. Do not run the install script over existing tables. Oracle DDL commits
implicitly. `generate_tables.py` regenerates scripts from the application's actual
SQLAlchemy metadata; it requires the backend and Oracle Python dependencies.

Existing installations must follow [the migration procedure](migrations/01_aegis_to_ags_owner.md).
Do not simply change an old database's username and assume its data will move.

For the laptop connection, use **Aegis-Local** in Oracle SQL Developer for VS Code
and open `database/queries/oracle-queries.sql`. The saved connection now uses AGS_OWNER.
Database passwords remain in private secrets/connection storage.

User access is controlled by `USER_DATASET_TBL`. The application adds this table
on first startup and preserves access for existing non-admin dataset owners once.
Later startups never restore revoked assignments. Revocations retain the row
with `ENABLED = FALSE` and update its audit columns. Every account with role `administrator`
has access to every dataset without explicit assignments. See
`queries/user-dataset-access.sql` and [dataset access](../docs/DATASET-ACCESS.md).

User roles are stored in `USER_TBL.ROLE`. Existing installations add the column
automatically at startup; see [user roles migration](docs/USER-ROLES.md).

Full schema details: [DATA-MODEL.md](docs/DATA-MODEL.md).
