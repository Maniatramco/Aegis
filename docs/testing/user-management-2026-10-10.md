# Users and passwords verification — 2026-10-10

Implemented and deployed locally in the existing Oracle Docker stack. Open **Manage workspace → Users & passwords**.

## Behavior

The original bootstrap administrator can search/list accounts, create users, and reset colleague passwords after verifying their own current password. Every authenticated user can change their own password. Matching 12–200 character passwords are required. Usernames are unique and validated. Duplicate or invalid requests leave existing accounts unchanged.

Successful changes revoke all affected account sessions; other accounts keep their sessions. Documents, datasets and extraction results retain their ownership. Creation and update actors/timestamps use the existing Oracle `user_tbl` audit columns. No schema migration, new production container, or new password storage was introduced. Passwords remain scrypt hashes and are never returned by these endpoints. Validation errors omit submitted values. Anonymous reset remains disabled for Oracle/network deployments.

## Executed checks

- **605 backend tests passed, 4 skipped**, in 348.23 seconds. Includes 13 new account tests and the existing auth, CSRF, recovery, relational, workflow, agent and API documentation regressions. Most regression fixtures use isolated SQLite databases; skipped external-environment checks are not claimed as validated.
- **100 frontend unit checks passed** (97 existing script checks plus 3 extraction-directory checks). TypeScript check and final Docker production frontend build passed.
- **7 real Chromium browser scenarios passed against Oracle `AEGIS_TEST`**, using the actual application API and production frontend images. No API mocking. Administrator directory; mismatched/valid creation; duplicate rejection; ordinary-user restrictions and empty workspace; reset with current-password verification, old-password rejection and session revocation; self change and new-password login; desktop search/mobile layout.
- A disposable dataset remained accessible after administrator reset and self change. Both operations retained the same user ID. Oracle audit inspection verified `created_by = administrator`, and the later self change recorded `updated_by = the affected user ID`, with timestamps and `user_management` source.
- **User1 and User2 passed real HTTPS browser login → password screen → cancelled form → logout**, through the active shared link. User administration remained inaccessible to them. Their passwords were not changed.
- Desktop 1280×900 and mobile 390×844 screenshots were visually inspected. No browser JavaScript errors or mobile page overflow were observed.

Final evidence is in `results/user-management-2026-10-10/`. Browser test scripts: `frontend/tests/user-management-live.js` and `frontend/tests/user-management-shared-live.js`. Credentials enter the runners through stdin and are excluded from reports/screenshots.

## Runtime and limits

Updated and restarted the existing API, worker and web containers. Oracle, Qdrant and Ollama persistent data and hardware configuration were retained. The isolated account test used the dedicated Oracle test schema with fresh fictional accounts; those rows and temporary containers were removed afterward. Test service names were separated from production Docker DNS names before the final successful reruns.

The same application containers remain suitable for the prepared Kubernetes deployment configuration. No OCI cluster deployment or cluster verification was performed. Password change/reset is verified for the local Oracle installation and shared HTTPS route, not every future deployment environment.

No existing user passwords were changed, and no commit or push was made by this task. See `docs/USER-MANAGEMENT.md` for usage and recovery limits.
