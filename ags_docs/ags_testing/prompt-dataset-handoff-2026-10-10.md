# Assistant prompt destination and acknowledgment regression

## Observed issue

The newly created dataset was `Resume_Mani`, but the two Assistant requests (`upload this` and `can you upload this`) selected the older `Resume Dataset`. Oracle contained `sample_resume.json` version 2 under that older dataset. The workspace and Assistant maintained separate dataset selections; restoring Assistant history could override the workspace choice.

The composer saves a validated prompt before submitting the chat request. The server therefore saw a saved prompt and said "already saved", even when Send had just created it. Filename identity was correctly scoped to owner and dataset; this was not cross-dataset duplicate detection.

## Fix

Persist explicit workspace dataset changes in the Assistant preference. Restore that valid preference ahead of historical conversation scope. Publish Assistant selection back to the workspace only after initial scope restoration. Saved prompt selection remains scoped to the selected dataset. Change the acknowledgment to "is saved in [dataset] and selected" without asserting it predated this upload.

The user's existing validated schema was saved through the template API in `Resume_Mani` as `sample_resume.json` version 1, ID `58642c02-f8d1-4736-bb4d-836a5e376662`. The old dataset's version 2 was preserved. The intended dataset has all three model mappings. An already-open browser must refresh and select `Resume_Mani` once to replace its old session preference; subsequent workspace dataset changes are carried into Assistant.

## Validation

- 95 frontend tests passed, including a new dataset-preference isolation regression.
- 37 focused backend tests passed, including truthful saved-state acknowledgments and same-filename isolation between datasets.
- TypeScript validation and Docker web/API/worker builds passed.
- Before restarting, Oracle reported zero queued/running jobs.
- Updated Docker API, worker, and web started. Live API `/ready` returned HTTP 200 with database and vector store available; `http://localhost:3003/` returned HTTP 200.
- A process-local test client against the rebuilt API and real Oracle data verified both Assistant catalog and Prompt templates listing contain the new dataset's prompt. Running application context/reply code returned the saved acknowledgment naming `Resume_Mani`, with no "already". Authentication overrides applied only to that isolated verification process; running server authentication was unchanged.
- Read-only Oracle verification confirmed destination version 1 and preserved old version 2.
- `git diff --check` passed.

No new graphical browser test or live Oracle Kubernetes deployment was performed for this narrow regression. Changes are local and have not been committed or pushed by this task.
