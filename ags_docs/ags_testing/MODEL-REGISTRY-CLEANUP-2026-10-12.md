# Model registry consolidation — 2026-10-12

Active registrations reduced from 14 to 3:

| Registration | Weights | Purpose | Context/input | Output |
| --- | --- | --- | --- | --- |
| Qwen3 Chat | qwen3:4b | Agent routing, tools and answers | 8,192 | 1,024 |
| Qwen3 Extraction | qwen3:4b | Structured field extraction | 8,192 | 2,048 |
| Nomic Embedding | nomic-embed-text:latest | Document vectors/retrieval | 2,048 | Not applicable |

The two Qwen entries are intentional role configurations, with different output budgets. LangGraph is the orchestration framework; its QA registrations are now archived, along with the other QA copies.

11 obsolete QA registrations were archived and disabled with explicit replacement IDs per capability. Their immutable model/connection versions remain available for historical runs. No model records, original files, extracted results or conversations were deleted. Default `/api/models` excludes archived entries; authorized audit reads may use `include_archived=true`. Archived registrations cannot be edited or newly mapped. Old cached model selections resolve to the approved role replacement only if it is enabled and mapped to the currently authorized dataset.

18 dataset mappings were updated through the normal versioned mapping function. Embedding changes incremented the dataset index generation. All 34 affected ready documents were reindexed by the real worker; all 34 completed, and all 34 indexes were checked against their current dataset/model fingerprint. Existing failed/unprocessed documents were not silently retried. A new dry run after completion returned zero registrations/datasets/indexes needing further changes.

The pre-change snapshot and migration job IDs are retained locally at `diagnostics/model-consolidation/1791790973.json`. The opt-in `app.model_registry` maintenance command defaults to dry run, requires canonical role IDs and a persisted administrator, rejects different weights/remote models, and refuses to change mappings while jobs are active.

Identical credential-free local registrations are rejected with an actionable 409 response. Different model roles or meaningful configuration variants remain supported. Legacy dataset settings import reuses equivalent registrations instead of creating another pair for every dataset. Both registration endpoints are covered; imported old-model updates reject archived registrations. Saved remote credentials are never reused through deduplication.

## Verification

```
.venv/Scripts/python.exe -m pytest ags_backend/ags_tests/test_model_registry.py ags_backend/ags_tests/test_model_registration.py ags_backend/ags_tests/test_dataset_models.py -q
docker exec aegis-oracle-api-1 python -m ags_app.agent_benchmark --label baseline
```

84 registration/routing checks passed. The real model + worker benchmark passed 10/10 after consolidation, using the canonical Qwen3 Chat registration with its 8,192-token context. Checks included real indexing/extraction, typo filenames, counts, saved values, a referential summary, original evidence/citations, 80 archived chat turns, budget audits, and confirmation-only re-extraction proposals.

Live registration payloads for all three remaining models were prepared and compared read-only against the registry; each correctly matched its existing registration, confirming duplicate detection without creating a test entry.

[Real model report](../../docs/testing/results/model-registry-2026-10-12/real-model-benchmark.json) · [Duplicate identity verification](../../docs/testing/results/model-registry-2026-10-12/duplicate-verification.json)

The signed-in local Model Registration page was refreshed and inspected through computer use. Its active list contains exactly the three canonical entries:

![Cleaned registration page](../../docs/testing/results/model-registry-2026-10-12/registered-models-proof.png)
