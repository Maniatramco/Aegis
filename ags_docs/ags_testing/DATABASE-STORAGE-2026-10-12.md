# One-screen OCI database and native-vector integration — 2026-10-12

## Result

The existing **Manage workspace → Storage** screen manages file storage, database and knowledge storage, and workspace recovery. No new database route or navigation entry was added. Connections links to Storage instead of offering a competing vector-provider selector.

OCI database `agsora` (`ags_ora_db`), Oracle 26ai in `ap-mumbai-1`, was inspected through the signed-in OCI console. mTLS is required. The user downloaded `Wallet_agsora.zip`, provided `ADMIN` as the database username, and entered the two existing passwords directly into the masked Aegis fields. The connection test succeeded, verified native vector support, and initially reported zero of 13 Aegis tables present.

Through the browser, **Create Aegis tables** created all 13 tables, then **Activate OCI database** copied and verified the current workspace before changing the shared routing configuration. The API and worker both verified that their ORM sessions use the remote OCI engine and their vector backend is `oracle`.

The 12 metadata tables retain the existing schema. `aegis_knowledge_vectors` is the thirteenth table and contains both document and unified-knowledge namespaces. No canonical extracted values were moved into `extract_tbl`; actual complete results remain in the pinned OCI JSON/Parquet files. The PDF, prompt and extraction file references were retained, and the original PDF SHA-256 stayed `cf8b71309548bc4a2a4bd542d47f0a1c0b02fe94cf87d008fb8cbdf6eebb2c85`.

Exactly one dataset (`Resume Extraction`), one fictional PDF, one prompt and one extraction remain. Users, sessions, model registrations, model mappings and their protected local configuration references were preserved. Old dataset/archive content was not migrated to OCI.

## Live checks

- Database connection and native cosine-distance support passed against the actual OCI database.
- All 13 Aegis tables exist in the user-supplied `ADMIN` schema.
- Saved-result semantic search returned Maya Rao and Python; original-document semantic retrieval returned the Blue Harbor Analytics passage.
- The final Aegis Agent original-document question answered from that passage: Senior Data Engineer, July 2021–Present, Python/Apache Airflow pipelines, and FastAPI analytics services. One real original-document citation was attached; the tool trace contains `search_documents`. The successful answer completed in 35 seconds on this laptop.
- The initial original-document test lacked request-level cloud consent. A blocked read was repeated until the tool limit. This was corrected: consent/permission failures now stop before additional model/tool calls and show a specific instruction. The next model attempt also confused the dataset title with a filename; an explicit filename constraint now requires evidence in the current question. Both regressions have tests, and the final same-question browser retest succeeded with consent enabled.
- Through Storage, OCI was switched to Local. The local catalog and Qdrant had the current records/vectors; Review still loaded the pinned OCI original and saved fields. Saved OCI credentials were reused without password re-entry, the OCI test passed, and activation switched both services back to OCI. OCI was left active.
- A separate live native-vector contract test on the laptop Oracle database verified native ranking, owner/dataset filters, authorized point-ID filters, paging, idempotent upserts and deletion in an isolated test namespace. That test namespace was removed afterward.

Native search currently uses filtered exact cosine distance, with primary-key and scope indexes. It does not yet create an approximate HNSW/IVF index. This work verifies the single fictional resume and backend switching, not a broad model-accuracy or large-corpus performance benchmark. The database connection uses the existing `ADMIN` account supplied by the user; no new database account or IAM grants were created.

## Credentials and persistence

Only `tnsnames.ora` and `ewallet.pem` were copied from the wallet to `C:/Users/Laya/.oci/database/wallet`. That directory is mounted read-only at `/run/aegis-db/wallet` in both services. Passwords are encrypted in the shared local application volume with the existing master key; API responses contain only saved-password flags. Wallet/private-key contents, passwords and the master key were not printed, put in repository files, embedded in images, or included in metadata/vector payloads.

Database activation preserves the source catalog, verifies copied rows, and refuses a destination containing unrelated Aegis rows. Nullable user audit references are populated after all users exist to handle self-reference cycles. Superseded target vectors are backed up locally before removal. Re-activating the same OCI connection is idempotent. Files remain independently pinned to their existing storage destination.

## Automated validation

