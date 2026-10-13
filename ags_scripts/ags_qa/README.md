# Manual verification helpers

Automated tests belong in `ags_backend/ags_tests/` and `ags_frontend/ags_tests/`. These manual
benchmarks and recorded verification helpers previously lived in `ags_docs/ags_testing/`.

| Scripts | Purpose |
| --- | --- |
| `benchmark_*.py`, `run_agent_accuracy.py` | Real-model routing, answer and latency measurements |
| `*.js` | Opt-in live browser tools, kept outside the automated frontend test folder |
| `create_resume_fixture.py` | Generate a fictional resume |
| `summarize_agent_accuracy.py` | Summarize locally retained result files |

These are operator tools, not automatic tests. Many capture a particular session
and contain its dataset names, record IDs or `/tmp` paths. Inspect and adapt those
inputs before reuse. Some modify test records, use real models or contact OCI;
run them only against a chosen test workspace with those operations authorized.

Most tools import `ags_app` and require backend dependencies and `ags_backend/` on
`PYTHONPATH`, or execution inside the configured API/worker environment. Do not
execute all scripts as a batch. CI uses isolated fixtures and mock providers.
Fictional fixtures remain in `ags_docs/ags_testing/ags_fixtures/`, and raw evidence remains
in ignored `docs/testing/results/`. Retired session-specific `verify_*.py` probes,
the old setup profiler and browser runners for removed controls are available in
Git history and the local `ags_runtime/ags_archive/ags_cleanup_2026_10_14/` archive.
Current regression checks are the automated backend/frontend suites described
above. Current real-model checks include `python -m ags_app.agent_benchmark` and
`python -m ags_app.ocr_smoke` in an explicitly selected test environment.

The optional browser QA image supplies `NODE_PATH=/app/node_modules`. For native
Node execution from this folder, set `NODE_PATH` to the absolute
`ags_frontend/node_modules` path so retained runners resolve Playwright from the
frontend's installed dependencies. Parsing and dependency resolution do not run
live provider calls or submit workflows.
