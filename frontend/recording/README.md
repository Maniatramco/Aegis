# Actual-app walkthrough recording

This opt-in harness records an actual Chromium session against a fresh Aegis
Compose deployment. It does not change the application or intercept its API.
Only a visual cursor is added for readability. All documents are fictional and
both generation and embeddings must use explicitly gated development mock mode.

The dedicated `Record Aegis walkthrough` GitHub Actions workflow runs this harness
and retains the raw WebM, chapter timing JSON and representative screenshots.
Authentication is seeded before the browser recording; tokens, passwords,
storageState and traces are not saved as artifacts. Never point this at an
existing or production workspace.

Run after preparing a fresh mock-only deployment:

```sh
cd frontend
AEGIS_SMOKE_PASSWORD='<disposable-test-password>' npx playwright test -c recording/playwright.config.ts
```

`recording-output/recording.json` records the exact commit, application base
commit, viewport, chapter times, runtime errors and mock-data limitations.
The raw recording can be converted to an H.264 MP4 with a separate caption band
without obscuring or substituting the app UI. This is a silent walkthrough.

The recording demonstrates interface and integration behavior only. Mock answers
repeat evidence and mock extraction returns placeholders; neither is evidence
of real model quality, live API connectivity or a provisioned OCI deployment.
