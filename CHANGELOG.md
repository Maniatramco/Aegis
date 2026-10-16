# Aegis change history

The application version and in-app feature history are maintained in `ags_frontend/app/application-version.json`. The About screen and footer read that same file. Entries describe included code; live deployment is confirmed separately by its deployment receipt.

## v26.1.1.0 - 17 October 2026

- Moved **Add Dataset Knowledge** to a sticky toolbar outside the scrolling Sources list. It stays available when Sources is collapsed.
- Added dataset checkboxes so Dashboard chat can combine multiple datasets, with the included dataset and indexed-source counts shown next to the action.
- Added dataset-card drag and drop into Sources. Adding knowledge preserves existing file selections, excludes inaccessible, inactive, unindexed and stale sources, and prevents duplicate inclusions.
- Added **About** navigation and a footer version link, with version-by-version feature notes.
- Kept the original Aegis Agent, Dataset onboarding, extraction/re-extraction, model mappings and backend APIs unchanged.

Validation: 207 frontend unit tests, 4 browser checks and app/test TypeScript checks passed. Browser scope, drag/drop, scroll and mobile checks used synthetic data. Local preview awaits visual review before tagging/pushing; not deployed live.

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
3. Test the actual changes and record the evidence. Review the local result before publishing.
4. After publication is approved, commit the release, push the approved branch, and create an annotated `vVERSION` tag when a versioned repository release is requested. Record the exact commit and deployment receipt; never move an existing version tag.
