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

## API

`GET /api/users`, `POST /api/users`, `PATCH /api/users/{user_id}/role`, `POST /api/users/{user_id}/password`, and `POST /api/auth/password`.

Role changes accept `{"role":"administrator","current_password":"<acting administrator password>"}` or role `user`. Cookie-authenticated mutations require the session CSRF token. Incorrect password checks are rate limited. Validation responses omit submitted values. The role endpoint returns the updated public account and whether sessions were revoked; an unchanged role leaves sessions intact.

Cluster deployment has not been performed as part of this change.
