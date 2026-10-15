# User roles migration

`USER_TBL.ROLE` is required, defaults to `user`, and accepts `user` or `administrator`. `01_user_tbl.sql` describes fresh installation; do not run the fresh install script over existing tables.

API and worker startup automatically add the role column to legacy installations and promote the existing account with ID `administrator` once. Restarting after an intentional demotion does not restore its role. Existing account IDs, passwords, sessions, ownership, dataset assignments and result references are retained. Updating roles through the application revokes affected login sessions and writes account audit metadata. The API locks account rows when changing roles to prevent simultaneous demotions from removing the last administrator.

Any existing administrator can use **Manage workspace > Users & passwords > Change role** and confirm using their own password. Use the application rather than direct SQL updates, which bypass session revocation and last-administrator protection.

Read-only inspection:

```sql
SELECT id, username, role, created_at, updated_at, updated_by, updated_via
FROM ags_owner.user_tbl
ORDER BY username;

SELECT role, COUNT(*) AS account_count
FROM ags_owner.user_tbl
GROUP BY role;
```

See [the account guide](../../ags_docs/ags_guides/USER-MANAGEMENT.md) and [the relational model](DATA-MODEL.md). No additional application table or container is required.
