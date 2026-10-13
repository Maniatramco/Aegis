# Frontend checks

`npm run test:unit` runs every `*.test.cjs` contract test. `npm run typecheck` and
`npm run build` validate types and the production bundle.

`npm run test:e2e` runs the current workspace, review and password-recovery suites.
They require a disposable mock deployment seeded by `scripts/smoke.py`, Chromium
installed through Playwright, and `AEGIS_SMOKE_PASSWORD` for that test account.
`AEGIS_TEST_BASE_URL` and `AEGIS_TEST_API_URL` select non-default local test ports.
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` can select an existing Chromium installation.

CI uses `compose.yaml` plus `compose.test.yaml` in a clean runner. The test overlay
installs a guarded scripted model fixture into both API and worker; it cannot call
real model providers. Use a separate checkout/configuration and a unique Compose
project when reproducing locally. Never attach this overlay to a real workspace.
API calls, permissions, persistence and processing jobs remain real. Only explicit
consent/error/recovery scenarios intercept named browser requests.

`npm run test:screenshots` runs responsive current-screen checks. Set
`AEGIS_CAPTURE_SCREENSHOTS=true` to retain synthetic screenshots under ignored
`frontend/screenshots/`. Historical browser specs for the retired combined
chat/extraction UI were replaced; their previous versions remain in Git history.
Shared streaming/attachment/selection contracts remain covered by unit tests.
