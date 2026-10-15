# Users, passwords and administrator roles

Every successful sign-in opens **Home**, for administrators and ordinary users.

Open **Manage workspace > Users & passwords**. The same screen and API work with Oracle in Docker and the prepared Kubernetes deployment.

## Make another user an administrator

1. Sign in as an administrator.
2. Create the account with **Add user** if it does not exist. Accounts start as ordinary users with no dataset assignments.
3. Find the account and click **Change role**.
4. Choose **Administrator**, enter your own administrator password, and click **Save role**.
5. Ask that person to sign in again. A successful role change signs out all sessions for the affected account.

Any administrator can manage accounts, reset passwords, change roles, configure datasets/models and access every dataset. Changing a username never grants access. The server checks the stored role on requests.

To remove administrator access, choose **User** in the same form. The person then sees only their previously saved dataset assignments. Administrators have implicit access to every dataset; their existing explicit assignments are retained while promoted. Configure assignments after demotion if needed. The last administrator cannot be demoted. Self-demotion is allowed when another administrator remains and signs the acting user out.

The initial account is migrated to Administrator once when the role column is introduced. Its password, data and existing assignments are preserved. Subsequent restarts respect role changes, including demotion of the original account. Roles and account audit metadata are stored in `AGS_OWNER.USER_TBL`; no additional table or container is needed.

## Passwords and dataset assignments

- Any signed-in user can change their own password with their current password and matching new passwords.
- An administrator reset requires the acting administrator's password. Password and role changes preserve files and extraction results and revoke all affected sessions.
- New passwords must contain 12-200 characters. Usernames support letters, numbers, `.`, `_`, `@`, and `-`, without spaces.
- Passwords and hashes are never returned by the account directory. Share credentials privately.
- Account creation, password and role changes record the acting account, creation/update timestamps and source. Unknown historical actors remain unknown.
- Click **Dataset access** for an ordinary user to assign datasets. Assigned users share documents and extraction results; conversations remain private. See [Dataset access](DATASET-ACCESS.md).
- Anonymous recovery is disabled in the shared Oracle installation. Contact an administrator; operator recovery is needed if no administrator can sign in.

## Delete a user and remove access

An administrator can use the trash action beside a user in **Manage workspace > Users & passwords**. Enter the acting administrator password and type the exact target username, then select **Delete user and remove access**. Cancel leaves the account unchanged.

Deletion removes the account, every sign-in session and all enabled or disabled dataset assignments in one database transaction. Shared datasets, documents, model mappings and extraction results are preserved. Private conversation and agent-workflow metadata is removed from the active catalog and retained with its original artifact references in a protected operator archive under `/data/account-archives/`; private payload files are not purged. The archive excludes passwords, password hashes and session credentials. Historical database audit references are cleared to avoid dangling foreign keys, with their original references retained in that archive. There is no user-facing archive restore action.

The signed-in account and last administrator cannot be deleted. Accounts owning shared content or processing jobs must resolve that ownership first; deletion rejects the request without removing access. Ordinary users cannot delete accounts. The server rechecks administrator rights under the account mutation lock and requires both the current password and username confirmation for HTTP requests.

## API

`GET /api/users`, `POST /api/users`, `DELETE /api/users/{user_id}`, `PATCH /api/users/{user_id}/role`, `POST /api/users/{user_id}/password`, and `POST /api/auth/password`.

Role changes accept `{"role":"administrator","current_password":"<acting administrator password>"}` or role `user`. Cookie-authenticated mutations require the session CSRF token. Incorrect password checks are rate limited. Validation responses omit submitted values. The role endpoint returns the updated public account and whether sessions were revoked; an unchanged role leaves sessions intact.

The delete action was deployed and its confirmation/cancel flow verified on the OCI Users screen on 15 October 2026.
