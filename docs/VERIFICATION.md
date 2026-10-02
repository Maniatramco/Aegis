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
