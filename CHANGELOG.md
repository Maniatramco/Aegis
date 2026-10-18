# Aegis change history

The application version and in-app feature history are maintained in `ags_frontend/app/application-version.json`. The About screen and footer read that same file. Entries describe included code; live deployment is confirmed separately by its deployment receipt.

## v26.1.5.0 - 19 October 2026

- Initially enable Data Governance only for the exact persisted username `mani`. Other accounts and administrators start disabled.
- Add administrator per-user Feature access controls, enabled/disabled directory badges, password verification and stale-version protection under Users & passwords.
- Enforce grants on all governance APIs, exports, OCI publication, policy publication and scheduled signatories; recheck access before releasing successful responses. Existing sessions refresh Dashboard capability state on focus and every 30 seconds while visible.
- Preserve separate administrator roles, assigned dataset scope, two-person approval, approved masking and legal holds. Hide governance-specific metadata graph attributes from disabled accounts while retaining the original metadata graph.
- Store audited versioned feature decisions through existing SQL catalog records and immutable shared control-volume snapshots, without schema changes. Preserve settings during workspace reset and archive grants during account deletion.
- Keep governance code on `data-governance`; `ags_sprint1` remains at its pre-governance source tree. OCI deployment is separate and remains pending.

Validation: 190 selected backend regression tests passed, with a further 39 access/metadata/governance checks passing after the final metadata fallback adjustment. All 223 frontend unit tests and app/test TypeScript checks passed. Synthetic browser checks verified default mani-only access, disabled-administrator access to feature administration, password-confirmed disable/re-enable, cleared password fields, mani catalog access, and 390px/320px layouts without page overflow or console errors. The local optimized Next.js build completed, with a Windows EPERM warning while copying standalone dependency symlinks; standalone runtime/container verification and OCI rollout were not performed. The complete backend suite and live account changes were not run.

## v26.1.4.0 - 18 October 2026

- Added saved-data quality scans, freshness/review/schema/duplicate checks, configurable field rules and pattern-based sensitivity discovery. Reports contain identifiers/counts and disclose unreadable sources, partial scans and source/policy changes.
- Added versioned operational policy proposals and independent administrator approval for masking, quality rules, schedules and retention, using the existing SQL catalog and immutable file snapshots without DDL.
- Enforced approved ordinary-user masking in structured results, saved history and supported exports; blocked originals, previews, raw Parquet, processing and grounded chat for protected datasets. Added pre-release scope/privacy rechecks while preserving model and retrieval contracts.
- Added immediate legal holds and independent release, including retained datasets. Holds block manual document/dataset deletion, retention and workspace reset.
- Added policy-driven inactivity retirement and optional active-storage purge after a grace period, with active-job, hold, backup, mixed-history and partial-failure guards. Retained governance/audit proof; provider backups, external exports, noncurrent object versions and historical external index destinations require separate lifecycle controls.
- Added approved quality/OCI publication/retention schedules on the existing shared-volume runtime and visible task outcomes. Signatory removal/demotion suspends automation; API downtime delays runs.
- Added content-free access auditing with an fsynced hash-chained shared-volume journal and paginated integrity-verified inspection. This is not external immutable storage.
- Added optional verified native OCI lineage submission and stable saved-event timestamps. Current Mumbai provider creation still fails with DCAT-11051; no native ingestion success is claimed.

Validation: the broad backend run completed with 1,112 passing and five opt-in integration skips. Eight failures were corrected (retirement receipt rechecks and two assertions affected by intentional guidance/audit additions); all 100 tests from the affected governance, lifecycle, temporary-chat, hybrid-chat, Dashboard-chat and access suites passed on rerun, including new coverage. All 214 frontend unit tests and both TypeScript configurations passed. Synthetic browser checks verified independent approval, holds, ordinary-user scope/read-only controls, redacted result review, and 390px/320px layouts without horizontal overflow or console errors. Production images and the exact application release plan are prepared separately. The entire backend suite was not repeated after the fixes; no real business retention policy, destructive live-data test or live inference/upload/extraction acceptance write was configured.

## v26.1.3.0 - 18 October 2026

- Added the access-scoped Data Governance catalog to the Dashboard, with complete selected metadata counts, search, classification filters and dataset pagination.
- Added administrator policy editing for ownership, stewardship, sensitivity, business purpose, descriptive retention and glossary terms, with change reasons, version conflicts and saved history.
- Reused the existing catalog and versioned file storage without schema changes; included governance in recoverable workspace archives.
- Added governance details to dataset nodes in Metadata Relationships and administrator metadata/OpenLineage exports without document text, extracted values, credentials or private conversations.
- Added verified OCI catalog connections and explicit policy/glossary publication using existing server-side OCI authentication. OCI IAM remains separate from Aegis dataset grants.
- Created the Mumbai Aegis-Governance catalog and published one real dataset policy/count snapshot and six Aegis concept definitions. No business classifications or stewards were invented.
- Registered the Aegis-Application-Metadata asset with eight live workflow table definitions and 99 columns, including key descriptions, using metadata-only inspection. No database credentials, harvesting connection, IAM change or DDL were introduced; an operator helper supports reviewed schema snapshots.
- Kept native OCI lineage ingestion disabled after OCI rejected Custom Lineage Provider creation with DCAT-11051. Saved lineage remains available in Aegis and OpenLineage export.

