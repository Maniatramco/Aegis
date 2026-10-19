# Aegis change history

The application version and in-app feature history are maintained in `ags_frontend/app/application-version.json`. The About screen and footer read that same file. Entries describe included code; live deployment is confirmed separately by its deployment receipt.

## v26.1.9.0 - 19 October 2026

- Add connected-record exploration with scoped, cancellable expand/collapse requests and preserved existing node positions.
- Add D3 network arrangement, a lineage layout and pinned positions, preserving mouse, touch and keyboard movement.
- Highlight neighbours, filter entity types, toggle relationship labels, zoom at the pointer with the wheel and separate parallel relationships with curved links. Keep the mobile heading compact and interaction controls at 44px.
- Keep exact catalog totals distinct from the bounded visible scene; preserve existing API access checks and read-only processing boundaries.
- Include the ISC notices for the bundled D3 force-layout modules. No Neo4j service, new database or paid cloud feature is required.

Pre-deployment validation: all 236 frontend unit tests, both app/test TypeScript checks and six isolated metadata API tests passed. Sixteen targeted local browser checks covered expansion and collapse, shared neighbours, preserved positions, pinning and manual dragging, network/lineage layouts, highlighting, search, dataset scope, labels/type filters, wheel zoom and 390px/320px controls. The Linux ARM64 production image built and started successfully; the page and all seven script assets returned HTTP 200, the served assets contain v26.1.9.0, and five production-browser checks passed for loading, expansion, pinning, mouse movement and 390px touch movement/controls. Preview tests used loopback synthetic metadata and made no model calls. The fixture log's parseable entries contain only GETs and no chat reply calls; two incomplete log fragments were excluded. Physical mobile/pen hardware, live provider inference and the full application browser suite were not tested. Private local evidence is retained under `ags_runtime/workflow-preview/metadata-explorer-v26.1.9.0/`.

Deployment, 19 October 2026: the explicitly approved frontend-only plan `release-20261019-213637-0446f2` published Sprint1 commit `63f6a4b55c6f17916bd865fc82fa6d32673727ef` to the existing Mumbai application. Committed source fingerprint: `a769496e5d3f9f0679644a893d078e1f25978bbde16ca267d6b4d1835d7abf0b`; immutable web digest: `sha256:5cd4d2250ec8837abb3c9ed79bfac4bd7a0e4f699bb6a2a3c1328f7d270ef0fc`. The exact publication image also passed startup/seven-asset checks and three candidate-browser checks before publication. The web rollout and both deployment readiness checks passed; protected configuration/runtime fingerprints and all unselected images matched. Backend, database objects, models, data, routing and infrastructure were unchanged. No Oracle queries, DDL, provider inference or upload/extraction writes were selected. Live HTTPS and all seven initial scripts returned HTTP 200 and matched the tested candidate byte-for-byte; the served assets and signed-in footer show v26.1.9.0.

Twelve targeted read-only live graph checks passed: the 46-record/102-relationship catalog, eight-document drilldown, expansion with preserved positions, pinning, mouse movement with following links, lineage, filters/labels, 390px touch controls/movement, controlled desktop/mobile arrangement isolation, collapse and connected extraction focus. Chrome restarted during verification; checks resumed in a fresh tab with the existing signed-in session. An initial coordinate comparison spanning other UI actions and a responsive transition differed; controlled responsive-only and touch-movement repeats preserved the separate desktop arrangement. Mobile checks used emulation; physical devices, live provider/write workflows and the full application browser suite remain untested. The exact receipt is retained privately at `ags_deploy/deployment-records/release-20261019-213637-0446f2/source/ags_deploy/deployment-records/release-20261019-213637-0446f2-122f45f8.json`, with the plan/result and live screenshots beside the release record. No automatic rollback was used.

## v26.1.8.0 - 19 October 2026

- Move every Metadata Relationships category or record node independently with a mouse, touch or pen, with edges and labels following its position.
- Preserve background panning and zoom. Fit the arranged nodes into view or restore the current view with an icon-only reset control; keep 44px camera controls on mobile.
- Support arrow-key adjustments, larger Shift steps, individual Home reset and Enter/Space inspection, with accessible instructions and move announcements.
- Keep layouts separate for dataset scope, record/filter view and desktop/mobile while the explorer is open. Preserve arrangements across refresh and graph/list switches.
- Clean up released/cancelled pointers and reset gestures; dragging does not open record details. No API, metadata, model, governance or processing changes.

Validation: all 220 frontend unit tests (including 10 new graph regressions), both app/test TypeScript checks and 20 targeted local browser checks passed. Browser coverage included all six category nodes, individual/connected records, following edges/labels, movement at 140% zoom, independent background panning, fit, keyboard movement and inspection, repeated reset, list/refresh retention, scoped layouts, 390px touch drag/cancellation/tap and 320px controls. The pinned Linux ARM64 production image also built and started successfully; root and all seven script assets returned HTTP 200, v26.1.8.0 was found in the served assets, and four production-build browser spot checks passed for modal loading, mouse drag, reset and touch drag. Preview tests used loopback synthetic metadata; the request log contains only GETs and no chat reply calls. Physical mobile/pen hardware, live OCI data/provider inference and the full application browser suite were not tested. Private evidence is retained under `ags_runtime/workflow-preview/metadata-nodes-v26.1.8.0/`. No OCI deployment was performed; the live frontend remains v26.1.2.2.

