# Real-model accuracy measurement — 12 October 2026

The current Aegis Agent passed **19 of 22 benchmark tasks (86.36%)**. The newly added harder questions passed **9 of 12 (75%)** after reviewing factual answers and tool arguments against canonical fixtures. This score describes this test set, not general model accuracy.

## Before/after comparison

| Matched test set | Before | Current | Change |
| --- | --- | --- | --- |
| Existing ten real-model regression tasks | 10/10, 100% | 10/10, 100% | **0 percentage points** |
| Twelve new extended questions | No baseline | 9/12, 75% | Improvement cannot be calculated |

The earlier report predates unified knowledge. Its question strings and fixture SHA-256 hashes match the current ten-case run. It covers real extraction, typo-tolerant filenames, counts, saved values, short follow-ups, original citations, long archived chats and confirmation-only re-extraction proposals. The historical report used Qwen3:4b through the older LangGraph QA registration; this run used Qwen3 Chat v4, Qwen3:4b, context limit 262144 and output limit 1024. Settings differ, so this is a historical comparison, not a controlled rerun of the old executable. The identical tasks already scored 100%; no numerical accuracy increase was demonstrated.

## Extended test results

| Case | Reviewed result | Evidence |
| --- | --- | --- |
| Semantic discovery of developer recruitment dataset | Pass | Correct dataset description and citation |
| Semantic discovery of supplier billing dataset | Pass | Correct separate invoice dataset and citation |
| Semantic prompt schema discovery | **Fail** | Chose cross-dataset scope for prompt content; authorized tool rejected it despite a selected dataset and existing prompt |
| Semantic saved Python/Cedar City result | Pass | Correct Alice name, skills and city from saved fields |
| List all saved skills | Pass | Python from Alice's saved extraction; no Java invented from Bob's unextracted original |
| Document names plus count | Pass | Both original filenames and exact count 2 |
| Selected-document count | Pass | Exact count 1 in selected scope |
| Bob's saved city when Bob has no extraction | **Fail** | Omitted person predicate and answered with Alice's saved city |
| Current configured chat model context limit | Pass | Correct 262144 value from model configuration |
| Missing invoice-number field for Alice | **Fail** | Treated Alice Example as an exact filename and requested a document filter instead of inspecting saved fields |
| Reviewed saved city edit | Pass | Maple City from revision 2 |
| Unchanged original document city | Pass | Cedar City from original document, with citation |

The automatic checker initially reported 10/12 answers and 11/12 tool families. Manual canonical-evidence review corrected those broad checks: a generic “No file” reply is not a correct missing-field answer, and choosing the right function family with the wrong scope/person predicate is not a correct tool call. Raw output was preserved separately. The reviewed answer, tool-argument and end-to-end scores are each **9/12 (75%)**. The overall 19/22 task success combines the ten regression tasks with these twelve extended tasks.

## Method and scope

- Actual deployed LangGraph, registered Qwen3:4b inference, Nomic embeddings, Qdrant, Oracle and persistent result files; no mocked model and no model-based judge.
- One request per case, with predefined fixture facts and expected sources/tools. Failed cases were not retried to improve the score.
- Current application code, model registrations and global configuration remained unchanged throughout measurement.
- All extended questions used fresh conversations. Core tests also seeded an 80-turn synthetic archive containing deliberately incorrect filenames/counts.
- The dataset and added decoy were isolated fictional QA fixtures. Bob's original exists, but only Alice has a saved extraction. The final two cases explicitly changed the fictional saved city to Maple City while preserving Cedar City in the original and previous revision.
- Questions created no unconfirmed processing jobs. Budget checks passed, and no case reached the tool-step limit. The prompt-scope failure was enforced by the tool's authorization/scope boundary.
- An initial attempt to use the benchmark's model-remapping option was blocked by the QA account's administrator restriction. That setup attempt is not a scored question. The benchmark then used the dataset's existing canonical mapping, without granting privileges.

There is no pre-change result for the twelve new questions, so their score cannot establish an improvement caused by unified knowledge. This small synthetic set is useful for finding concrete regressions; it does not estimate broad accuracy, production load or repeatability.

## Reproducible evidence

- [Current core run](../../docs/testing/results/agent-accuracy-2026-10-12/current-core.json)
- [Historical matched baseline](../../docs/testing/results/agent-context-2026-10-12/real-model-benchmark.json)
- [Extended raw run](../../docs/testing/results/agent-accuracy-2026-10-12/current-extended-raw.json)
- [Extended reviewed scoring](../../docs/testing/results/agent-accuracy-2026-10-12/current-extended-reviewed.json)
- [Calculated comparison](../../docs/testing/results/agent-accuracy-2026-10-12/comparison.json)
- [Extended runner](run_agent_accuracy.py) and [comparison/review script](summarize_agent_accuracy.py)

Current core dataset: `1a63bf15-92a8-4152-bc4f-6b29df798cea`. Its reviewed synthetic extraction is `3fc027a2-351d-4e68-a1b7-fed29d955209`. Decoy invoice dataset: `ca44a02a-7765-431e-a634-5d34811eee2c`. All fixtures and earlier revisions were retained.
