# Verification record

Verified in the build workspace and GitHub-hosted CI on 2026-10-02. Mock-provider checks never claim live model answer quality.

All four jobs passed on commit `c9f211b415e183746bc00529aea27042df224802`: [Validate Aegis run](https://github.com/Maniatramco/Aegis/actions/runs/36995570646). Subsequent documentation-only commits may have their own repeat runs.

## Passed

- Backend pytest suite: 155 tests passed. Coverage includes auth/CSRF, ownership and document scope, traversal and archive guards, durable-job leases/cancellation/retry, cleanup fencing, encrypted credential masking, named profile isolation, schema validation, extraction evidence, provider contracts, queue reconciliation, and checksum-verified storage migration.
- Full same-origin integration smoke: Next.js API proxy → FastAPI → separate worker, with SQLite/file search and explicitly gated mock providers. Upload/indexing, scoped citations, original download, template versions, extraction/export, reindex/delete, session logout passed.
- Real Docker Compose deployment with PostgreSQL and Qdrant: startup/readiness, durable queued-worker restart, upload/index, scoped citations, downloads, template versions, extraction/export, reindex/delete and logout passed. The discovered localhost publishing issue was fixed with a dedicated web bridge while database/vector services remain internal.
- Four Chromium browser workflow tests passed: all ten screens and session refresh; knowledge-base creation, upload, ready status, preview and index; schema template and masked connections; mobile navigation and signout.
- Default Docker image built with CPU-only PyTorch and produced real normalized 384-dimensional local embeddings.
- Frontend TypeScript type checking and optimized Next.js production build passed.
- npm dependency audit: zero reported vulnerabilities.
- Python production runtime lock audit: zero reported vulnerabilities.
- Real local Sentence Transformer model loaded from Hugging Face with CPU PyTorch; produced normalized 384-dimensional embeddings. This check uses real local inference, not a mock embedding.
- YAML parsing, shell syntax, repository whitespace checks and targeted secret-pattern scan passed. Source packaging excludes credentials, runtime data, caches and dependencies.
- OCI Object Storage/Queue tests exercise the actual pinned SDK argument/model contracts with transport mocked. OCI Responses/vector store tests exercise verified HTTP/auth contracts and mocked complete workflows, including stream cancellation and source reconciliation.

## Explicitly unverified or unsupported

- Direct interactive inspection in this workspace's cloud browser was blocked for localhost; browser interaction tests instead passed on the GitHub-hosted runner against the real Compose deployment.
- Live OpenAI calls, live OCI tenancy authentication/resources, real OCI ingestion/retrieval and OKE deployment have not been exercised. They require the recipient's own credentials and provisioned resources. SDK/HTTP mocks do not prove live compatibility, quota, region availability or IAM policies.
- Scanned/image-only PDFs require external OCR before upload; built-in OCR is not included.
- Cold storage migration requires genuinely stopped writers; the operator assertion cannot detect a separate deployment sharing the same storage.

## Reproduce

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
(cd backend && pytest -q)
(cd frontend && npm ci && npm run typecheck && npm run build && npm audit)
./scripts/local-smoke.sh
```

The CI workflow adds real container services, default-image CPU inference and Playwright UI tests. See the linked completed run for evidence; local mock tests alone do not substitute for these checks.

## Dataset-first revision (issue #1)

The dataset/model routing update is tracked in [issue #1](https://github.com/Maniatramco/Aegis/issues/1). Its local backend suite passes 172 tests, including capability/mapping enforcement, dataset ownership and source scope, explicit legacy migration, pinned profile versions for queued extraction, embedding-generation reindex checks, external consent, and concurrent model/credential isolation. Transport-mocked OpenAI tests inspect the actual selected model and authorization header; they do not make live API calls.

The isolated HTTP smoke also passes the new dataset-first workflow. The hosted CI workflow runs five browser workflow tests covering dataset onboarding, mapped defaults, no/one/multiple eligible models, actual chat/extraction request IDs and persisted provenance, dataset switching, and mobile layout. A separate browser capture test creates eleven actual-app screenshots using synthetic documents and explicitly identified mock models. See the exact pushed commit's [Actions checks](https://github.com/Maniatramco/Aegis/actions/workflows/ci.yml) and issue review record for the hosted run outcome; test discovery or a local build alone is not a browser-test pass.

Existing live-provider and native-laptop limitations above remain. ARM and native Windows/macOS deployments have not been separately exercised; hosted container verification runs on Linux x86_64.

## Focused blue-and-white interface (issue #3)

Daily navigation focuses on Home, Datasets, Ask Aegis, Extract and Templates; operational screens remain under Manage workspace. Dataset browsing, onboarding and detail are separate surfaces. Document upload is opened explicitly; model mappings and dataset activation live in their own sections. Ask keeps dataset/model selection visible and puts document scope and conversation history behind disclosures. Extract separates creation, history and result review. Connections separates Models, Profiles, Providers, Storage, OCI and Diagnostics while preserving unsaved form values across section changes. The requested transparent blue-and-white A/shield logo appears in navigation, sign-in and the browser icon.

The hosted browser suite exercises the preserved routing/consent/model behavior and the new disclosure boundaries. Screenshot evidence is generated against real Compose services with synthetic documents and clearly marked mock generation, including focused Ask, Extract, dataset detail and Connections sections. Check the exact commit's Actions result and issue #3 review comment for terminal verification; no live OpenAI or OCI credentials are used.

## Responsive browser layouts (issue #4)

The baseline rendered-layout audit found horizontal overflow in Templates at 320px, 768px and 844px landscape, plus Dashboard and Setup at 320px. The responsive revision uses shrinkable grids, wrapping action rows, a tablet/mobile navigation drawer, readable form controls, and keyboard-focusable contained data tables rather than hiding body overflow. The drawer supports focus containment, Escape/backdrop dismissal, focus restoration and breakpoint changes. Dataset and model selection remain explicit.

`frontend/tests/responsive.spec.ts` checks all main screens and Connections sections at 320×740, 390×844, 768×1024, 1024×768, 1440×1000 and 844×390. It adds long synthetic names, dataset settings/mappings/upload, table keyboard scrolling, chat/citations/history, extraction review, drawer keyboard/resize behavior, and enlarged-text checks. Screenshots and a layout-audit JSON are retained with the existing CI screenshot artifact. Geometry assertions fail for unintended page or control overflow; deliberately contained table/code scrolling is allowed.

The 200% zoom case uses the equivalent 720-CSS-pixel layout viewport of a 1440px browser; native browser toolbar zoom is not automated. A separate 200% computed-font-size test exercises text enlargement. Tests run in Linux Chromium on the hosted Compose deployment, not physical iOS/Android devices or Safari. Check the exact commit's Actions result and issue #4 review comment for the terminal outcome. All source content is synthetic and AI output remains explicitly mock-only.

## Chat document attachments (issue #7)

Ask Aegis and Datasets share a single upload controller and panel. The controller uses the existing document-upload API, stored originals, indexing jobs and reindex API. It validates file type, size, emptiness and selection count; submits files individually to avoid hiding partially accepted batches; distinguishes upload uncertainty from an indexing failure; and never automatically resends an original whose response was lost. Pending/failed/cancelled/stale-index documents are kept out of selectable chat scope. Chat model routing, provider approval and drafts are independent of upload state.

`frontend/tests/chat-upload.spec.ts` covers picker and drag/drop interactions, selected-dataset routing, ready/progress states, invalid files, upload and processing retries, ambiguous network outcomes, interrupted and repeated flows, consent boundaries and mobile keyboard/layout behavior. Actual upload screenshots are written to the existing `aegis-ui-screens` artifact using synthetic documents and the disposable mock-enabled deployment. See [issue #7](https://github.com/Maniatramco/Aegis/issues/7) and the exact commit’s Actions checks for final CI results and screenshot review. Local backend tests and the HTTP smoke run remain distinct from hosted Chromium/Compose verification; live providers and physical devices are not claimed as tested.
