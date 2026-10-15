# Chat Agent verification — 12 October 2026

The default LangGraph Chat Agent now queries published unified vectors directly. There is one typed agent handoff, one bounded knowledge query and, where necessary, one answer-model call. It has no application mutation tools, canonical business-file hydration, query-time index rebuild or iterative read-tool loop.

Live environment: Qwen3:4b, Nomic Embedding, OCI Oracle native vectors, Mani (`administrator`), fictional dataset Resume Agent Verification (`36fe2487-eaa3-5132-a9bd-12fdb48bcc52`). Existing datasets, uploaded originals and extraction results were preserved.

## Real-model results

All seven live graph questions passed the expected factual and tool-trace checks. Every request had exactly one `query_unified_knowledge` trace, zero document/extraction/prompt business-file reads, and no canonical hydration, Parquet load or knowledge sync. Those functions were instrumented or forbidden during the benchmark.

| Question | Correct | Total graph seconds | Model calls | Query embeddings |
| --- | --- | ---: | ---: | ---: |
| Document count | Yes | 23.227 | 1 | 0 |
| Misspelled filename-list request | Yes | 8.285 | 1 | 0 |
| Saved full name and experience | Yes | 9.476 | 2 | 0 |
| Saved skills | Yes | 11.147 | 2 | 0 |
| Mapped models | Yes | 9.855 | 1 | 0 |
| Original resume email and title | Yes | 8.493 | 2 | 0 |
| Semantic discovery of extracted Python profile | Yes | 24.749 | 2 | 1 |

The first question includes a cold model load. Semantic discovery switches embedding/chat weights on a laptop configured for one resident model. Warm exact questions averaged 9.45 seconds in this run. Metadata catalogs avoid query embeddings and answer-model calls. Warm classification took approximately 0.9–1.3 seconds in the seven-question benchmark.

Eight additional real-model routing checks passed: named onboarding, extraction, upload-and-extract, re-extraction, filenames, count, how-to guidance and saved-result summary. Warm classification in that run took 0.62–2.22 seconds. These routing checks did not confirm or execute new processing jobs.

The final deployed global model-catalog check also passed: with no selected dataset it returned the three registered models, used one model call and did not claim a dataset mapping (9.315 seconds).

This is a small fictional fixture benchmark, not a measured overall production accuracy or controlled before/after improvement percentage. The first implementation pass exposed wrong model-query routing and an invalid semantic scope; the final typed router resolved those cases. Both raw runs are retained.

## Browser end-to-end

Used the computer-use browser controls on localhost:3003 while signed in as Mani.

1. Home → Open chat opened Aegis Agent with the correct dataset selected. The old hidden Document Chat destination was corrected.
2. The original misspelled request returned `maya-rao-sample-resume.pdf` with ready status.
3. Clicking its citation opened `/api/knowledge/published-sources/...`; the preview contained the matching native vector metadata and digest.
4. The following count question returned exactly one document.
5. Model mapping returned Nomic Embedding, Qwen3 Chat and Qwen3 Extraction with their registered configuration.
6. A combined saved-result question returned Maya Rao, eight years and all eight expected skills, with a Review action for extraction `b1c6d15d-c36b-4adc-be3b-57fcab37aafb`.
7. Review displayed the complete saved extraction beside the unchanged original PDF. Save remained disabled without edits.
8. Back to Aegis Agent restored the same conversation. Completed workflow details collapsed by default; manual expansion showed the actual vector query and answer stages. No duplicate floating progress appeared on the Agent page.

The browser workflow badges reported about 6 seconds for filenames, 5 seconds for count and model mapping, and 14 seconds for the combined fields question after deployment. These are reported step durations; they do not include every HTTP setup/persistence delay and should not be treated as click-to-finish wall time.

## Automated checks

- 20 Chat Agent tests passed, including complete 30-file catalogs, exact predicate counts, selected-document scope, deletion/access changes, stale revisions, fragment completeness, forged native payload rejection, vector-only source previews, no query-time canonical hydration, unexpected mutation rejection and global model catalogs.
- The combined Chat Agent/context check passed 32 tests before the additional global-model regression. Context tests include a long archive sentinel absent from both routing and answer inputs, and model-budget enforcement.
- Prior onboarding/goal checks passed after adding recoverable final workflow publication and revision-aware plan saves.
- 40 frontend attachment/onboarding regressions passed. TypeScript and the production API/worker/web build passed. `git diff --check` reported no whitespace errors.

Authorization, revision guards and runtime model configuration still use the control database. Conversation persistence still uses configured storage. Only the answer facts are vector-backed. Source-file access in Review is intentional and separate from Chat request-time answer retrieval.

## Evidence

- [Final real-model benchmark](../../docs/testing/results/chat-agent-2026-10-12/live-benchmark.json)
- [Initial benchmark retained for audit](../../docs/testing/results/chat-agent-2026-10-12/first-pass.json)
- [Real-model routing regression](../../docs/testing/results/chat-agent-2026-10-12/routing-regression.json)
- [Final global model-catalog check](../../docs/testing/results/chat-agent-2026-10-12/global-models.json)
- [Persisted browser answers and native filenames](../../docs/testing/results/chat-agent-2026-10-12/browser-proof.json)
- [Completed browser answer](../../docs/testing/results/chat-agent-2026-10-12/completed.png)
- [Expanded actual workflow](../../docs/testing/results/chat-agent-2026-10-12/workflow.png)
- [Review page](../../docs/testing/results/chat-agent-2026-10-12/review.png)

See [Chat Agent design](https://github.com/Maniatramco/Aegis/blob/aegis-freeze-2026-10-15/ags_docs/CHAT-AGENT.md) for source selection, freshness and context limits.
