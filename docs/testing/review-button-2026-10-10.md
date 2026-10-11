# Extraction Review button correction - 2026-10-10

The directory arrow fetched a saved extraction successfully (HTTP 200) and mounted its Review panel, but did not reveal it. At 1294 x 582, the reproduced panel started at y=734 while the browser remained at scrollY=0. The earlier acceptance checks asserted that fields existed/loaded and interacted with them using browser automation, which automatically scrolled to those fields. They did not assert that clicking the directory button itself brought the review into the viewport. This was a gap in the prior verification.

## Change

Opening an extraction scrolls its entire review panel into view and focuses the review heading. Opening the same extraction again also reveals it. Directory arrows, extraction ID links, Assistant results and Re-extract callbacks use the explicit open counter. Refreshes and saving a new version do not trigger the opening effect. If the user confirms discarding an unsaved draft while reopening the same extraction, the saved draft is restored; rejecting the confirmation retains the draft and selection.

## Observed validation

- Updated production Docker frontend running at http://localhost:3003; Next.js production build and TypeScript checks passed.
- All 100 frontend unit/component tests passed after the final code change.
- 11 real browser checks passed, with no substituted application responses and no page errors.
- Desktop 1294 x 582 and mobile 390 x 844: arrow opens an independent saved result; ID link opens a merged saved result; arrow reopens the same merged result; heading is focused and fully in the viewport; loaded extraction ID matches the selected ID; merged profile selector is available.
- Both sizes: rejecting discard retains unsaved values and does not fetch the other result; accepting discard while reopening the same extraction restores saved values. QA draft changes were cancelled/discarded, never saved.
- Workspace refresh retains saved result availability, and subsequent Review still reveals the chosen result.
- No horizontal overflow in the captured desktop/mobile views. Screenshots visually inspected.

The live tests used the existing isolated fictional QA dataset, including extraction IDs `ea4fd217-6afc-44c9-bf2c-b76e159c78b6` and `a45b40e0-c3aa-4973-a8dd-0ff4c90f694c`. The two extraction IDs in the user's screenshot were separately checked for existence and ready status in Oracle metadata; no customer credentials were used and no customer results were edited. This is a focused review-navigation regression, not a new full-system or OCI deployment test.

## Evidence

See `results/review-button-2026-10-10/` for the raw browser report, before/after viewport screenshots, frontend test output and production build output. The regression runner is `frontend/tests/review-directory-live.js`; it takes private QA login JSON on stdin and uses the real Docker web/API.
