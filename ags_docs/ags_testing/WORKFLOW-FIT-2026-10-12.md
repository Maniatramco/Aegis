# Workflow fit verification — 12 October 2026

Implemented the user's request to fit the existing shared stepper into its available space, preserving the blue/white palette and the actual stage-driven animations. Agent progress stays inline; the bottom-right Workspace progress popup is suppressed on Agent only.

## Layout

| Browser check | Rail width / scroll width | Result |
| --- | --- | --- |
| Before: desktop onboarding, eight stages | 665 / 704px | Final stage clipped; horizontal scrollbar |
| After: desktop onboarding, eight stages | 665 / 665px | All stages fit; labels/status rows aligned |
| 662px viewport, eight stages | 560 / 560px | Compact labels; page width remains 662px |
| 375px viewport, eight stages | 301 / 301px | Mini rail with full inspected/active step caption; page width remains 375px |
| Desktop answer details | 643 / 643px inside 665px panel | Compact preview fits beside Agent header |
| 375px saved answer, six stages | 301 / 301px | Mini rail; real saved timings and completion count |

The desktop eight-stage rail height decreased from 130.6px to 111.5px. The eight-stage mobile rail and caption occupy 81.4px. Marker inspection displayed `Index documents — Pending` without changing stage status or creating a dataset.

## Live browser verification

Used the computer-use browser tools against the signed-in local app, in a separate QA tab. The in-app browser was at sign-in, so the existing authenticated Chrome session was used. No original draft was edited or original tab reloaded. Temporary viewport overrides were reset.

Ran an actual question against the retained synthetic `invoice-alpha.txt` in `Agent full onboarding browser QA`. The real server workflow reported workspace reads, request understanding, evidence retrieval, response generation and saving. It returned Northstar Example, QA-101 and 1250 USD with a document citation. Verified:

- Running hover preview is bounded to 665px, with the full rail fitting inside it.
- Active ring remains `workflow-ring`, 1.15s, with navy `rgb(11, 49, 111)`.
- Incoming particles remain `workflow-particle`, 2.15s; completed markers remain `rgb(37, 99, 235)`.
- Completion automatically collapses a hovered/pinned preview. Saved answers reopen their recorded timings; Escape closes the details.
- Zero `Workspace progress` popups during running and completed answers.
- Restored conversation and narrow-screen details remain usable; no browser warning/error logs were captured.

This verifies the workflow UI, not a change to intent routing. A preliminary broad invoice-summary query followed an existing saved-profile search route and returned zero matches; selecting and asking explicitly about the available original produced the grounded answer above. No planner/backend changes were made in this layout task.

## Automated checks

- All 124 frontend Node unit tests passed.
- After the final preview-width adjustment, all 63 affected progress, attachments and onboarding tests passed.
- TypeScript check passed; production Docker/Next build passed compilation and type validation; updated web container is healthy on port 3003.
- Added regression coverage for suppressing all floating Agent progress even with requests, startup loading and unrelated jobs, while retaining progress on other pages.
- Corrected an existing onboarding test's asynchronous hashing wait: it now waits for the actual completion condition, instead of assuming a fixed number of event-loop turns finishes native SHA-256 work.

Screenshots: [before](../../docs/testing/results/workflow-fit-2026-10-12/before.png), [desktop onboarding](../../docs/testing/results/workflow-fit-2026-10-12/desktop.png), [662px](../../docs/testing/results/workflow-fit-2026-10-12/tablet.png), [375px onboarding](../../docs/testing/results/workflow-fit-2026-10-12/mobile.png), [final running preview](../../docs/testing/results/workflow-fit-2026-10-12/running.png), [mobile answer](../../docs/testing/results/workflow-fit-2026-10-12/mobile-live.png).