- Database-control/native-vector tests: 12 passed, covering encrypted secrets, identity-bound credential reuse, wallet/TLS checks, local-only deployment enforcement, admin-only APIs, sanitized errors, transactional catalog copying, unrelated-workspace refusal, session routing, active-job blocking, failed-copy handling and stale-target-vector cleanup.
- Database-control and Agent graph regression suite: 44 passed before the last filename-scope regression was added. The consent and filename regressions then both passed in the final focused run.
- Storage/Oracle/knowledge/dataset routing suites: 72 passed and one opt-in Oracle test skipped on the initial combined run; its one new fixture failure was repaired and the focused database suite passed afterward. The failure was a fixture with no source users, not an OCI schema failure.
- Frontend suite: 130 passed; TypeScript and Docker production builds passed. Final focused Storage screen suite: five passed.
- Native Oracle live test and actual OCI metadata/vector/file checks passed. API and worker health checks passed after deployment.

Proof: [OCI database JSON](../../docs/testing/results/database-storage-2026-10-12/oci-database-proof.json), [Local switch JSON](../../docs/testing/results/database-storage-2026-10-12/local-switch-proof.json), [final OCI JSON](../../docs/testing/results/database-storage-2026-10-12/final-proof.json).

![Same Storage screen, OCI database active](../../docs/testing/results/database-storage-2026-10-12/storage-oci-active.png)

![Agent original-document source answer](../../docs/testing/results/database-storage-2026-10-12/agent-original-source.png)

![Review retained the original and fields after switching to Local](../../docs/testing/results/database-storage-2026-10-12/review-after-local-switch.png)

## Active connection footer

Added an authenticated, credential-free active-destination summary and a fixed 36px footer for Files, Database and Knowledge. Browser verification confirmed OCI/mk-aegis, OCI/agsora and OCI/Oracle vectors on Agent, Storage and Review. Selecting Local in the unsaved database form did not change the active OCI indicator; the form was restored to OCI without saving or activating. Review navigation and return passed. Geometry checks verified the chat composer and Review save controls do not overlap the footer. Status refreshes after configuration activation, on focus and each visible minute; unavailable status does not fall back to Local.

Storage backend tests: 12 passed, including active-versus-draft and mixed-destination/credential-disclosure regressions. TypeScript and final production builds passed; API and web are healthy. No database or file destination was changed for this footer verification.

![Active destinations at the bottom of Aegis Agent](../../docs/testing/results/database-storage-2026-10-12/connection-footer.png)

## Agent dataset and model selectors

Mani's persisted OCI role is administrator, and Resume Extraction belongs to the administrator account. The selector issue was investigated separately from document cloud consent: initial dropdowns depended on a full catalog that resolved disabled/retired model profiles and probed document index readiness. A measured full catalog took 11.97s, while the page has a 30s GET timeout; a failed read previously left empty choices without a catalog-specific retry.

A lightweight, access-checked `GET /api/agent-v2/catalog?selectors_only=true` now serves enabled models, dataset mappings and file/template metadata. It reuses resolved mapped models and does not contact Ollama or read document indexes to populate selectors. Normal execution retains live model/index validation. Workspace Refresh also refreshes the Agent catalog. Initial dropdowns say Loading, failures expose Retry datasets and models, and retries restore the catalog and normal session initialization.

The live OCI selector catalog took 3.50s in one direct measurement and returned Resume Extraction, Nomic Embedding, Qwen3 Extraction, Qwen3 Chat and one document. These timings compare individual catalog calls, not overall answer generation or a load benchmark. Browser verification under Mani's session passed after a fresh reload; both selectors were enabled, General chat and Resume Extraction could be selected, and Qwen3 Chat was selected as the mapped Agent Model. Workspace Refresh retained the choices.

Validation: 58 tests passed in the initial combined dataset-access/Agent-workspace/model-routing run; the one new test's fixed-count fixture assertion was corrected and its focused retest passed. The final authenticated dataset-access suite passed all 9 tests, including assigned-user isolation and avoiding retired profiles/index probes. Frontend selector/attachment tests passed all 38, including load-failure retry, prompt saves and model selection. TypeScript, final production builds, API and web health checks passed.

![Dataset and model choices visible in Aegis Agent](../../docs/testing/results/database-storage-2026-10-12/agent-selectors.png)
