# Review screen rename — 13 October 2026

Renamed the extraction directory from Extract to Review in the menu, heading, breadcrumb, return links and related help text. Extract Data retains its name. The individual result editor remains separate.

Routes: `#Review` opens the list; `#Review/<id>` opens an individual result; `#Review/create` opens New extraction. Legacy Extract and extraction-review aliases still work and normalize to the corresponding Review route. Cancelling navigation with unsaved edits retains the current result route.

Validation: production builds with TypeScript validation passed; whitespace checks passed. Chrome verified the legacy `#Extract` link opens the Review list, an existing result opens its own editor, Back to Review restores the list, and New extraction opens and returns correctly. Existing Review flow test expectations were updated for the renamed Back button. No saved results or documents were changed.

Screenshot: `results/review-rename-2026-10-13/review.png`.
