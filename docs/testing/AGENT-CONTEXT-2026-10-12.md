# Aegis Agent context verification — 2026-10-12

The LangGraph agent now sends the current request and fresh authorized source observations to its models. Archived user/assistant chat text never enters routing, tool selection, or answer generation, even when the model has spare capacity. Chat remains saved and visible in history/export.

Follow-ups can use server-saved citation filenames/IDs, saved-result IDs, successful read-source types and actual workflow metadata. They reread the source through authorized tools. Earlier assistant conclusions and user questions are not supplied to the model. Stored document references are revalidated against ownership, dataset and the current document filter before reuse.

Every adapter budgets the serialized message/tool representation before inference, including Qwen compatibility formatting and tool contracts. The conservative UTF-8 byte estimate reserves the actual output allowance plus 512 tokens for overhead. This is a preflight estimate, not an exact tokenizer count. The active Qwen3 Chat registration remains at 8,192 context tokens and 1,024 final-answer tokens; required Qwen routing/tool decisions reserve their actual 256-token allowance. Whole optional worked-example pairs are removed when needed. Required current questions/evidence are never silently truncated; if they cannot fit, inference is blocked with a smaller-scope explanation.

Source-specific instructions replace the broad workspace snapshot for ordinary answers. General questions receive no dataset snapshot; original-document questions receive retrieved passages; saved-value answers use requested field projections and coverage. Successful result discovery catalogs stay in the full trace but are omitted from final generation once their projected values have been read. Exact repeated successful read pairs are replaced with their latest observation; different pages, mutations, failures and multi-call groups remain intact.

## Automated checks

```
.venv/Scripts/python.exe -m pytest backend/tests/test_agent_context.py backend/tests/test_agent_graph.py backend/tests/test_agent_metadata.py backend/tests/test_agent_onboarding.py -q
```

77 passed in 261.76s. After adding two reference-isolation cases and correcting native Ollama budgeting to use its exact messages/tools representation, the focused context suite passed all 13 tests in 10.44s. The 66 other regression checks are unchanged by that adapter correction.

Checks cover exclusion even with spare capacity; preserving the entire archive; whole-example removal; current-question/evidence overflow rejection before provider invocation; successful read deduplication without orphan calls; different pages and mutations; Qwen streaming/nonstreaming and native OpenAI/Ollama serialization; long current-question budgeting; fresh metadata against 160 stale archived messages; result follow-ups from verified IDs; and rejection of previous references outside the dataset/current filter.

## Real model and worker

```
docker exec aegis-oracle-api-1 python -m app.agent_benchmark --label baseline
```

10/10 passed with actual qwen3:4b generation, indexing, extraction and authorized tool reads. Includes typo filenames, counts, saved values, a summary follow-up, original evidence/citations, and confirmation-only re-extraction proposals. Three fresh read cases passed after injecting 80 synthetic archive turns (895,722 bytes), containing deliberately false claims of 9,999 files and imaginary.txt. No question created unconfirmed jobs.

This fixture used the existing QA model's configured 32,768-token window. The separate browser verification below explicitly used the active 8,192-token Qwen3 Chat model. The benchmark records per-call budgets and must fail if an observed request exceeds its own model registration.

[Real-model report](results/agent-context-2026-10-12/real-model-benchmark.json)

## Computer-use end-to-end verification

Tested the signed-in local application through Chrome using the computer-use skill, with the real Qwen3 Chat model and synthetic Agent full onboarding browser QA dataset. Its current four documents were independently read from metadata; two invoice originals/results were used for factual questions.

| Scenario | Observed answer | UI elapsed |
| --- | --- | --- |
| Simple document count | 4 current documents | 1s |
| Current filename list | Both invoice TXT files and both synthetic PDF files | 3s |
| Original invoice-alpha supplier/total | Northstar Example; 1250 USD; original passage citation | 22s |
| Referential invoice-number follow-up | QA-101; saved-result citation and extraction ID | 8s |
| Filename list after long archive | Same four real filenames; imaginary.txt excluded | 3s |
| Count after long archive | 4; stale 9,999 claim excluded | 1s |
| Targeted saved values after long archive | Northstar Example; 1250; QA-101; unreviewed result and Review link | 1s |

For the long-chat UI test, a separate background tab/new QA conversation was created, then seeded with 80 synthetic old turns (906,263 bytes). Opened **Context budget browser QA** using the actual Chat history UI and submitted fresh questions through the composer. The archive remained saved (160 seeded messages plus live test messages). Existing user conversations were preserved.

Every recorded browser call used context_limit 8192. Highest conservative input + output + overhead estimate: **8,043 / 8,192**; all dispatch checks passed. Final answer generation was much smaller: the initial filename answer reserved 1,024 output tokens with an estimated total of 2,959; original invoice generation totaled 2,279. No window increase was used.

[Simple browser audit](results/agent-context-2026-10-12/browser-simple-8192.json) · [Long-chat browser audit](results/agent-context-2026-10-12/browser-long-8192.json)

![Long-chat browser answer proof](results/agent-context-2026-10-12/browser-long-proof.png)

API/worker images were rebuilt and restarted against existing persistent volumes. No frontend redesign or data deletion was required. Work remains uncommitted as requested scope did not include a new commit.
