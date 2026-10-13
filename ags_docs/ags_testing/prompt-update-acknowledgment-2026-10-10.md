# Attached JSON prompt update acknowledgment

## Actual diagnosis

Oracle showed `sample_resume.json` version 2 under `Resume_Mani`, and the latest Assistant request was `can you update this`. Saving had succeeded. A subsequent request was `upload the prmpt`. Both went through model planning instead of a verified prompt-save acknowledgment.

Prompt attachments are validated, reviewed and saved by the composer before the plan request. The composer supplied the saved template ID but not the identity of the prompt submitted with this particular request. Prompt files were correctly excluded from document upload filenames. The previous deterministic guard covered simple upload commands, but not update commands, so the model saw no document attachments and asked for clarification despite the completed prompt save.

## Implemented correction

The composer now supplies `submitted_prompt_id` only for a reviewed prompt attached to the current request. The server verifies it matches the owned selected template and validates dataset scope, then obtains the filename and version from storage. Simple save/update/replace/overwrite/upload commands return an application acknowledgment naming the saved prompt, dataset and version without inference. The observed `prmpt` spelling is recognized in this narrow command guard.

Without a newly submitted prompt, an update request asks for revised JSON rather than claiming a new version was saved. Mixed extraction requests, document updates, questions and negations do not use the prompt-save acknowledgment. Prompt uploads still use JSON/schema validation and explicit review confirmation before saving. Existing versions and dataset filename isolation are preserved.

## Observed verification

- 96 frontend tests passed, including a component test that attaches revised JSON, reviews an existing filename update, sends `can you update this`, verifies saving precedes chat planning, and checks attachment clearing and sent-message display.
- TypeScript validation passed.
- 79 focused backend tests passed across application state, prompt validation and fast extraction commands. New cases cover saved version acknowledgment, no-file guidance, invalid submitted identity and exclusions for other tasks.
- Docker web, API and worker images built successfully. Zero active jobs were present before restart; updated services started successfully.
- An isolated API test-client process inside the rebuilt Docker API container used real Oracle persistence in the existing `Full E2E QA 2026-10-10` dataset. It created a fictional prompt, validated an update, saved version 2 with the same ID, verified the updated schema in Prompt templates, and checked unchanged version 1 bytes.
- Actual API plan and streaming reply completed for `can you update this` in 0.289 seconds, and `upload the prmpt` in 0.250 seconds. Both responses named the QA filename, dataset and version 2. Model planning/generation was forbidden in that test process and was not used. These timings describe this local test harness, not browser or general model latency.
- The user's real `sample_resume.json` remained version 2; testing did not upload it again or alter it.
- Live `/ready` and `http://localhost:3003/` returned HTTP 200. `git diff --check` passed.

Authentication overrides applied only inside the separate verification process; the running server's authentication was unchanged. No new graphical browser test or live Oracle Kubernetes deployment was performed. Reload the browser to use the rebuilt frontend; historical chat responses remain historical. This task did not commit or push the changes.
