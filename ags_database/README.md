# Live OCI Oracle database reference

`ags_database/` contains native Oracle SQL aligned with the deployed `agsora`
Autonomous AI Database in `ap-mumbai-1`. Read-only inspection on
15 October 2026 at 23:54 IST (18:24 UTC) confirmed owner `ADMIN`, mTLS wallet alias
`agsora_low`, and all thirteen application tables. OCI identifies
the database as Oracle 26ai; the connected server reports `23.26.4.1.0`.
No application data or credentials are included in these scripts.

Local Oracle Free owner creation, the SQLAlchemy-based local DDL generator,
its twelve-table installer and generated SQL now live under
[`ags_local_use/ags_database/`](../ags_local_use/ags_database/).
SQLAlchemy remains part of the live backend's Oracle access layer. Moving the
local tooling does not remove or replace that runtime dependency.

## Files and responsibilities

| Folder or file | Purpose |
| --- | --- |
| `ags_tables/` | Thirteen Oracle table definitions read from live metadata, including native vectors |
| `install.sql` | Ordered reference installer for a separate empty, prepared Oracle application schema |
| `ags_schema/verify_live_schema.sql` | Read-only connection, table, column, constraint and vector checks |
| `ags_queries/` | Read-only workflow, account and dataset-access inspection using the connected owner |

## Verification and installation boundary

Use a fresh SQLcl or SQL Developer connection with the intended destination's
wallet and private database credentials. The current live connection uses
`agsora_low` and owner `ADMIN`. Keep passwords and wallets outside Git.

For read-only verification from the repository root, run:

```sql
@ags_database/ags_schema/verify_live_schema.sql
```

The script reads schema metadata and checks native vector support. The diagnostic
queries use unqualified application table names, so they run in the connected
schema rather than assuming the old local `AGS_OWNER` schema.

`install.sql` and `ags_tables/*.sql` are logical schema references and an optional
rebuild path for an empty, separately prepared Oracle 26ai application schema.
They are not upgrade scripts for the populated live database. Oracle DDL commits
implicitly. No installer, table creation, user creation, migration, grant or
data-changing SQL was executed while aligning this folder.

The SQL preserves the observed 165 columns, defaults, collations, primary/unique/
foreign/check constraints and twenty application indexes. Schema qualification
and Autonomous Database managed physical storage clauses are omitted so a
reviewed destination can use its own owner and storage defaults. LOB/system and
constraint-backed indexes are managed by Oracle rather than duplicated as
separate application index statements.

