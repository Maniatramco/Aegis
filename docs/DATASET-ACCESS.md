# User and dataset access

Sign in with an administrator account. Open **Manage workspace >
Users & passwords**, find the colleague, and click **Dataset access**. Select
one or more datasets and click **Save dataset access**. Users refresh their
screen or sign in again to update visible lists. Removing all assignments gives
the user an empty dataset list. Existing User1/User2 passwords are unchanged;
assign their datasets explicitly rather than sharing existing private data by default.

Administrator access is determined by the persisted `user_tbl.role`, not by a
username or account ID. Any administrator manages users, assignments, passwords
and dataset/model configuration and sees every dataset. Accounts start as users;
use **Change role** in Users & passwords to promote them. Demotion restores their
saved explicit assignments and signs them out. The last administrator is protected.
See [Users and administrator roles](USER-MANAGEMENT.md).

Assigned users can upload documents, save/update dataset-scoped JSON prompts,
chat with citations, run extraction/re-extraction and review/edit shared results.
Two users assigned the same dataset share its documents, prompts and results.
Their chat history and Assistant plans remain private. Unassigned datasets and
their documents, exports, results and jobs are blocked by the API, including
direct links. Revocation applies to new requests immediately, even with an
existing login session; data already displayed or downloaded cannot be recalled.
Previously authorized work already running may complete for the remaining users.

Oracle `AGS_OWNER.USER_DATASET_TBL` stores assignments and enabled state with
creation/update timestamps, actors and source. Documents, prompts and extraction
payloads continue to live outside the database. Audit columns identify the
acting user even though shared resources use the dataset owner's storage/index.
Existing non-admin owners receive a compatibility assignment once when the table
is introduced. Later restarts do not restore revoked access.

Admin API: `GET /api/users/{user_id}/datasets` and
`PUT /api/users/{user_id}/datasets` with `{"dataset_ids":["dataset-id"]}`.
An empty list revokes all assignments. All IDs are validated before changes;
unknown IDs and duplicates leave existing assignments unchanged. The PUT route
requires the existing cookie-session CSRF token. Administrator access is implicit
and cannot be removed using the mapping endpoint.

The same API/container code is used by Docker and the prepared Kubernetes
deployment. No extra service is needed. OCI cluster deployment has not been run.
