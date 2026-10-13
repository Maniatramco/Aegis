# Full onboarding from Aegis Agent — 11 October 2026

Implemented document selection/upload, separately uploaded or entered JSON Schema prompt setup, instructions, independent/merged extraction and direct Review actions within the separate dataset onboarding workflow. It uses the existing upload receipts, index jobs, extraction submission receipts and review page. Configuration-only onboarding remains available.

## Real browser and model verification

Used computer-use browser controls on the deployed Oracle/Qdrant/Ollama stack at localhost:3003. Created the synthetic dataset **Agent full onboarding browser QA**, mapping Nomic Embedding, Qwen3 Chat and Qwen3 Extraction. Both inference roles use the actual registered qwen3:4b model; no mock provider was used in the browser run.

- Selected `invoice-alpha.txt` and `invoice-beta.txt` through the browser file chooser.
- Submitted an invalid schema; the UI displayed `Strict extraction requires additionalProperties:false at $`, retained the selected files and allowed correction. No dataset was created by that rejected attempt.
- Uploaded `invoice-prompt.json` separately through the prompt chooser. Its schema and instructions populated the form; the JSON prompt was never uploaded as a source document.
- Confirmed the complete workflow. Actual stages completed validation, dataset creation, mapping, prompt save, upload, indexing, extraction and review readiness.
- Reloaded while extraction was running. The restored card resumed the same workflow without reattaching files or creating new submissions.
- Both results completed and produced persisted Parquet output. Alpha contains supplier **Northstar Example**, invoice **QA-101**, amount **1250**. Beta contains supplier **Cedar Example**, invoice **QA-102**, amount **875**.
- Opened Alpha using its Review button. The separate page displayed editable fields on the left and the unchanged original TXT source on the right. Save was disabled initially, enabled after changing 1250 to 1251 and disabled after reverting to 1250. No edits were saved.
- Back to Aegis Agent returned to the completed onboarding card with both Review actions.
- Verified 390×844 layout: page scroll width equals viewport width, 390px; onboarding card 337.6px, stepper 316px. Horizontal scrolling stays inside the shared stepper.

Saved workflow: `a5f63fd7-86bd-530d-9819-8e17b727231d`. Dataset: `6f50b7f5-d0ed-5ccc-9b0b-8d36865c38c2`. The server receipt confirms two source documents, one dataset-scoped prompt at version 1 and two completed extraction records. Dataset mapping remains version 2. [Sanitized saved-record report](results/agent-full-onboarding-2026-10-11/live-report.json).

Screenshots are preserved in the task output directory: `agent-full-onboarding-running.png`, `agent-full-onboarding-mobile.png`, `agent-full-onboarding-completed.png`, and `agent-full-onboarding-review.png`.

## Recovery and regression checks

Backend onboarding tests cover capability/admin/ownership checks; deterministic creation/mapping replay; independent and merged processing through the actual worker pipeline with test providers; invalid schema and altered file manifests; interruption after accepted upload/extraction writes; explicit retry of failed/cancelled worker jobs; streamed and nonstreamed graph proposals; canonical full processing receipts and read-only status metadata. A registered-local-model adapter check verifies the filename/status classifier fits an 8192-token context with onboarding reference receipts.

Frontend onboarding, attachments and shared progress tests: **62 passed**. These include duplicate confirmation protection, retained request UUID after unknown initial response, rejection correction, document hashes/prompt binding, staged-file reload recovery and recovery after rejected file transfer. Dataset/model API regression batch: **40 passed** before the final context-specific changes (28 dataset/model tests and the first 12 onboarding tests). Later onboarding additions and context-specific graph checks are recorded separately in the task tool results.

Production Docker builds, TypeScript checks and `git diff --check` passed.

Final combined rerun after the filename/status repair: `test_agent_onboarding.py`, `test_agent_metadata.py` and `test_agent_graph.py` — **57 passed in 285.04s**.

## Issues found during browser QA and repaired

The floating background-progress panel could intercept the Agent Send button. Agent background progress now begins compact, sits above the composer, and its passive panel cannot intercept underlying controls; the disclosure button remains interactive.

Detailed onboarding histories were duplicated into the classifier's reference context, causing an 8192-token local model to reject a basic filename/status question before inference. Routing now receives concise verified receipts, detailed facts remain available through the status tool, and classifier reference context appears once alongside the current question. A redundant rerun example was removed while preserving the rerun instruction and representative extraction/re-extraction examples. No registered model context limit was increased and no budget checks were bypassed.

The first live metadata response then mislabeled document IDs as filenames after selecting the dataset-status tool. That authorized, read-only tool now includes actual original document names (up to 20), an explicit completeness flag and guidance to paginate the document-list tool for larger datasets. Tests cover exact original names, dataset scope and incomplete lists. After deployment, repeating the same question through the browser with Qwen3 Chat returned **invoice-beta.txt and invoice-alpha.txt** and correctly confirmed both extractions finished. The final response took 1m 34s on this local setup. The earlier failed/incorrect responses remain in the conversation audit trail.

Final browser proof is saved in the task output directory as `agent-full-onboarding-final.jpg`. API and web health checks passed after the final deployment.
