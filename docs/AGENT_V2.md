# Aegis agent V2

The **Aegis agent V2** menu opens a separate conversational orchestration screen. The original **Aegis Agent** remains available for grounded questions, temporary chat and extraction review.

Choose a registered Chat model for planning and describe a task in natural language. This model selects functions using a strict JSON tool schema and an orchestration system instruction; routing is not based on keywords. Dataset mappings select the Embedding and Extraction models used by the actual document jobs.

| Tool | Inputs | Result |
| --- | --- | --- |
| `upload` | Attached PDF, DOCX or UTF-8 TXT files; dataset; confirmation; cloud consent when required | Stored document references and real indexing job IDs |
| `extract` | Uploaded references or selected existing documents; dataset; prompt template; confirmation | A new structured extraction and job ID |
| `reextract` | Existing document references; dataset; prompt template; confirmation | A new extraction run, preserving earlier results and reviewed edits |

For “upload and extract,” the agent proposes both tools. Confirm upload, wait for indexing to finish, then confirm extraction. Extraction cannot run before preceding jobs complete. Failed or cancelled jobs stop the chain and expose their reason. Missing or ambiguous names require user selection; documents are never silently selected from another dataset.

Every tool requires confirmation at the API as well as the UI. Repeating an already-submitted call returns its existing result rather than starting another upload or extraction. Uncertain submissions fail closed and require checking the dataset/extraction history before making a new request. Pending plans expire after one hour.

Authenticated server-sent events update the inline workflow from real job status every two seconds. The **Check status** action offers an explicit refresh. A reload restores the last plan for the signed-in user; attachments must be chosen again if upload had not started. The screen suppresses duplicate global workflow popups for jobs it displays.

Voice input uses the browser's `SpeechRecognition` or `webkitSpeechRecognition` when present. It fills the same editable text box; it does not send requests or confirm tools automatically. Spoken responses use `speechSynthesis` and are off by default. Browser speech recognition may transmit audio to its speech service. Unsupported browsers retain text chat; microphone permission, recognition service availability and audio playback depend on the browser/device. No voice-provider account is provisioned by Aegis.

This first version exposes only upload, extraction and re-extraction. Model registration/mapping, credentials and infrastructure settings remain in their existing screens. Cloud policies, ownership, CSRF protection, explicit transmission consent, compatible indexes and token budgets apply through the same domain handlers used by the rest of Aegis.

The planner receives the user request, unfinished-request clarification, selected context, attached filenames and a bounded catalog of entity names. It receives no credentials, document content or tool-result content. Plans and results are stored as owner-scoped `agent_plan` records in the configured workspace storage. Planner output is validated before any tool can run.

## Verification

`backend/tests/test_agent_workspace.py` mocks only planning and executes the existing upload/API/worker path. It covers chaining, real indexing dependencies, confirmation, idempotency, retained reviews, failed jobs, ownership, ambiguous selection, external consent and expiry. Existing routing/provider regression tests cover model behavior. The live QA exercise uses local Qwen3 planning/extraction and Nomic embeddings; cloud adapters and actual microphone audio must be verified separately in their intended environment.
