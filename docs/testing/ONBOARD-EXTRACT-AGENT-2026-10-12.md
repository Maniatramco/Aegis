# Onboard & Extract Agent — 12 October 2026

Implemented and deployed to localhost:3003 with the existing OCI storage/database configuration. LangGraph classifies the current request once and delegates onboarding, upload and extraction to `OnboardExtractAgent`. The agent prepares validated tools directly; it does not make a second model call to choose the operation again. User confirmation, dataset access, registered model validation and explicit external consent still apply.

The confirmed onboarding workflow is worker-owned. The browser reads persisted progress and can leave the page. Failed workflows require an explicit retry. Completion includes reading saved Parquet artifacts, synchronizing knowledge, checking current source digests and verifying expected vector IDs against the active provider. Existing-dataset upload/extraction plans share this publication check; their Retry knowledge update action republishes retained results without another extraction job. The compact shared blue/white stepper and animations are unchanged.

## Real browser verification

Used computer-use browser controls with Mani's existing administrator session, actual registered Nomic Embedding and Qwen3:4b inference models, OCI database `agsora` and bucket `mk-aegis`. No mocked model was used in the browser run.

- Asked to create **Resume Agent Verification**, upload/extract a resume and configure models/prompt. The model copied the requested name correctly and prepared the onboarding form with **one model call**. The visible response workflow took about **17 seconds**.
- Selected the fictional Maya Rao PDF and separately uploaded `resume-extraction-v1.json` through browser file choosers. Confirmed the reviewed choices and consent.
- Navigated to Home during processing, after the document staging receipt. Creation, mapping, prompt saving, upload, indexing, extraction and knowledge publication continued without an open Agent workflow component. API logs contain onboarding creation, file staging and status GETs, with **no browser POST to /advance** for this successful run.
- The persisted workflow completed in **226.780 seconds (3m 47s)** after confirmation. Exactly one original document and one extraction were created; their two jobs completed on their first attempt.
- Returning to Agent restored the completed nine stages and the receipt **Knowledge updated · OCI · 9 verified vectors · JSON and Parquet results saved**. Use dataset selected the newly created dataset.
- Review opened the extracted fields alongside the original PDF. Maya Rao, eight years, Python, employers and education were present. Save was disabled without edits. Back returned to the original Agent workflow.

Dataset `36fe2487-eaa3-5132-a9bd-12fdb48bcc52`; workflow `5eb32a2b-7d8d-531b-a139-5a90d97b19d5`; proposal `34f79a12-eee6-44f1-a9ad-67c236541ae1`. Existing Resume Extraction dataset is preserved.

[Live storage/vector/result proof](results/onboard-extract-agent-2026-10-12/live-proof.json) confirms the unchanged original SHA-256, valid saved JSON schema, OCI object routes for original/prompt/result/Parquet, expected vector count in native Oracle `aegis_knowledge_vectors`, and a successful scoped semantic search returning two saved-extraction matches. That search took 10.920 seconds in this run. Original hash: `cf8b71309548bc4a2a4bd542d47f0a1c0b02fe94cf87d008fb8cbdf6eebb2c85`.

Screenshots: [completed workflow](results/onboard-extract-agent-2026-10-12/completed.png), [separate Review](results/onboard-extract-agent-2026-10-12/review.png).

## Latency and routing checks

[Real-model routing benchmark](results/onboard-extract-agent-2026-10-12/routing-benchmark.json): eight of eight checks passed for named onboarding, extraction, upload/extraction, re-extraction, misspelled filename question, exact document count, read-only application guidance and saved summary. These are narrow routing checks, not a production-wide accuracy percentage.

Warm routing took **1.14–2.04 seconds**, using roughly 1,760 input tokens and an 8,192 runtime context window. The initial cold routing call took **16.89 seconds**. The first benchmark harness expected the raw onboarding grammar source `application`; the adapter intentionally normalizes workflow sources to `action`. Its dataset name and operation were already correct. The harness expectation was corrected and all cases rerun without product/model changes; the first pass is preserved in `routing-first-pass.json`.

This change removes a redundant inference call for the first agent. It does **not** establish a before/after percentage for total extraction latency: there is no identical frozen baseline for this OCI sample run. Extraction was the largest stage at **97.714 seconds**; publication took **17.483 seconds**, and OCI saves, validation and worker scheduling account for the rest. Warm routing times must not be presented as whole-question response times. Other agent tool loops and laptop model residency settings were not redesigned.

## Automated recovery and regression verification

- Backend onboarding: **18 passed**, plus the added named-document scope check **1 passed**.
- Backend context and LangGraph: **47 passed**. Long current requests still retain the complete question and prune optional examples to fit the configured model budget; archived chat text is excluded.
- Backend goals and workspace: **28 passed**.
- Frontend onboarding and attachments: **40 passed**. Confirmation, retained document bytes, hashes, explicit retry, uncertain outcomes and browser GET-only observation are covered.
- Vector outage recovery checks retain completed JSON/Parquet and extraction IDs, withhold completion, require confirmation and create no additional extraction jobs on knowledge retry.
- TypeScript, Python compilation, Docker production builds and `git diff --check` passed.

These checks verify the first agent and its integration. They do not claim the entire application is production ready. Review still correctly displays the absence of verified field evidence when the extraction provider has not supplied it.
