# Verification record

Verified in the build workspace on 2026-10-02. Mock-provider checks never claim live model answer quality.

## Passed

- Backend pytest suite: 155 tests passed. Coverage includes auth/CSRF, ownership and document scope, traversal and archive guards, durable-job leases/cancellation/retry, cleanup fencing, encrypted credential masking, named profile isolation, schema validation, extraction evidence, provider contracts, queue reconciliation, and checksum-verified storage migration.
- Full same-origin integration smoke: Next.js API proxy → FastAPI → separate worker, with SQLite/file search and explicitly gated mock providers. Upload/indexing, scoped citations, original download, template versions, extraction/export, reindex/delete, session logout passed.
- Frontend TypeScript type checking and optimized Next.js production build passed.
- npm dependency audit: zero reported vulnerabilities.
- Python production runtime lock audit: zero reported vulnerabilities.
- Real local Sentence Transformer model loaded from Hugging Face with CPU PyTorch; produced normalized 384-dimensional embeddings. This check uses real local inference, not a mock embedding.
- YAML parsing, shell syntax, repository whitespace checks and targeted secret-pattern scan passed. Source packaging excludes credentials, runtime data, caches and dependencies.
- OCI Object Storage/Queue tests exercise the actual pinned SDK argument/model contracts with transport mocked. OCI Responses/vector store tests exercise verified HTTP/auth contracts and mocked complete workflows, including stream cancellation and source reconciliation.

## Not yet run or blocked

- Docker Compose container build/runtime, PostgreSQL/Qdrant service integration and browser interaction tests are configured in GitHub Actions but have not run. This workspace has no Docker daemon, and the cloud browser blocked direct localhost access. A successful source build is not a substitute for these checks.
- Repository publication is blocked by the connected GitHub integration returning HTTP 403: `Resource not accessible by integration` on a repository Contents write. No push or GitHub Actions success is claimed until access is corrected and the exact remote commit is verified.
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

The CI workflow adds real container services and Playwright UI tests. Do not interpret a configured workflow as a passed workflow.
