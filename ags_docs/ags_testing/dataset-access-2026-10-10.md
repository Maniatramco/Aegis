# Administrator-managed dataset access

Implemented and installed in the existing Oracle Docker application at
http://localhost:3003. Sign in with the original administrator and open
**Manage workspace > Users & passwords > Dataset access** on the colleague's row.
Choose datasets and save. Colleagues refresh their screen to see updated lists.

## Permissions and storage

- One administrator: the original account with internal ID `administrator`.
  It manages users/passwords, dataset assignments and dataset/model configuration.
- Ordinary users see only enabled dataset assignments. They can upload, save
  scoped prompts, chat, extract/re-extract and review/edit shared dataset results.
- Users assigned the same dataset share documents, prompts, extraction results
  and jobs. Conversations and Assistant plans stay private to their creator.
- API permissions protect direct IDs, original downloads, previews, exported
  results, historical conversations and job actions. Revocation applies to new
  requests immediately, without deleting stored content. Previously displayed
  or downloaded information cannot be recalled; existing authorized jobs can finish.
- `AGS_OWNER.USER_DATASET_TBL` is the twelfth custom table. Composite user/dataset
  key, enabled state, four foreign keys and six audit fields are verified in Oracle.
  Disabling an assignment preserves its creation audit. Startup backfills existing
  non-admin owners only when introducing the table; restarts never restore revoked access.
- Shared resources use the dataset's storage/index owner. Their creation audit
  records the actual requesting user. Raw files, prompts and results remain outside
  Oracle. Retrieval rechecks durable-resource access before reading/reranking text.

## Executed validation

| Check | Observed result |
| --- | --- |
| Final full backend suite | 613 passed, 4 skipped; 237.51 seconds |
| Frontend unit checks | 100 passed; 3.15 seconds |
| TypeScript and Docker production build | Passed |
| Actual Chromium, API, worker and Oracle AEGIS_TEST | All 8 scenarios passed |
| Password-management browser regression in Oracle | All 7 scenarios passed; account audit checked |
| Existing User1/User2 in installed Oracle Docker | Login, empty unassigned catalog, blocked administrator actions, own password screen and logout passed; no passwords changed |
| Production readiness and web | API readiness 200; web/API/Oracle/Ollama healthy; worker running |
| Oracle metadata | 12 tables; assignment foreign keys and audit columns checked |

The final eight browser scenarios covered: two users/two datasets; empty
unassigned accounts; administrator assignment/reload/mobile layout; dataset
visibility in Assistant, Datasets and Review; real upload/index/extraction and
cited chat; review arrow/open/edit/save; second-user sharing with private chats;
and revocation of old IDs while preserving admin/second-user access. The final
upload/index/extract/chat scenario took 3.36 seconds with **mock inference**.
This validates permission/workflow behavior, not real-model quality or CPU/GPU speed.

Eight focused backend tests additionally cover real cookie/CSRF authentication,
cross-user audit, Assistant upload-to-extraction continuation, native LangGraph
reading assigned results, historical-access revocation, invalid atomic assignments,
legacy-owner migration/restart behavior and retrieval under storage owners.

Earlier regression runs caught older tests assuming user-created datasets,
the model-read interception changing after routing was refactored, and owner-less
retrieval doubles. Those tests now exercise the approved roles and real authorized
resources. A mobile grid overflow was corrected and the final browser run verified
the production image without injected CSS. The final complete suite has no failures.

## Deployment boundaries

API/worker/web images were rebuilt and restarted. Existing persistent volumes,
Oracle owner, Qdrant and optional GPU configuration were retained. Existing user
rows had no updates during deployment; original User1/User2 credentials worked
afterward. Production metadata counts advanced as conversations/plans, an
extraction and a job were created during the running interval, so a frozen whole-
workspace snapshot comparison is not claimed. No User1/User2 assignments to
existing private datasets were created automatically.

The previous public dev-tunnel URL did not resolve during the optional HTTPS
check. Installed-app checks therefore used the real Docker web service on
localhost; shared HTTPS accessibility is not claimed for this run. OCI cluster
deployment was not performed. The same containers/configuration remain in use.

The disposable Oracle test rows and test containers/volume were removed after
verification. Source, DDL, usage guide and results were synchronized into both
the active VS Code project and the finalized checkout. No Git commit or push
was made by this change.

See [dataset access instructions](../ags_guides/DATASET-ACCESS.md) and
[saved test evidence](../../docs/testing/results/dataset-access-2026-10-10/).
