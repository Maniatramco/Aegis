# Real-model benchmark and persistent goals

The agent benchmark is an explicit operator check, not application startup and
not the scripted-model pytest suite. It uses the registered dataset model through
the real API, actual indexing/extraction workers, and isolated fictional profiles.
It never upgrades the QA account to administrator. Dataset fixture provisioning
is internal operator setup; ordinary API requests retain their normal grants.

## Run the release check

An encrypted `diagnostics/langgraph-ui-auth.enc` QA fixture and its mapped model
must already exist. Select a supported local model before running; the shipped
benchmark does not consent to sending fixtures to external inference services.
In the API container run:

```
python -m app.agent_benchmark --label baseline
python -m app.agent_benchmark --label after
```

Baseline checks actual extraction values, typo-tolerant filename discovery,
document counts, saved-value reads, short follow-up context, original citations,
and an explicit re-extraction proposal that creates no jobs before confirmation.
The `after` check also confirms independent extraction of both fictional files
and requires the persistent goal to finish with both profiles, both result
references and exactly two new extraction jobs.

Every run creates a separate dataset and retains the fixtures and report.
Reports are JSON under `/data/diagnostics/agent-benchmark/`, with fixture hashes,
model identity/version, source routes, tool arguments, assertion outcomes and
measured durations. Any failed case exits nonzero. A benchmark pass proves these
specific cases on this deployment; it does not establish broad model accuracy,
concurrent-user capacity or a production latency SLO. Repeat on model, prompt,
adapter or routing changes and retain failures alongside successful reports.

## Goal lifecycle

New LangGraph action plans retain the original requested objective, success
criteria and goal status in their existing external plan artifact. Confirmation
still authorizes the actual dataset, document scope, template, extraction mode
and external consent. Merely asking a question, selecting files, reading a plan
or subscribing to events never starts goal finalization.

The existing worker reconciles confirmed plans after jobs finish and periodically
after restart. It checks coverage against the confirmed documents, reads only
their exact extraction IDs, then invokes a read-only LangGraph continuation to
finish the original summary/comparison. The continuation bypasses mutation
routing and receives no action tools. It labels unreviewed results and provides
Review links. Oversized/inaccessible/missing results fail honestly rather than
claiming completion; current result pages and aggregate answer input are bounded.

States: awaiting_confirmation → waiting_jobs → queued → running → completed.
Processing failures use waiting_recovery and existing confirmed workflow retry
controls. Answer provider failures use retry_wait with exponential backoff
(10/20 seconds between attempts), at most three attempts, then failed. Validation
failures stop; revoked access is blocked. No failed answer reruns extraction.

Finalization has a 15-minute persisted lease, refreshed on real progress. Expired
leases can be reclaimed. A goal ID is saved with the completed conversation
answer so death after answer commit does not create another answer on recovery.
Model ID/version is checked on every attempt; a changed registration requires a
new request. Live dataset/model authorization and accepted external consent are
rechecked. This uses the existing single-worker/shared-lock deployment; it does
not claim independent multi-replica support.

`POST /api/agent-v2/plans/{id}/goal` accepts `pause`, `retry`, or `cancel` for the
personal plan. Pause/cancel stops answer continuation, preserving saved results;
it does not undo already accepted processing. Resume queues only the answer.
`GET /api/agent-v2/goals` returns up to ten recent personal goals for restoration
when browser session history is absent. Completed answers are also in exported
conversation history.

The UI uses the existing compact answer workflow pill and shared horizontal
stepper. It shows actual answer operations, completion, failure, and recovery
controls. Saved values remain subject to source review; schema compliance and
successful goal completion do not imply factual verification.