The local-only generator writes exclusively inside `ags_local_use/ags_database/`;
it cannot overwrite this OCI schema reference. Local setup and the legacy
`AEGIS` to `AGS_OWNER` procedure are documented in
[`ags_local_use/README.md`](../ags_local_use/README.md#local-database-tools).

## Tables and keys

| Table | Primary key | Purpose / main fields |
| --- | --- | --- |
| `USER_TBL` | `ID` | Username, password hash, role (user/administrator) and account audit |
| `SESSIONS_TBL` | `ID` | Hashed login token, owner, expiry and CSRF protection |
| `DATASET_TBL` | `DATASET_ID` | Owned dataset, name and status |
| `USER_DATASET_TBL` | `USER_ID, DATASET_ID` | User/dataset assignment, enabled flag and creation/update audit |
| `DOCUMENT_TBL` | `DOCUMENT_ID` | Dataset, filename, merged flag, storage reference, bytes and status |
| `PROMPT_TBL` | `PROMPT_ID` | Filename, version, schema reference, owner and optional dataset |
| `EXTRACT_TBL` | `EXTRACT_ID` | Dataset, document, prompt/version, result/version, status and error |
| `REVIEW_TBL` | `REVIEW_ID` | Extraction, reviewed input version, saved review version and result reference |
| `JOB_TBL` | `ID` | Indexing/extraction task, target, status, progress, attempts, lease and error |
| `MODEL_CONFIG_TBL` | `MODEL_ID, CATEGORY` | Model name, provider model, category, configuration reference, version and enabled flag |
| `DATASET_MODEL_TBL` | `DATASET_ID, MODEL_ID, CATEGORY` | Dataset/category model mapping, enabled and default flags |
| `AEGIS_ITEMS` | `ID` | Internal entity catalog: kind, owner, parent, reference, status and version |
| `AEGIS_KNOWLEDGE_VECTORS` | `COLLECTION_NAME, POINT_ID` | Native vectors, dimensions, payload and owner/dataset/document scope |

Core account/session/job keys retain the physical column name `ID` to preserve
existing application interfaces. Workflow entity IDs equal their catalog IDs;
they are not new IDs invented during migration. There is no separate `records`
table in the active Oracle schema: that legacy catalog is now `AEGIS_ITEMS`.

## Workflow relationships

```mermaid
erDiagram
    USER_TBL ||--o{ SESSIONS_TBL : owns
    USER_TBL ||--o{ DATASET_TBL : owns
    USER_TBL ||--o{ USER_DATASET_TBL : assigned
    DATASET_TBL ||--o{ USER_DATASET_TBL : authorizes
    DATASET_TBL ||--o{ DOCUMENT_TBL : contains
    DATASET_TBL o|--o{ PROMPT_TBL : scopes
    DATASET_TBL ||--o{ EXTRACT_TBL : contains
    DOCUMENT_TBL o|--o{ EXTRACT_TBL : supplies
    PROMPT_TBL o|--o{ EXTRACT_TBL : guides
    EXTRACT_TBL ||--o{ REVIEW_TBL : reviewed
    EXTRACT_TBL o|--o{ JOB_TBL : processes
    DOCUMENT_TBL o|--o{ JOB_TBL : indexes
```

Oracle enforces these foreign keys. Each owned workflow entity also references
`USER_TBL.ID`. Dataset/document/prompt/extraction/model configuration IDs reference
their catalog entry, with cascade deletion of their projection when that catalog
entry is deleted. The catalog's general `PARENT_ID` remains a compatibility field;
named workflow tables provide actual dataset foreign keys.

Global prompts have a NULL dataset. Document deletion sets extraction/job document
links to NULL while preserving historical extraction/job IDs. Prompt deletion sets
the extraction prompt link to NULL. Extraction deletion removes its reviews and
clears job extraction links. A job can have at most one of `DOCUMENT_ID` and
`EXTRACT_ID`; both may be NULL for deleted or historical targets. `TARGET_ID`
retains the original target string.

## Dataset permissions

`USER_DATASET_TBL` is a many-to-many mapping. Accounts with
`USER_TBL.ROLE = 'administrator'` manage accounts, assignments and dataset/model
configuration and access every dataset. Ordinary users see only enabled
assignments. Role changes preserve explicit assignments, revoke affected sessions,
and cannot remove the last administrator. Assigned users share dataset documents, scoped prompt templates,
extraction results, reviews and workflow jobs. Conversations and Agent plans
remain private to their creator and require continuing access to their dataset.
Global prompts remain owner-scoped.

Uploads and extraction jobs use the dataset's storage owner so model workers and
vector indexes stay consistent. `CREATED_BY` records the authenticated uploader
or requester, rather than treating the storage owner as the person who acted.
Each assignment has the standard creation/update timestamps, actor foreign keys
and source fields. Revocation disables a row without losing its creation audit;
reassignment enables that same row. Startup only grants legacy owners access
when the mapping table is first introduced, never after an administrator revokes it.

## Model configuration and dataset mapping

```mermaid
erDiagram
    USER_TBL ||--o{ MODEL_CONFIG_TBL : owns
    DATASET_TBL ||--o{ DATASET_MODEL_TBL : selects
    MODEL_CONFIG_TBL ||--o{ DATASET_MODEL_TBL : maps
    MODEL_CONFIG_TBL {
        string MODEL_ID PK
        string CATEGORY PK
        string PROVIDER_MODEL
        boolean ENABLED
    }
    DATASET_MODEL_TBL {
        string DATASET_ID PK
        string MODEL_ID PK
        string CATEGORY PK
        boolean IS_DEFAULT
        boolean ENABLED
    }
```

`CATEGORY` is constrained to `chat`, `extraction` or `embedding`. A registered model
supporting chat and extraction has two category rows with the same model ID.
The composite mapping foreign key requires the category to exist on that model.
The application validates ownership, availability and defaults when mapping
models to a dataset. One-default-per-category is an application rule, not a
database unique constraint. Removed capabilities remain disabled so historical
mapping references do not break. Query both mapping and model enabled flags when
checking availability. Provider endpoints, credentials and advanced options
remain in the referenced configuration/secret storage, not duplicated in this table.

## Audit columns on every table

| Column | Meaning |
| --- | --- |
| `CREATED_AT` | Creation time, Unix epoch seconds (`BINARY_DOUBLE`) |
| `CREATED_BY` | Account ID, nullable foreign key to `USER_TBL.ID` |
| `UPDATED_AT` | Most recent application update time, Unix epoch seconds |
| `UPDATED_BY` | Account on whose behalf the update ran, nullable foreign key |
| `CREATED_VIA` | Source such as `api`, `worker`, `operator`, `legacy` or `migration` |
| `UPDATED_VIA` | Source of the latest update |

Application transactions maintain audits and named workflow projections together.
Worker updates identify the owning account and `worker` source; they do not imply
that the user manually performed each background step. Operator account
provisioning has an unknown actor (NULL), rather than crediting the new account
for its own creation. Historical creators/updaters were never recorded and remain
NULL. Legacy account/session timestamps mark import time, not a recovered creation
date. Known review actors/times are recovered from saved review JSON.

These are application audit hooks, not database triggers. Direct SQL edits do not
automatically populate audits, update JSON payloads or rebuild vector indexes.
Use the application for writes; use the supplied SQL to inspect data. The audit
columns identify current creation/update metadata, not a full event history.

## Extraction, merging and review history

`EXTRACT_ID` tracks a logical extraction; re-extraction increments its version and
creates another background job under the same ID. Independent extraction creates
one extraction ID per document. Single extraction of multiple files creates a
real merged document with its merged filename. `DOCUMENT_TBL.IS_MERGED` marks it;
the extraction links to that merged document and preserves all original source
IDs, names and merge details in its versioned JSON.

Older combined selections without a physical merged document have a NULL
extraction `DOCUMENT_ID`, rather than misleadingly linking the first source.
Their original source list remains in the retained result JSON. Merge membership
is not represented by a separate relational join table in this implementation.

Extraction status is the entity's state (`queued`, `ready`, `failed`); job status
and progress describe current processing (`queued`, `running`, `completed`,
`failed`, `cancelled`). Inspect both tables to distinguish pending data from a
running task. Status strings follow the existing application lifecycle.

Each saved review has a separate UUID `REVIEW_ID`. The unique pair
`EXTRACT_ID, REVIEW_VERSION` prevents duplicate history rows. `EXTRACTION_VERSION`
identifies the version reviewed; `REVIEW_VERSION` is the resulting saved JSON
version, not a sequential review count. Example: extraction v1, review v2,
re-extraction v3, second review v4. Review result references retain their individual
JSON versions instead of replacing earlier reviewed content.

## SQL and content storage

Oracle stores workflow metadata, relationships, statuses, references and audits.
Original/merged files, prompt schemas, extracted field values, citations, merge
source lists and review JSON remain in persistent application storage (or the
configured OCI Object Storage). The current OCI installation stores vectors in
Oracle Autonomous AI Database through the separate `aegis_knowledge_vectors` table.
Qdrant belongs to the alternative local/self-hosted configuration. The thirteen scripts in `ags_tables/` include the separate native vector
table. Relational tables retain references rather than the full extracted fields.

`AEGIS_ITEMS` and versioned payloads remain the application's compatibility source;
the named tables are transactionally maintained relational views of those entities,
implemented as physical tables. Writing projection tables directly does not update
the catalog. Native SQLite retains legacy core names to preserve existing native
workspaces. The verified live owner is `ADMIN`; local Oracle Free setup remains
under `ags_local_use/ags_database/`.

Exact column definitions, constraints and indexes are in `ags_database/ags_tables/*.sql`.
The query file shows joins and readable time conversion without selecting
password hashes, session/CSRF tokens or provider secrets.

## User roles

`USER_TBL.ROLE` is required, defaults to `user`, and accepts `user` or `administrator`. `ags_tables/01_user_tbl.sql` describes fresh installation; do not run the fresh install script over existing tables.

API and worker startup automatically add the role column to legacy installations and promote the existing account with ID `administrator` once. Restarting after an intentional demotion does not restore its role. Existing account IDs, passwords, sessions, ownership, dataset assignments and result references are retained. Updating roles through the application revokes affected login sessions and writes account audit metadata. The API locks account rows when changing roles to prevent simultaneous demotions from removing the last administrator.

Any existing administrator can use **Manage workspace > Users & passwords > Change role** and confirm using their own password. Use the application rather than direct SQL updates, which bypass session revocation and last-administrator protection.

Read-only inspection:

```sql
SELECT id, username, role, created_at, updated_at, updated_by, updated_via
FROM user_tbl
ORDER BY username;

SELECT role, COUNT(*) AS account_count
FROM user_tbl
GROUP BY role;
```

See [the account guide](https://github.com/Maniatramco/Aegis/blob/a33d5fba9e5c9c62319bb65c42a0341eed8de238/ags_docs/ags_guides/USER-MANAGEMENT.md) and [the relational model](#tables-and-keys). No additional application table or container is required.
