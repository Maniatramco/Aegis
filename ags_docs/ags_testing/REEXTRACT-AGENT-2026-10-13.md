# Re-extract Agent verification — 13 October 2026

The optimized Re-extract Agent is deployed. LangGraph makes one typed handoff, the agent proposes the validated extraction API call, and the existing worker independently saves artifacts, verifies vector publication and records completion. A plain processing request uses no additional tool-selection or final-answer model call. Required extraction-model and embedding calls still occur.

## Live browser run

Tested localhost:3003 as Mani using the fictional **Resume Agent Verification** dataset. The test preserved the earlier user conversation and its unconfirmed request, and started a separate verification conversation.

1. Attached `resume-reextract-v2.json`, validated it as a prompt template and saved it through Aegis Agent. It adds `highest_qualification` to a compact five-field schema.
2. Asked to re-extract the existing `maya-rao-sample-resume.pdf`. The agent selected the saved document and new prompt, with one routing call, and waited for confirmation.
3. Confirmed **Re-extract** with the result name **Resume re-extract verification**. Exactly one new extraction job was accepted.
4. Left Aegis Agent for Home while the job was running. The worker completed extraction, publication and the durable completion receipt without Agent-page polling.
5. Returned to Aegis Agent. It showed nine verified vectors, one saved Parquet artifact and a completed goal.
6. Review opened the new result beside the unchanged original PDF. The new qualification was **B.Tech in Computer Science**; Maya Rao, eight years, Senior Data Engineer and all eight expected skills were correct. Save remained disabled because no edits were made.
7. Back restored the same completed conversation. A follow-up asking for the qualification in the named new extraction returned **B.Tech in Computer Science**, with native vector citations and a Review action for only the new extraction ID. This exposed and corrected metadata-name predicates being mistaken for extracted-field predicates; failed test replies remain in the QA conversation for audit. No additional extraction was run for the lookup fix.

Run IDs:

- Plan: `aac6eb68-5caa-4a65-827c-cf7f75784f9e`
- Conversation: `55450c7b-0d5d-46ac-8d12-dc4debdf109c`
- New extraction: `220d33d7-b58c-43eb-a22c-35de309acde8`
- Preserved earlier extraction: `b1c6d15d-c36b-4adc-be3b-57fcab37aafb`

## OCI storage and native vector readback

Read the saved object directly through its pinned OCI backend and checked its HEAD response, byte length, metadata checksum and decoded Parquet result. Validated the decoded result against the saved prompt schema.

| Check | Verified value |
| --- | --- |
| Namespace / bucket | `bmyljaecivrj` / `mk-aegis` |
| Parquet object | `aegis/extraction/220d33d7-b58c-43eb-a22c-35de309acde8/results/v1-221adb10f1d868f0.parquet` |
| Object size | 7,412 bytes |
| SHA-256 | `221adb10f1d868f0177bec00480dacd1024219804e2d8b5e8f5f094690cc8367` |
| Native vector table | `aegis_knowledge_vectors` |
| Logical collection | `aegis_knowledge_a6324aaa260735555b01` |
| New extraction points | Two: metadata and saved field record |
| Embeddings | 768 dimensions, present and nonzero |
| Contents | All new payload digests match canonical publication; qualification appears in the native field payload |
| Chat vector view | Sees the new qualification |
| Original / earlier Parquet | SHA-256 unchanged from the pre-run baseline |
| Completion receipt | Exactly one |

Nine vectors were verified for the required dataset, model mappings, document knowledge, selected prompt and new extraction. The new run has its own immutable Parquet artifact; it does not overwrite the earlier reviewed/result history.

## Routing and latency

The real Qwen3:4b routing benchmark passed four variants: selected-document rerun, named-file rerun, extraction-again wording and a how-to question that must remain read-only. Eight real routing checks for onboarding, extraction, upload, re-extraction and Chat sources also passed. Initial failures choosing ordinary Extract for two rerun variants were corrected and retained in the initial benchmark evidence.

The live run measured 30.576 seconds to propose, 58.518 seconds for its extraction job, 24.408 seconds in publication, and 109.580 seconds from accepted processing to completed goal. These stages include storage/queue overhead and are not additive click-to-finish measurements. Subsequent warm route-only checks took approximately 1–4 seconds. The initial routing benchmark measured an 18.173-second model load.

This is a small fixture test, not an overall accuracy percentage or controlled before/after speed comparison. The revised schema is smaller than the earlier full-resume schema. Model/context loading, source retrieval and OCI I/O can still dominate elapsed time.

## Recovery and regression checks

- 24 tests passed across Re-extract, knowledge publication and durable goals, including confirmation, repeated clicks, Parquet corruption, altered native payloads, expired publication leases, partial independent retry, and reindex-prerequisite publication recovery.
- 35 Chat/context tests passed, followed by three parameterized metadata-scope checks for small-model argument variants.
- 31 earlier processing/onboarding/goal regressions and 21 earlier Chat/independent-retry checks passed during implementation; these overlap the final focused suites.
- 41 frontend attachment/onboarding tests passed, including publication-only retry that never submits extraction again.
- TypeScript, the production API/worker/web build and whitespace validation passed.

Publication failure retains completed Parquet and stops completion. **Retry knowledge update** republishes existing artifacts without creating another extraction job. A retry during an active lease cannot duplicate publication. Independent extraction retry retains successful results and resubmits failed documents only. A failed reindex publication resumes the already confirmed extraction after successful retry.

Worker reconciliation and publication skip archived read-only question plans. Queries still use the control database for authorization and revision guards; answer facts come from published native vectors.

## Evidence

- [Live storage/vector proof](../../docs/testing/results/reextract-agent-2026-10-13/live-proof.json)
- [Pre-run preservation baseline](../../docs/testing/results/reextract-agent-2026-10-13/baseline.json)
- [Re-extract routing benchmark](../../docs/testing/results/reextract-agent-2026-10-13/routing-benchmark.json)
- [Other-agent routing regression](../../docs/testing/results/reextract-agent-2026-10-13/other-agent-routing-regression.json)
- [Initial routing failures retained](../../docs/testing/results/reextract-agent-2026-10-13/first-routing-pass.json)
- [Completed workflow](../../docs/testing/results/reextract-agent-2026-10-13/completed.png)
- [Updated Review result](../../docs/testing/results/reextract-agent-2026-10-13/review.png)
- [Named-result follow-up proof](../../docs/testing/results/reextract-agent-2026-10-13/followup-proof.json)
- [Corrected browser answer](../../docs/testing/results/reextract-agent-2026-10-13/followup.png)

See [Re-extract Agent design](../REEXTRACT-AGENT.md).
