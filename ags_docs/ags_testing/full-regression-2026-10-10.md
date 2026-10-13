# Aegis end-to-end regression — 2026-10-10

Application: http://localhost:3003 (Docker). Database: local Oracle Free,
AGS_OWNER. Real inference: Qwen3:4b; embeddings: Nomic; search: Qdrant.
Fictional fixtures only, in **Full E2E QA 2026-10-10**
(`d21843dc-e3d8-403f-9234-c93bab97fcc0`). Existing user data was retained.

## Live scenarios

| Scenario | Observed outcome | Verification surface |
| --- | --- | --- |
| Create dataset and map chat/extraction/embedding models | Saved successfully | Browser |
| Invalid prompt JSON | Line 1, column 55 validation error; sending disabled | Browser |
| Valid prompt import | Saved and appeared in Prompt templates under its filename | Browser |
| Same-filename prompt upload | Updated the same template to version 2 | Browser |
| Reload Assistant | Dataset and prompt restored; composer empty | Browser |
| Attach five PDF resumes and send extraction request | All five attachments appeared with the sent question; composer cleared | Browser |
| Multi-file confirmation | Merge/independent choice required before confirmation | Browser |
| Five independent extractions | All five completed; every nested field exactly matched expected fixtures | Browser submission/progress; Oracle/API result comparison |
| Review validation | Invalid schema rejected (400); stale version rejected (409) | API + Oracle |
| Review edit | Version 2 saved; reviewer audit recorded; original PDF unchanged | API + Oracle |
| Export results | JSON, CSV and XLSX succeeded; unsupported format rejected | API |
| Re-extract reviewed result | Confirmation required; version 3 completed; versions 1 and 2 preserved | API + normal worker + real model |
| Three-profile merge/retry | Initial output truncation detected; two saved profiles retained; retry completed all three correctly | API + worker + real model |
| Fresh Assistant upload → physical merge → index → extract → review | One merged document saved; three profiles extracted exactly; review version 2 saved; CSV contains all three names | Assistant API + normal worker + Oracle + real model |
| Merged-file provenance | Three-page PDF downloaded; original source downloads byte-for-byte unchanged; SQL extraction points to merged document | API + Oracle |
| Partial upload/indexing failure | Bad UTF-8 TXT failed; ready PDF retained; explicit Continue ready processed only the valid PDF and completed extraction | Assistant API + worker + real model |
| Knowledge-base question | Meera's Kubernetes experience answered from her resume with a source citation | API + real retrieval/model |
| Whole-dataset knowledge-base search | Meera's Kubernetes experience found with a citation, with no explicit document selection; failed uploads excluded | API + real retrieval/model |
| General chat | Kubernetes explained without document citations | API + real model |
| Chat feedback/export | Feedback saved and conversation export matched saved answer | API |
| Restart persistence | Earlier documents/results retained after API/worker rebuilds | Oracle + API |

Live API checks used a process-local TestClient authentication override scoped to
the existing fictional QA dataset owner. This did **not** change authentication
on the running server. Actual login/session isolation, account recovery and
database transactions were exercised separately by the isolated Oracle
integration suite, with controlled generation providers.

## Timings

Measurements are from this laptop, with other workloads running and substantial
host memory pressure. They are observations, not performance guarantees.
Some inference calls overlapped and therefore include model queue time.

| Measurement | Seconds |
| --- | ---: |
| First independent extraction completed after batch submission | 82.50 |
| Fifth independent extraction completed after batch submission | 339.24 |
| Re-extraction of one reviewed resume | 64.69 |
| Explicit upload/extract planning, fresh probe | 0.149 |
| Explicit planning in failure-recovery case | 0.305 |
| Fresh merged upload through completed extraction | 179.13 |
| Document chat, feedback and export (combined timing) | 85.02 |
| General chat | 31.31 |
| Whole-dataset Kubernetes search | 92.09 |
| Final generation + embedding + readiness smoke | 46.415 |

Ollama reported GPU offload during this run (including Nomic: 100% GPU). The final
smoke observed 2,874,062,929 VRAM bytes and completed generation in 40.847 seconds;
generation, embedding and readiness all passed. The API readiness endpoint
returned HTTP 200 with database and vector store ready after the final rebuild.
CPU compatibility/startup testing from earlier work is recorded in
`assistant-resume-2026-10-10.md`; this run is not a new CPU benchmark.

## Corrected defects

1. API reference omitted three implemented merge/recovery routes; catalog and
   OpenAPI now agree.
2. Password recovery did not consistently record its update audit source/actor.
   Native and browser recovery now record recovery audit fields; legacy SQLite
   schemas remain supported. Updated session fixtures include required audit data.
3. “Please upload and extract these resumes” unnecessarily invoked model
   planning. Narrow explicit extraction commands now use the fast path. An
   explicit upload with no attached files still requires upload, rather than
   extracting unrelated previously selected documents.
