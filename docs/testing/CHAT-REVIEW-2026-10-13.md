# Fresh chat, citations and final Review — 13 October 2026

Implemented and deployed to the existing OCI-backed localhost:3003 application.

## Behavior

- A new authenticated login resets active chat, selected prompts and unfinished onboarding drafts. The same login retains an explicitly opened conversation during reload/navigation. Saved History and completed jobs are retained. The public login marker is not an authentication credential.
- Citation buttons open an accessible, closable right-side source drawer. Extraction values are loaded from their cited saved revision and filtered to requested fields. The drawer shows original document name, recorded page, extraction name/version, available source text and original page. If a field quote is absent, indexed chunks from the recorded page provide a labelled text window around matching values. Metadata citations are labelled separately. Missing page numbers or exact field evidence are explicitly unavailable, rather than invented.
- Reviewed saves a verified Parquet revision and locks the result. UI edits and backend PATCH, same-result re-extraction, resume and old-job retry paths cannot overwrite a reviewed result. Starting a separate re-extraction remains available from the Review list/Agent.
- Review has cascading Dataset, Prompt template and Extraction name selectors. One prompt is selected at a time. Empty selections do not display unrelated results.
- Review uses available viewport height, independent field/PDF scrolling, collapsed string lists, readable PDF width, Fit page/zoom/page controls and an expanded document view. On narrow phones, Fields and Original document buttons switch panes.

## Validation

- 41 backend tests passed together across review finalization/workflow, dataset access, Extract Data, Re-extract Agent and relational catalog suites.
- 13 frontend utility tests passed; TypeScript and production builds passed.
- Real browser, signed in as Mani: a fresh session-aware load cleared the old active conversation. A new real model question returned B.Tech in Computer Science for the saved resume extraction. Both its extracted-value and metadata citations opened the correct original PDF/page 1 without leaving chat; Close restored chat. The final deployed drawer showed a matching indexed education passage. Open Review and Back to Aegis Agent preserved the same conversation.
- Browser Review: prompt switching selected the corresponding extraction; a temporary edit produced the unsaved indicator and Cancel restored it. Reviewed finalized a separate labelled QA copy, and read-only inputs/disabled Reviewed persisted after reload.
- Live OCI readback verified QA v2 Parquet against returned fields, API mutation rejection, original fixture still v1/unreviewed, original PDF SHA unchanged, and historical citation v1 still readable.
- Responsive browser checks at 662×668 and 390×720. Phone pane switching displayed the original image with no document-wide horizontal/vertical overflow; temporary viewport override was reset.

QA extraction: `06007e9d-b1e2-4bc8-b80a-7427e4ca18ce` (a copy of verified fictional data, not a new model extraction). Original user extraction: `220d33d7-b58c-43eb-a22c-35de309acde8`, preserved unchanged. The live verifier is `verify_final_review.py`.

Login/logout/re-login token rotation was tested using real cookie authentication in isolated backend fixtures, plus frontend reset tests. The user's Mani session was not signed out during browser QA.

Evidence screenshots: `results/chat-review-2026-10-13/fresh-chat.png`, `review-locked.png`, `review-narrow.png`, `citation-panel.png`.
