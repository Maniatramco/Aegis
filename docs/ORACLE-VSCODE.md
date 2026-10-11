# Query the local Aegis Oracle database in VS Code

Oracle SQL Developer for VS Code is installed on this laptop. The saved
connection **Aegis-Local** uses Oracle's common connection store with its saved
password in the private wallet, rather than a password in the repository.

1. Open Oracle SQL Developer from the VS Code activity bar.
2. Refresh Connections if needed, then connect to **Aegis-Local**.
3. Open `DB/queries/oracle-queries.sql`. Select **Aegis-Local** using the connection
   selector at the bottom of the editor, if the file is not already attached.
4. Select a statement and press **Ctrl+Enter**. You can also right-click the
   connection and open a SQL Worksheet, then paste a query.

| Connection field | Value |
| --- | --- |
| Host | `127.0.0.1` |
| Port | `1521` |
| Service name | `FREEPDB1` |
| Username | `AGS_OWNER` |
| Role | Default |

The database login differs from your Aegis application login. The current
connection uses the Aegis database schema account. No database administrator
credentials are needed to view its tables.

`EXTRACT_TBL` stores extraction IDs, statuses, names, ownership and storage
references. `JOB_TBL` stores running state, progress, attempts and errors. Original
documents, merged files, extracted JSON and detailed provenance remain in the
persistent application storage volume. Application timestamps are Unix epoch
seconds. The query file intentionally does not select password hashes or login
tokens from the `USER_TBL` / `SESSIONS_TBL` tables.

For table responsibilities, columns, relationships, statuses and storage layout,
see [the Aegis data model](../DB/docs/DATA-MODEL.md). The current AGS_OWNER schema
has eleven custom tables, including categorized model configuration and dataset
mappings. Table scripts and migration details are under `DB/`.

## Keep the laptop connection available after recreating containers

Docker Desktop must be running. The optional client Compose override publishes
Oracle only at `127.0.0.1:1521`. It is separate from the CPU/GPU configuration
and is not required for Oracle Kubernetes deployment.

From the configured live project directory (`Aegis` on this laptop), run:

```powershell
docker compose --env-file .env.oracle -f compose.oracle.yaml -f compose.oracle-client.yaml up -d --no-deps --wait --wait-timeout 300 oracle
```

This only targets the database and preserves the running Ollama hardware mode
and all data volumes. Applying the override the first time, or removing it,
recreates the database container and briefly interrupts database access.

For a full GPU stack startup with laptop database access, include both optional
overrides:

```powershell
docker compose --env-file .env.oracle -f compose.oracle.yaml -f compose.gpu.yaml -f compose.oracle-client.yaml up -d --wait
```

On a CPU-only machine omit `compose.gpu.yaml`. Starting/recreating the database
with only the base Compose configuration removes laptop port access; reapply the
client override to enable it. No host port publishing is added to the Kubernetes
manifests.

To disable laptop database access while preserving data:

```powershell
docker compose --env-file .env.oracle -f compose.oracle.yaml up -d --no-deps --wait --wait-timeout 300 oracle
```

Verified locally on 2026-10-10 using the SQLcl bundled with Oracle's VS Code
extension: host TCP login, schema table listing, every statement in
`oracle-queries.sql`, and the latest merged extraction ID/status. The desktop
extension's graphical worksheet was not operated automatically.

Oracle documentation:
- https://www.oracle.com/database/sqldeveloper/vscode/
- https://docs.oracle.com/en/database/oracle/sql-developer-vscode/26.2/sqdnx/creating-connection.html