4. Single-document EXTRACT_TBL filenames were projected from the prompt name.
   They now use the source document filename; existing projections refresh at
   startup without changing extraction IDs or result contents.
5. Nested local extraction templates allowed up to 64 supporting quotes, risking
   output-budget exhaustion. Compact evidence is bounded to eight short quotes;
   extracted fields and arrays are not restricted. Output truncation now reports
   the actual configured token limit and retry/configuration guidance. Partial
   JSON is never accepted as a complete result. The previously failing merge and
   a fresh three-profile merged workflow both subsequently passed.
6. The Oracle test image omitted scripts imported by the wider regression suite.
   It now includes the password-recovery and storage-migration scripts.

Test-harness assumptions were corrected separately: ready upload IDs live on the
upload call; REVIEW_TBL's dataset relationship is through EXTRACT_TBL; the Docker
PDF parser is pypdf; workflow authorization uses `continue_extraction`. These were
not application defects.

## Automated checks

- Windows backend suite: **549 passed, 4 opt-in skipped**, 570.14 seconds, before
  the final no-attachment guard and evidence/error improvements.
- Final focused fast-command/relational checks: **32 passed**.
- Final focused Ollama/multiple-extraction checks: **40 passed, 1 opt-in skipped**.
- Frontend unit suite: **94 passed**, 3.891 seconds; TypeScript check passed.
- Actual isolated Oracle database suite: **20 passed**, 3.60 seconds.
- Final full Linux container regression: **552 passed, 4 opt-in skipped**,
  658.40 seconds. This includes all final fixes and the three added guard/evidence
  checks. No failures remained in this final suite.

The opt-in skips were downloaded-public-RFC/local-model choices, the standalone
real-Ollama pytest scenario, the live-Oracle pytest scenario and the optional ONNX
reranker. Real Qwen/Nomic workflows and container smoke were tested separately
above; the live Oracle scenario ran in the separate 20-test suite. The optional
reranker is disabled in the running app and was not enabled for this test.

To repeat the Linux backend suite from the prepared project (Docker running):

```powershell
docker compose --env-file .env.oracle -f compose.oracle.yaml -f compose.oracle-client.yaml --profile test run --build --rm --no-deps -e DATABASE_PROVIDER=sqlite oracle-test python -m pytest ags_backend/ags_tests -q --tb=short -rs
```

This uses isolated fixture databases. The separate Oracle integration command is
the same compose/test invocation with `oracle-test` as its final argument, omitting
the SQLite environment override and pytest command; it uses AEGIS_TEST, not
AGS_OWNER. These checks do not download or invoke paid cloud models.

Tests cover dataset/model mappings and category restrictions, prompt schemas,
upload/merge, retrieval/chat streaming, attachment/document selection, review
edits and optimistic concurrency, exports, recovery, queue/worker behavior,
ownership isolation, audit/FK relationships, storage migration and adapter
contracts. Voice logic is covered by frontend unit checks; physical microphone
capture was not tested. External OCI model/storage/queue calls use controlled
adapter tests here, not a live cloud deployment.

## Limits and retained evidence

Browser automation worked for prompt import and independent upload/extraction
submission, but timed out when opening Review during heavy inference. A fresh
browser later exposed the username/password login page in its DOM and had no
authenticated session available. Its subsequent click and screenshot controls
also timed out. Review/re-extraction/exports/merge/failure recovery were
therefore verified through API/worker/database, **not claimed as fresh browser
passes**. Working browser controls and a signed-in session are needed for the
remaining graphical review retest. No new screenshot of that UI is claimed.

No live Oracle Kubernetes deployment was made or verified. The existing CPU/GPU
deployment renders and prerequisites remain documented in `../KUBERNETES.md`.
These local results do not guarantee cluster storage, drivers, resources or
network configuration.

Useful saved extraction IDs:

- Independent Arjun/review/re-extraction: `0f48de64-f9ba-4609-92af-a6c001cf34b3`.
- Recovered three-profile merge: `3c7c1ab3-81a5-4305-bd37-b683ed8004e6`.
- Fresh physical merged upload/review: `4e48ff9a-702f-4b07-8aab-72f68ab75d9d`.
- Partial-indexing recovery extraction: `b3e22133-23c0-442c-82ed-0cbb6c7b59e8`.

The fresh merged filename is
`merged-01-arjun-rao-backend-3-files-359a9f4e.pdf`, document ID
`5ba72732-10d8-4480-a727-f71b209299b2`. Its manifest lists Arjun, Meera and Nikhil
with original filenames and page ranges. Detailed live assertion results are
saved in the adjacent `results/full-e2e-*.json` files.

Changes were rebuilt into the local Docker API/worker. They remain uncommitted and
unpushed; this testing request did not publish code to GitHub.
