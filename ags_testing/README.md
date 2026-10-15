# Aegis testing

All automated tests, synthetic fixtures, manual QA tools and test-only container
support live here, separate from application source. Application startup and
health checks remain in the runtime because the launchers use them.

```text
ags_testing/
  backend/                  Pytest suites, browser API fixture and test requirements
  frontend/                 Node unit tests, Playwright suites/config and fixtures
  qa/                       Opt-in manual browser tools, benchmarks and fixtures
  scripts/                  Smoke, Oracle integration and hardware test helpers
  deployment/               Offline image-only release guard checks
  docker/                   Oracle integration and browser QA images
  compose.test.yaml          Disposable mock API/worker overlay
  pytest.ini                Backend discovery and application import path
  run_backend_tests.py      Isolated local backend runner
```

## Backend tests

Use Python 3.12 and run from the repository root. If needed, first create the
virtual environment with `py -3.12 -m venv .venv`.

```powershell
.\.venv\Scripts\python.exe -m pip install -r ags_testing\backend\requirements.txt
.\.venv\Scripts\python.exe -B ags_testing\run_backend_tests.py
```

Run one file or one test (paths are relative to `ags_testing`):

```powershell
.\.venv\Scripts\python.exe -B ags_testing\run_backend_tests.py backend/test_api_documentation.py -v
.\.venv\Scripts\python.exe -B ags_testing\run_backend_tests.py backend/test_api_documentation.py::test_documentation_requires_login_and_returns_only_contract -v
```

The runner uses a fresh temporary directory, SQLite and mock providers. It clears
inherited cloud/database/model settings and all `AEGIS_TEST_*` integration flags
in the test child process. Your shell and the live installation are unchanged.
It accepts normal pytest arguments, including `--collect-only`, `-k` and `-x`.
`passed` means success; `failed` needs investigation; `skipped` normally identifies
an opt-in integration. Install local-embedding dependencies separately only when
that integration is needed.

For deliberate integrations, invoke pytest directly with `-c ags_testing/pytest.ini`
and an explicit `ags_testing/backend/...` target, using a separately selected test
database/model service and its required `AEGIS_TEST_*` flags. The Oracle helper
requires the dedicated `AEGIS_TEST` schema. Do not use application credentials.

## Frontend tests

Install with `npm ci` inside `ags_frontend`, then run:

```powershell
npm --prefix ags_frontend run test:unit
npm --prefix ags_frontend run typecheck
npm --prefix ags_frontend run build
npm --prefix ags_frontend run test:e2e -- --list
```

The Node runner resolves dependencies from `ags_frontend/node_modules`; no second
Node dependency installation is needed. The last command lists browser tests
without opening a browser or submitting workflows. Remove `-- --list` only when
the isolated mock deployment is ready. Browser suites require Chromium installed
through Playwright and `AEGIS_SMOKE_PASSWORD` for the disposable test account.
`AEGIS_TEST_BASE_URL` and `AEGIS_TEST_API_URL` select test ports;
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` selects an existing Chromium installation.

## Disposable integration environment

CI uses `ags_local_use/compose.yaml` plus `ags_testing/compose.test.yaml` from
the repository root with `--project-directory .`. The overlay mounts the guarded
`backend/browser_app.py` into API and worker. It cannot call real model providers;
permissions, persistence and jobs still use the application code. Seed only that
isolated deployment with `python ags_testing/scripts/smoke.py` and a disposable
`AEGIS_SMOKE_PASSWORD`. Use a unique Compose project and separate configuration
and volumes when reproducing locally. Never attach this overlay to live state.
`AEGIS_SMOKE_ENV_FILE` selects the smoke configuration (default `.env`); match its
values, project name and Compose file selection to the test environment.

`npm --prefix ags_frontend run test:screenshots` runs responsive browser checks.
Set `AEGIS_CAPTURE_SCREENSHOTS=true` to retain synthetic screenshots under ignored
`ags_runtime/ags_screenshots/`. Browser results/traces are written to
`frontend/test-results/` and the HTML report to `frontend/playwright-report/`,
both under `ags_testing` and ignored by Git.
The Oracle test image is `docker/Dockerfile.oracle-tests`, selected by the local
Oracle Compose profile. The optional browser QA image is `docker/Dockerfile.browser-qa`.

## Manual QA and real models

`qa/benchmark_*.py` and `run_agent_accuracy.py` measure routing, answers and latency.
The `*.js` tools are opt-in browser checks; fixture generators and result summaries
are kept beside them. Fictional inputs live under `qa/ags_fixtures/` and
`frontend/ags_fixtures/`. Some retained tools contain session-specific names, IDs
or paths and can write test records, contact OCI or call real models. Inspect and
adapt them for an explicitly selected test workspace; do not batch-execute them.
Most Python tools need backend dependencies and `ags_backend` on `PYTHONPATH`.
Native QA Node tools need `NODE_PATH` set to the absolute
`ags_frontend/node_modules` path; the optional QA image provides it automatically.
Explicit QA commands `qa/agent_benchmark.py`, `qa/agent_smoke.py`,
`qa/agent_test_setup.py` and `qa/agent_goal_recovery_smoke.py` are also kept here;
run them with `ags_backend` on `PYTHONPATH` only in a deliberately selected test
environment. The launcher's `python -m ags_app.ocr_smoke` check stays with runtime code.
Moving these files does not execute them or deploy anything.

## Deployment helper checks

Run `python -B -m unittest discover -s ags_testing/deployment -v` from the
repository root. These offline checks verify that the code-release guard accepts
the intended image updates and rejects configuration drift, wrong destinations,
unready/partial rollouts and inconsistent receipts. The command-line checks also
exercise connection/publication approvals, existing-schema and fresh-owner
workflows, source/target drift and partial failures using simulated clients.
Component checks cover frontend-only, backend-only, database-only and combined
releases, unchanged unselected images, Y/N flags and legacy JSON booleans. The
Oracle release simulation checks ordered script selection, missing-schema/object
creation, matching-object skips, dependency errors, drift, declined approvals,
partial failures and password-safe records without loading a real Oracle driver.
On Windows the
actual PowerShell release helper runs against in-process Docker/kubectl stubs;
the test verifies selected build, push and image-update calls without contacting
those tools or changing a real deployment.
The schema fixture contains historical logical metadata with synthetic destination,
capability and status values; it is not a new live inspection. These checks make
no OCI, Docker or database connections and require only the Python standard library
plus Git. The PowerShell launcher smoke check runs on Windows when available.
