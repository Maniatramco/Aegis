# Aegis functionality verification — 2026-10-10

Runtime: **http://localhost:3003**, real Docker frontend/API/worker, Oracle Free (`AGS_OWNER`), Qdrant, Ollama Qwen3:4b and Nomic embeddings. No application responses were substituted in the live browser checks. Test data belongs to the disposable QA account and contains fictional invoices/resumes. Existing user datasets were retained.

## Changes made during this verification

1. Reselecting the current Assistant dataset preserves its saved prompt selection.
2. Assistant now resolves the displayed mapped model and the model ID sent to the API together. Returning from Review cannot display one model while submitting an empty selection.
3. The semantic classifier distinguishes storing/indexing an attachment from requesting structured extraction. Having an attachment or selected prompt alone does not authorize extraction. The original upload-only request was retested against real Qwen3 and proposed only upload.

The updated web, API and worker images are running locally. These changes do not constitute a GitHub push or an OCI deployment.

## Automated checks

| Check | Result |
| --- | --- |
| Full backend suite | 592 passed, 4 opt-in tests skipped; 310.39 seconds |
| Frontend unit/component checks after fixes | 100 passed; 18.50 seconds |
| Actual Oracle integration, isolated `AEGIS_TEST` schema | 20 passed; 9.64 seconds |
| Focused agent regression after classifier instruction change | 89 passed; 182.98 seconds |
| Production frontend build and TypeScript validation | Passed |

The focused 89 tests overlap the full backend suite; they are not 89 additional distinct tests. Host-suite Oracle and Ollama opt-in skips were supplemented by actual Oracle checks and live application inference. The optional RFC/SmolLM2 fixture and ONNX reranker integration were not run.

## Observed browser coverage

| Area | What was verified |
| --- | --- |
| Every menu screen | All 16 opened on desktop; all 16 passed mobile width checks at 390 × 844; no captured JavaScript page errors |
| Accounts | Actual login/session, logout, empty-input validation, invalid login, recovery entry/back navigation |
| Home / Datasets | Search and navigation, dataset creation, mapping, TXT/DOCX/PDF upload and successful indexing, TXT preview, deactivate/reactivate, inactive extraction blocked with HTTP 409 |
| Model Registration / Mapping | Local chat/extraction/embedding registration and connection tests, search, invalid extra-parameter validation, cancelled edits preserve stored registration, mapping drafts survive refresh and save correctly |
| Prompt templates | Invalid JSON blocked, valid Assistant import saved under filename, repeat filename versions the same ID, update receipt avoids a tool loop, dataset/name search and prior-version dialog |
| Assistant upload/extract | Drag/drop, submitted attachments move into the sent message and leave the composer, confirmation, merge/independent choice, real combined two-invoice extraction retaining both records, extraction IDs and Review navigation |
| Extraction Review | Dataset/ID lookup, individual profile selection, saved edits, review status/version increments, unsaved-navigation guard, cancellation of edits, JSON/CSV/XLSX routes, previous reviewed version retained after re-extraction |
| Re-extract | Separate menu starts independent extraction, obtains correct reference/total, opens the matching Review ID |
| Document Chat | Real retrieval answer, numbered source citation opens evidence, feedback persists, conversation export, history reopened after reload |
| Temporary chat | Parse/upload one file, answer directly, clear file; persistent indexed-document count unchanged |
| Failure handling | Corrupt PDF visibly fails; retry remains available; continue-ready excludes the failed file and completes/reviews the valid invoice; ending a failed request retains the original and truthful failed status |
| Jobs & activity | UI retry accepted; corrupt original fails again and is not labelled ready. Attempt counts reset per retry run |
| Index inspector | Inspect stored chunks and actual Qdrant retrieval matches |
| Connections | Save profile, save version 2, safe configuration export, saved storage/database/vector/queue checks all true; no profile activation or provider migration |
| API Documentation / Setup / Services | Documentation API/catalog, Setup navigation, migration prerequisites and capability information displayed; no live cloud migration |
| Assistant knowledge | General Kubernetes answer, tool-computed numeric filter/count (one invoice total >50), versioned extraction citations, citation opens the correct Review ID, and actual JSON link download matches that extraction ID; passed in 10.34 seconds. |

## Measured times

These are observed browser scenario times, not hardware-independent promises or inference-only benchmarks.

| Scenario | Seconds |
| --- | ---: |
| Dataset TXT/DOCX/PDF upload and readiness checks | 13.28 |
| JSON validation, import/update, template library/version checks | 56.63 |
| Assistant merged two-file planning, confirmation, extraction and Review navigation | 60.58 |
| Review edits, guard, exports, re-extraction and version checks | 11.53 |
| Independent extraction through Re-extract and opening Review | 8.96 |
| Document chat answer, citation, feedback, export and history reopening | 75.82 |
| Temporary direct chat plus clear/no-index check | 3.94 |
| Partial upload failure, failed retry, continue-ready, extraction and Review | 128.56 |
| Corrected upload-only planning | 10.56 |
| Upload-only failure and end-request check, including planning | 14.51 |

The active model was observed using GPU offload during this round. CPU fallback exists in the deployment configuration and has earlier test evidence; this round does not establish CPU timings, equal CPU/GPU speed, or future OCI performance. Model load, context size and switching between generation/embedding models affect latency.

## Remaining limitations

- **Docker/Oracle password reset is unavailable.** The browser recovery route is restricted to the native local desktop/SQLite recovery design. Recovery availability must not be described as a completed Oracle password reset. The live browser displayed the restriction and the configuration request returned HTTP 403. Back to sign in works; no password reset was performed.
- OCI/OKE deployment, OCI storage/queue/vector adapters and external paid model providers need their own credentials and live tenancy/cluster validation. They were not deployed or certified by this local test.
- Scanned-PDF OCR is explicitly unsupported. Corrupt files correctly fail; they are not made usable by retrying unchanged bytes.
- Native microphone/speech device operation and visual rendering inside Chromium's PDF viewer were not verified by this headless run. PDF parsing/indexing worked; earlier evidence separately validates the original PDF response bytes.
- Passing these checks does not guarantee correct model answers for every possible question or unrestricted document size. Context/output limits still produce explicit errors and recovery choices.

## Evidence and reproduction

Detailed results, timings and screenshots are in `results/all-functionality-2026-10-10/`. `verified-checks.json` combines the latest observed result for each scenario. Raw phase reports retain interrupted/test-driver failures: selector/endpoint assumptions, waiting for re-extraction submission, document-scope popover closure, reopening saved history, dataset IDs represented by the legacy `kb_id` list field, login username retention, and per-run retry counters were corrected before retesting. Those driver failures are not silently presented as application defects.

The opt-in runner is `ags_frontend/ags_tests/all-functionality-live.js`; the initial screen inventory is `ags_frontend/ags_tests/all-screens-inspect.js`. Fictional PDF/DOCX fixtures are included at `ags_docs/ags_testing/ags_fixtures/ags_all_functionality/`. Build `ags_deploy/ags_docker/Dockerfile.agent-browser` as `aegis-agent-browser`, mount the runner at `/tests`, fixtures at `/fixtures` and a persistent test-output directory at `/results`, join the Compose edge network, and provide a disposable account's JSON credentials on standard input. Never put passwords in command arguments or committed files. Run phases `setup`, `workflows`, `chat`, `failures`, `operations`, `assistant`, `recovery`; the other phases support resuming a specific check.

QA artifacts were kept for inspection. Failed documents in that QA dataset are deliberate corrupt-file fixtures.
