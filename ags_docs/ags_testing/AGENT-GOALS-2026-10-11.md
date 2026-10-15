# Agent reliability and durable goals — 11 October 2026

Implemented and deployed locally to `http://localhost:3003`. Testing used only
fictional benchmark profiles and isolated datasets. Existing user documents and
extraction values were not edited.

## Real-model release gate

- Baseline: **6/7 passed**. The model incorrectly classified an explicit
  re-extraction plus comparison as ordinary extraction, which attempted to reuse
  an existing result. This was corrected with semantic operation guidance and
  worked examples; no spelling/keyword routing shortcut was added.
- Final run: **8/8 passed**, including a real two-document independent extraction
  followed by automatic completion of the original comparison request.
- Actual registered model: `qwen3:4b`, registration version 2, LangGraph runtime,
  real Ollama inference and real indexing/extraction workers.
- Known initial extraction values exactly matched the synthetic fixture.
- Final goal retained both extraction references, answered for Alice Example
  and Bob Example, and submitted exactly two new extraction jobs in its dataset.
- Reports retain source selection, executed tool arguments, errors, fixture
  hashes, model identity and measured timings. A failed case returns nonzero.

Evidence: [baseline](../../docs/testing/results/agent-goals-2026-10-11/baseline.json),
[final benchmark](../../docs/testing/results/agent-goals-2026-10-11/after.json).
Individual final questions took 6.35–43.79 seconds; the confirmed two-document
goal took 83.33 seconds after confirmation. These are observations on the local
machine, not a concurrent-user benchmark or production latency guarantee.

The first benchmark development attempt did not hydrate the saved reply before
grading it; it was discarded. An intermediate goal gate counted simultaneous
work from another dataset and therefore failed the job-count assertion despite
correct completion. The final harness counts this invocation's dataset only;
neither issue was resolved by weakening the model/goal assertions.

## Automated regression checks

82 passed:
`test_agent_graph.py`, `test_agent_workspace.py`, `test_agent_multi_extraction.py`,
`test_queue_worker_integration.py`.

64 passed:
`test_agent_goals.py`, `test_agent_metadata.py`, `test_agent_application_state.py`,
`test_agent_stream.py`.

Goal-specific checks cover confirmation gates, exact result reads, no mutation
tools during finalization, incomplete coverage, private plan access, read-only
GET, backoff/attempt limits, pause/cancel, manual resume, and recovery after an
answer committed before its goal completion state. TypeScript, production
Docker builds and `git diff --check` also passed. Goal tests were rerun after
the final queue-timing adjustment: 6 passed.

## Computer-use end-to-end verification

Used the Codex computer-use browser API against the deployed app:

1. Selected the isolated dataset and both TXT documents.
2. Asked to re-extract and compare names, cities, skills and years.
3. Verified a proposal with no processing before confirmation, selected the
   actual saved template and independent mode, and confirmed.
4. Reloaded during accepted processing; the saved plan and jobs were restored.
5. Verified automatic goal completion with both profiles and result references.
6. Injected a **CLI-local synthetic ProviderError** in the final answer for a
   separate recovery fixture, without changing application provider settings.
   It followed actual 10/20-second retry backoff and stopped after three attempts.
7. Used the browser's Resume, Pause and reload controls; the paused state persisted.
8. Restarted API/worker/web while paused, then resumed in the browser. Real model
   generation completed using the original two extraction IDs.
9. Verified **two extraction jobs total and one goal answer**, with no duplicate
   processing. [Recovery evidence](../../docs/testing/results/agent-goals-2026-10-11/recovery.json).
10. Opened a result link, checked Alice's actual city/name/skills/years in Review,
    and used Back to restore the completed comparison.
11. Checked desktop and 390px mobile layout: no page horizontal overflow. Browser
    console had no errors. Temporary viewport overrides were cleared.

The outage was deliberately injected; this does not claim an actual model-server
outage or a full network chaos test. Worker recovery after an expired running
lease is covered by automated tests; the live restart check used a paused goal.

Screenshot evidence is saved in the task's `outputs` directory:
`agent-goal-failure.png`, `agent-goal-paused.png`, `agent-goal-recovered.png`,
`agent-goal-comparison.png`, and `agent-goal-mobile.png`.

## Remaining production work

This implements the first two agreed stages. It does not establish multi-replica
safety, high availability, disaster recovery, production telemetry/SLOs or broad
language/model accuracy. Goal input/result paging and attempts remain bounded;
oversized or missing results stop honestly. Saved fields remain unreviewed until
the user verifies them against original sources. See
[runtime contracts and operator commands](../ags_operations/AGENT-RELIABILITY.md).
