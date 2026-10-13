# Manual verification helpers

Automated tests belong in `ags_backend/ags_tests/` and `ags_frontend/ags_tests/`. These manual
benchmarks and recorded verification helpers previously lived in `ags_docs/ags_testing/`.

| Scripts | Purpose |
| --- | --- |
| `benchmark_*.py`, `run_agent_accuracy.py` | Real-model routing, answer and latency measurements |
| `profile_agent_setup.py`, `verify_agent_latency.py` | Request setup and latency inspection |
| `verify_*.py` | Recorded chat, onboarding, extraction, review and OCI publication checks |
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
in ignored `docs/testing/results/`.
