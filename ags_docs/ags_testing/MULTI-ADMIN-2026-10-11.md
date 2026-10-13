# Multiple administrators acceptance — 2026-10-11

The running Docker application at `http://localhost:3003` now stores account roles in Oracle `AGS_OWNER.USER_TBL.ROLE`. Any administrator can promote/demote accounts through Users & passwords using their own current password. Target sessions are revoked, saved dataset assignments are retained, and the last administrator is protected. No production account was promoted by this test.

## Automated checks

- Backend regression: **648 passed, 4 skipped**, 100.95 seconds, inside the Linux API container with isolated SQLite test databases. The skipped integration cases require separate environment configuration.
- Focused role checks: **11 passed**, 11.05 seconds, including concurrent demotion, CSRF, password verification, legacy migration, session revocation, original-account demotion persistence, model/profile access and dataset model mapping by a second administrator.
- Frontend unit checks: **104 passed**, including four role form/access/error/sign-out cases.
- TypeScript validation and the production Next.js Docker build passed.

## Browser acceptance with Oracle

Real Chromium interacted with the updated web/API containers using the isolated Oracle **AEGIS_TEST** schema. Credentials were supplied privately on stdin. The internal Docker test origin was treated as secure for browser APIs, matching the secure-context behavior of the production localhost URL. No model inference was needed for account role checks.

| Check | Result | Observed duration |
| --- | --- | --- |
| Administrator directory and new-user creation in browser | Passed | 3.361 s |
| Last administrator cannot demote themselves | Passed | 0.341 s |
| Dataset assignment UI and ordinary user access enforcement | Passed | 2.231 s |
| Wrong acting password rejects promotion without changing sessions | Passed | 0.338 s |
| Promotion signs out target; new administrator accesses users, all datasets and models | Passed | 2.007 s |
| Self-demotion signs out and displays the correct role-change message | Passed | 2.047 s |
| Second administrator restores original account through UI | Passed | 1.817 s |
| Demotion retains assigned data scope and removes configuration privileges | Passed | 1.594 s |
| Desktop and mobile role controls fit the viewport; no JavaScript errors | Passed | 0.285 s |

Oracle startup was rerun after testing: the final administrator/user roles persisted, the role check constraint was present, and role audit fields identified the acting account. Desktop and mobile screenshots were inspected; the mobile form fits a 390-pixel viewport and no browser JavaScript errors were observed.

- [Browser outcomes](../../docs/testing/results/admin-roles-2026-10-11/admin-roles.json)
- [Desktop directory](../../docs/testing/results/admin-roles-2026-10-11/admin-roles-desktop.png)
- [Mobile role form](../../docs/testing/results/admin-roles-2026-10-11/admin-roles-mobile.png)

## Running installation

The API, worker and web images were rebuilt and the three application containers recreated. Existing Oracle, Ollama and Qdrant containers/volumes were retained. Web and API health checks passed; localhost web returned HTTP 200 and setup remained complete.

A before/after comparison confirmed that the original four accounts' usernames/password hashes and counts of existing datasets, documents, prompts, extractions, reviews, model configurations and assignments were preserved. One new account and one dataset were created through concurrent use of the installation during verification; these were retained too. The private verification digest was removed after checking.

[Production migration verification](../../docs/testing/results/admin-roles-2026-10-11/production-migration.json)

This report covers administrator roles and affected access controls. It does not claim a new full OCR/model inference run or an OCI cluster deployment. The same application images and automatic role migration are used by the existing Kubernetes configuration; cluster execution remains to be validated there.
