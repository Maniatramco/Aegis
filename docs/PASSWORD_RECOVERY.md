# Local administrator password recovery

If you saved your password in a password manager, try that first. Aegis stores a
salted scrypt hash; the original password cannot be retrieved. First-run setup
does not reset an existing administrator.

`scripts/reset_admin_password.py` is an **offline operator tool for SQLite**.
It requires trusted filesystem access to the existing database. It creates no
account, changes no account ID or username, and adds no network recovery route.
Documents, datasets, models, provider configuration and encrypted secrets stay
unchanged. Only the selected existing administrator's password hash is replaced;
all its sessions are revoked in the same transaction.

## Owner-run steps

1. Stop **all Aegis API and worker processes**, including other replicas sharing
   this database. Stop the frontend too. Ollama can remain running. Stopping the
   API prevents a concurrent login from creating a session against the old hash.
2. Open a private interactive terminal as the account that owns the installation.
   Use the exact existing SQLite `control.db`, not an empty/new database. This
   tool does not read `.env`, guess the data directory, or support PostgreSQL.
3. Run the command, replacing the example paths and username as appropriate:

   ```powershell
   .\.venv\Scripts\python.exe scripts/reset_admin_password.py --database "C:\path\to\runtime\demo-data\control.db" --username admin --services-stopped
   ```

   Linux/macOS: use the corresponding Python environment and absolute database
   path. The backend dependencies are not needed by the tool itself.

4. **Enter and confirm the new password yourself** at the two hidden prompts
   (12–200 characters), then type `RESET` to submit. Never paste the password into
   chat, command arguments, environment variables, logs, or a ticket. Piped input
   and terminals that cannot hide input are refused. Cancellation leaves the
   account unchanged.
5. Restart Aegis normally and sign in with the new password. Old sessions no
   longer authorize requests; documents and model mappings remain available.

The local port check (3000/8000) is an additional guard, **not proof** that every
replica is stopped. `--services-stopped` is your explicit confirmation of step 1.
Custom ports/remote replicas must be stopped manually as well.

## Backup and failure behavior

Before any credential change, the tool takes a consistent SQLite backup while
holding a write reservation. The unique `password-recovery-*` directory beside
the database is private: mode 0700 on POSIX, or an explicit current-user-only
inheritable ACL on Windows. The backup file is created with mode 0600 and inherits
that restricted Windows ACL. Permission/backup/check failures abort the change.
The password update and session revocation commit together or roll back together.

The backup contains sensitive metadata, old credential hashes, and old sessions.
Keep it on private local storage and do not upload or commit it. It is a database
backup, not a copy of original document files. Existing originals are untouched.
Do not restore it casually: restoring it can restore the old credential and
sessions. A failed reset can leave a protected backup for operator diagnosis.

No agent should enter or submit the owner's password. Test recovery only against
isolated synthetic accounts. There are no password flags, default passwords,
bootstrap-token reuse, email delivery, subscriptions, or cloud calls.
