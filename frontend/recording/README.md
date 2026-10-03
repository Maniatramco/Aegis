# Issue 7 preview recorder

This isolated branch records real chat attachment/drop, original storage, durable indexing, and citation review before publishing the application changes to main. It runs after the full browser suite against the disposable mock-enabled Compose deployment. The worker is briefly stopped and resumed to show the genuine persisted queue; responses are not intercepted. No real documents, external providers or credentials are recorded.

Run `npx playwright test -c recording/playwright.config.ts` after the existing smoke setup. Raw WebM, representative PNGs and chapter timing/provenance JSON are saved in `frontend/recording-output/` and retained in the `aegis-chat-upload-preview` artifact. Narration/captions can be assembled from the recorded chapter timings without altering the actual UI footage.

Recording-only workflow/configuration files must stay on this branch. The application change ends at the recorded `applicationBaseCommit`; publish that tested application commit separately after delivering the preview.
