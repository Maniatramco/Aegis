# Password reset from the local app

In the local desktop app, choose **Forgot password?**, enter your existing
username, enter and confirm a new password (12-200 characters), then choose
**Reset password**. The username is prefilled. No terminal command, old password,
email, recovery code or private link is required. Return to sign in afterwards.

This is an explicit **trust-this-computer** policy: anyone able to use the local
installation can reset its administrator password. It is available only with
`AEGIS_LOCAL_ONLY=true`, SQLite, a direct loopback API connection, and a matching
configured local frontend origin. It is unavailable for remote and PostgreSQL
deployments. Forwarded/proxied recovery requests are refused. Do not enable this
mode for shared or remotely exposed installations.

The page discovers the configured local API port instead of assuming ports
3000/8000. An automatic, signed, five-minute CSRF challenge protects the form;
users do not handle it. Opening the page does not change the account. Invalid
fields, an unknown username, an expired form or a failed transaction leave the
password unchanged. The API replaces the password hash, revokes the
administrator's old sessions and invalidates any older private recovery links in
one transaction. Login and reset hold the same lock. Documents and account
identity are preserved, and services keep running throughout the reset.

## Legacy private browser recovery (local SQLite)

The trusted installation operator can open a private reset page while the local app runs:

```powershell
python scripts/open_password_recovery.py --database "<existing-data-folder>/control.db" --username "<existing-username>"
```

The account owner enters and confirms the new password privately in the browser. Never send passwords or recovery links in chat. The helper never prints the link; the browser removes its secret fragment immediately. Reloading or closing the page requires a fresh link.

Each 256-bit capability is hashed at rest, bound to the existing administrator, expires after five minutes and works once. Issuing a new link invalidates earlier links. There is no public link-issuance endpoint. Redemption requires local-only SQLite mode, a direct loopback connection, the exact local frontend origin and a CSRF cookie/header. The frontend proxy rejects recovery requests.

A protected backup is verified before resetting. The password update, old-session revocation and grant consumption commit together. Login and recovery share a filesystem lock. Identity, documents, indexes, configuration and other users remain intact. The browser never receives database paths or backup contents. This method is for the local single-computer launcher on ports 3000/8000; it is unavailable for remote or PostgreSQL deployments.

## Offline recovery alternative

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