## v26.1.2.2 - 19 October 2026

- Refine [#18](https://github.com/Maniatramco/Aegis/issues/18): replace the visible Show/Hide sources and Restore Dashboard/Expand chat labels with compact icons.
- Retain descriptive tooltips, accessible labels and 44px mobile touch targets. Preserve the existing layout behavior and selected knowledge, draft and conversation.

Validation: all 210 frontend unit tests and both app/test TypeScript checks passed. Targeted desktop and 390px mobile browser checks verified icon-only controls with descriptive tooltips, 44px mobile touch targets, preserved draft/conversation and selected knowledge across layout changes, no horizontal overflow, and the composer above the footer. No backend changes, real model inference or OCI rollout were performed; the preview uses synthetic data. The complete browser regression suite was not run for this styling refinement.

Deployment after source validation: on 19 October 2026, frontend v26.1.2.2 from `ags_sprint1` source commit `147adb9f9c7a5a1049061c8045953897a7011760` was published to the existing Mumbai `aegis-oci` installation under approved release `release-20261019-192624-b8d433`. The saved source snapshot fingerprint is `333862501765bb024390c4133a4e7d1741629d0cf6234d465b5db26d4b3afba2`; the immutable web image digest is `sha256:bd9b7f1b713d1f46717a7fbe72f9f9bb811aa63fd454a66ccdde48cdd13c1fac`. The ARM64 production image, local startup and seven script assets passed. Web rollout, both deployments at 1/1 readiness, exact image/configuration preservation, public HTTPS 200 and all seven live script assets passed; v26.1.2.2 was verified in the served application assets. As explicitly approved, this Sprint1 frontend omits the separate governance screens while retaining the existing backend image and saved governance settings. API, worker, sidecar images, infrastructure, model mappings and data were preserved. No Oracle queries or database scripts were selected. Authenticated live Dashboard interaction remains unverified because the browser requires sign-in; no model inference, uploads or extraction writes were run. Exact private plan, result, receipt and smoke-check records are retained under this release's ignored deployment-records directory. The source version tag remains unchanged.

Subsequent end-to-end verification on 19 October 2026: 19 authenticated live Dashboard checks and 15 isolated production-image browser/API checks passed, alongside 53 focused backend regressions. Live checks covered indexed-file filtering, expansion/focus, accessible icon controls, draft and saved-conversation preservation, picker cancellation, combined scope with exclusions, empty selection, history, keyboard use, 390px/320px layouts, About history and the existing metadata explorer. A fresh request audit of the source/layout/picker/history cycle captured no mutations or API errors; a longer earlier capture was truncated and is not claimed complete. The identical ARM64 frontend image was also connected to an isolated real API, SQLite, local vector retrieval and the pinned CPU ONNX reranker, with guarded mock embeddings/answer generation and blocked external networking. That path verified synthetic upload/indexing, unpublished-knowledge failure/retry, exact two-dataset/two-document sends, hybrid retrieval, complete-catalog counts, citation validation/source access, general-answer disclosure, conversation/history/reload restoration and sign-out. No cloud model calls were initiated by these tests; existing saved live messages may be displayed. Corrected dataset-toggle browser-test selectors because successful auto-expansion hides their controls before check/uncheck can re-resolve them. Native HTML5 drag delivery could not be verified by the browser-control tool; its drop-handler unit tests had passed previously. The full application browser suite, fresh live provider inference, live upload/extraction and model accuracy were not evaluated. Private results, attempt notes and screenshots are retained under `ags_runtime/workflow-preview/e2e-v26.1.2.2/`. Application code, deployed image and immutable version tag are unchanged by this test/documentation update.

## v26.1.2.1 - 19 October 2026

- Fix [#18](https://github.com/Maniatramco/Aegis/issues/18): expand Dataset Knowledge Chat after indexed knowledge is included, collapsing the surrounding dataset cards, Sources and guidance.
- Keep the included knowledge summary and Add Dataset Knowledge available, with Show sources and Restore Dashboard controls. Keep the existing chat mounted across layout changes so drafts and conversations survive.
- Focus the composer when chat opens, without generating an overview or sending a question automatically. Preserve existing dataset/document scopes, exclusions, busy guards, authorization and retrieval workflows.
- Fit the conversation into the available desktop/mobile workspace and retain the full Dashboard for empty, inactive or unindexed knowledge choices.

Validation: all 210 frontend unit tests, 25 Dashboard Dataset Knowledge Chat backend regressions and both TypeScript configurations passed. Targeted browser checks with synthetic API responses verified automatic expansion, composer focus, source inspection, picker cancellation, preserved drafts/conversations, and a visible composer without horizontal overflow at 1440px, 390px and 320px widths. No Send occurred before explicit submission; the one synthetic submission retained exactly two datasets and 25 selected documents. The maintained browser regression suite was updated and typechecked, but not run as a complete suite. The optimized Next.js build compiled and generated routes; Windows EPERM while copying a standalone dependency symlink leaves standalone packaging unverified. Full backend testing, real model inference and OCI rollout were not performed.

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
