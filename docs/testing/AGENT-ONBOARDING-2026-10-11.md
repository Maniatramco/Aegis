# Dataset onboarding verification

Verified against the running Oracle/Docker application at localhost:3003 with the computer-use browser controls and the real local Qwen3 model.

- Opened Onboard dataset inside Aegis Agent, supplied a synthetic name/description, confirmed the registered role selections, and observed all four saved stages complete.
- Asked “Onboard a new dataset named Agent final onboarding QA with model mapping.” The real semantic route selected `run_workflow` / `onboard_dataset`; LangGraph called the chat agent's `prepare_dataset_onboarding` tool. The proposed form retained the requested name and required explicit confirmation. No dataset was created by the proposal alone.
- Selected Nomic Embedding, Qwen3 Chat and Qwen3 Extraction as three distinct registered roles. Confirmed setup and observed validation, creation, mapping and readiness complete. The original chat proposal became a saved completion receipt with the actual model names.
- Used the created dataset in Aegis Agent. Its dataset selector and Agent Model became Agent final onboarding QA and Qwen3 Chat respectively. Reloading retained both selections and the completed setup card. Browser error log was empty.
- Checked 1280×800 desktop and 390×844 mobile. The mobile page width remained 390px, the setup card was approximately 338px wide, and the four-stage stepper stayed inside the card. Reset temporary viewport overrides afterward.

The final dataset is `a0380582-271d-5fe4-a3bb-a8f7dc5d02a9`, version 2, index generation 1. Storage inspection confirms all three role IDs are distinct, all saved steps are completed and the chat has its persistent completion receipt. Sanitized evidence is in [live-report.json](results/agent-onboarding-2026-10-11/live-report.json). These are synthetic QA datasets; no existing dataset mappings were changed.

Automated validation:

- Six new backend storage/API/graph cases pass, including streamed and non-streamed proposals, administrator/ownership/capability checks, duplicate confirmation and retry after committed creation or mapping. Completion receipt and live setup metadata are asserted.
- Three component cases pass for explicit confirmation/duplicate-click protection, restored failed workflow retry and recovery of an unknown initial response using the original request UUID. Thirty-two existing agent attachment/chat cases also pass.
- Dataset/model and agent metadata regression batch: 45 cases passed. Existing graph/goal regression cases: 40 passed; the initial new-test fixture errors were corrected and the six onboarding cases rerun successfully.
- TypeScript checking, production Docker builds and whitespace validation pass.

Screenshots are saved in the task outputs as `agent-onboarding-completed.png` and `agent-onboarding-mobile.png`. The final natural-language proposal took approximately 1 minute 43 seconds with the existing constrained local-model configuration. The onboarding configuration transitions completed immediately afterward. This workflow checks configuration/capabilities/credentials presence; it does not advertise a live provider reliability test or index documents that have not been uploaded.