Validation: 96 backend checks across governance, metadata, access, storage, dataset lifecycle, API documentation, OCI adapter and schema-publication suites passed; all 207 frontend unit tests and app/test TypeScript checks passed. Both Linux ARM64 production images built using the maintained dependency pins. The production web image served its page, all ten referenced script/style assets and the API proxy successfully. Browser checks against isolated synthetic data verified policy/glossary saves and history, administrator/read-only roles, selected dataset scope and the 390px mobile layout; no browser console errors were recorded. Live OCI checks verified eight workflow tables, 99 column definitions, zero harvesting connections and repeat glossary publication with current ETags. Application release release-20261018-220739-6526e3 was approved and published on 18 October 2026; API/worker and web rollouts, image/configuration/schema checks and HTTPS verification passed. No live upload, extraction or model-inference acceptance tests were run.

## v26.1.2.0 - 18 October 2026

- Added a Dashboard header action for the on-demand Metadata Relationships explorer.
- Added a read-only, access-scoped lineage API covering datasets, documents, extractions, saved prompt versions, reviews and model mappings.
- Preserved combined-document lineage and distinguished pinned extraction model versions from current dataset mappings.
- Added scoped counts, category drill-down, search, paginated records, graph/list views, zoom, pan and mobile record details.
- Applied Aegis blue and navy branding to the light graph canvas, nodes, relationships, controls and list view.
- Completed the API reference entries for the five existing Dashboard Dataset Knowledge Chat routes, including scope, history and streaming behavior.
- Registered metadata routes before the API documentation catalog is finalized so their descriptions appear in the exported contract.
- Preserved Dashboard chat state and existing onboarding, extraction and review workflows. No graph database, schema change or inference is required.
- Built from saved metadata catalog records and version snapshots, independently of the knowledge vector store. OCI deployment remains separate.

Validation: 60 backend regression and API documentation tests, 207 frontend unit tests and app/test TypeScript checks passed. Local browser checks with isolated synthetic data covered dataset scope and counts, empty selection, record search, graph/list views, zoom, saved extraction navigation to Review, preserved chat drafts/source selection and mobile record details. Both Linux ARM64 images built with maintained pinned dependencies; production web startup and seven script assets returned HTTP 200, and backend provider imports, syntax and pip dependency checks passed.

Deployment: Published on 18 October 2026 from app source commit `1280406c365de7b429ece2c989474110c34321b7`, release `release-20261018-111729-f3a940`, to the existing Mumbai `aegis-oci` namespace. Web, API and worker rollouts completed; exact image, configuration fingerprint, database schema, readiness and HTTPS checks passed. Authenticated live browser checks verified v26.1.2.0, 46 metadata records / 102 relationships across three accessible datasets, extraction pagination and mobile details. No database DDL or infrastructure/configuration changes were performed. Live model inference and upload/extraction write tests were not run. Private receipts remain outside Git.

## v26.1.1.0 - 17 October 2026

- Moved **Add Dataset Knowledge** to a sticky toolbar outside the scrolling Sources list. It stays available when Sources is collapsed.
- Added dataset checkboxes so Dashboard chat can combine multiple datasets, with the included dataset and indexed-source counts shown next to the action.
- Added dataset-card drag and drop into Sources. Adding knowledge preserves existing file selections, excludes inaccessible, inactive, unindexed and stale sources, and prevents duplicate inclusions.
- Added **About** navigation and a footer version link, with version-by-version feature notes.
- Kept the original Aegis Agent, Dataset onboarding, extraction/re-extraction, model mappings and backend APIs unchanged.

Validation: 207 frontend unit tests, 4 browser checks and app/test TypeScript checks passed. Browser scope, drag/drop, scroll and mobile checks used synthetic data. Rendered previews reviewed. The user has authorized version tags and GitHub pushes after relevant checks pass, without repeated approval. Live deployment is tracked separately by its receipt.

## v26.1.0.0 - baseline through 17 October 2026

The base version was introduced on 16 October. Releases through commit `0116318` used this version; historical changes are recorded together rather than assigning versions retroactively.

- Document onboarding, uploads, extraction, review, re-extraction, model registration/mappings and the original Aegis Agent.
- Dashboard with onboarded dataset cards, permitted Unified Knowledge sources, and a separate read-only Dataset Knowledge Chat with scoped history.
- On-demand chat initialization, no automatic summary on page load, and compact knowledge-source counts and citations.
- General greetings and self-contained questions answered by the selected chat model without knowledge lookup; dataset, private, mixed and uncertain questions retain hybrid retrieval, CPU reranking and citation validation.
- Compact Connections footer with Local/GCP hosting metadata. Original inline Dataset onboarding restored; the extra onboarding screen removed.

## Maintaining each release

1. Increment the four-part application version for an approved release: a feature increments the third component; a fix increments the fourth.
2. Add a dated feature entry in `application-version.json` and this file. Keep prior entries intact and update the current README version.
3. Test the actual changes, review the rendered local result for UI changes, and record the evidence and its limits.
4. After the relevant end-to-end checks pass, commit the release, create an annotated `vVERSION` tag when a versioned repository release is requested, and push to the approved branch without asking again. Record the exact commit and any deployment receipt; never move an existing version tag.
