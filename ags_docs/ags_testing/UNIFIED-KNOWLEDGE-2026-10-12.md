# Unified knowledge end-to-end verification

Date: 2026-10-12. Branch: `feat/aegis-assistant-oracle-docker`. Existing uncommitted work was preserved. API, worker and web images were rebuilt and deployed to the local Oracle/Qdrant/Ollama stack serving port 3003.

## Automated checks

- 80 backend tests passed across Agent graph, metadata, context, dataset access and unified knowledge.
- 29 backend tests passed across unified knowledge, persistent goals and onboarding; eight overlap the previous run, giving **101 distinct passing backend tests**.
- After final routing changes, metadata/context tests passed again (32), and unified knowledge tests passed again (8).
- **125 frontend tests passed**, TypeScript passed and the production web build passed.
- `git diff --check` passed, with only existing Windows line-ending warnings.

These tests use scripted model decisions where indicated. They verify real API/storage/tool/graph behavior without representing themselves as real-model accuracy benchmarks. The browser checks below used the deployed Qwen3 model and actual Nomic/Qdrant retrieval.

Unified tests cover canonical source citations, access rejection at search/source-open time, selected document scope, stale versions, forged payload text, deletion, reviewed result revisions, deterministic IDs, repeat synchronization, LangGraph semantic source routing, no mutation jobs for questions and preservation of requested fields after removing an empty substring predicate. Context checks include bounded current-question input and omission of archived chat text.

## Real index

Initial backfill completed with zero failed entities and **542 vector points**: dataset 27, document 87, document chunk 145, extraction 175, prompt 46, model 3, workflow 52 and application 7. These are point counts, not complete entity counts. The collection was `aegis_knowledge_a6324aaa260735555b01`, using actual Nomic 768-dimensional embeddings.

The fictional onboarding test added six points, yielding **548**. Worker restart and repeat synchronization retained them with zero duplicate upserts and zero failed entities. Qdrant inspection confirmed the older extraction revision's points were removed. The canonical revision files remained preserved.

## Computer/browser verification

Used the computer-use browser API in a separate signed-in Chrome QA tab. The in-app tab was at login; the user's original signed-in tab/draft was left untouched.

1. Semantic dataset discovery returned invoice-related canonical dataset metadata and numeric citations. An early answer overclaimed the number of matching datasets; the tool observation now explicitly describes ranked candidates, and final-model instructions reject unsupported candidates/count claims. The final answer identified the relevant fictional supplier-billing dataset without claiming a complete matching catalog.
2. Open source loaded the authenticated current dataset source JSON with its name, description, version and model-role IDs. Generic knowledge citations use the knowledge endpoint, not an undefined document ID.
3. Onboarded **Unified knowledge browser QA 2026-10-12** entirely through Aegis Agent: dataset creation, three model mappings, TXT upload through the file chooser, JSON Schema prompt, indexing, extraction and Review. All eight onboarding steps completed.
4. Real extraction returned `UK-2026-001`, `Blue Harbor Demo Supplies.` and total **1640**. The result was written as Parquet and derived Qdrant points were available.
5. Review initially disabled Save changes. Editing the fictional total to **1650** enabled Save changes; saving published reviewed **version 2**, then disabled the button with “All changes saved.” The unchanged source still showed **1640**. A fresh Agent answer returned **1650** with the saved extraction citation and Review action.
6. The new dataset name now appears correctly in Review. Agent onboarding refreshes the parent workspace catalog.
7. Requested document names plus the exact count. An early routing decision chose count-only; the selector example/instruction and fast-path guard were corrected. The final answer returned **unified-knowledge-invoice.txt** and **1**, using `list_documents`, not semantic candidate counts.
8. Reproduced “list all skills” in Mani_Sample. The loop ended but initially omitted skills from the projection after removing an empty filter. The requested field is now retained; the final real-model answer listed the actual Kubernetes/Docker/Terraform/AWS and Python/Pytest/Playwright skills from three saved result reads, with no tool-step-limit reply. Final browser time was 35 seconds including model loading; this is not a latency guarantee.
9. Actual Nomic/Qdrant queries verified prompt schema, original document total **1640**, public model context **262144**, application Review guidance and saved extraction total **1650**. Exact values were checked against canonical content, not inferred from similarity scores.

Final observed browser answer times: saved invoice 22 seconds, dataset discovery 22 seconds, names/count 27 seconds and skills 35 seconds. Existing model loading and the one-model-at-a-time GPU configuration affect these timings. No full maximum-context inference stress test was part of this feature.

## Synthetic fixture and evidence

- Dataset: `8a1a0283-a056-5b83-a68d-5d5cd0d7cc82`
- Document: `227b64f5-fc30-4698-86f2-d91976d6ec8f`
- Extraction: `eaefbdf5-4641-45f9-8158-187768f770f5`
- Reviewed artifact: `extraction/eaefbdf5-4641-45f9-8158-187768f770f5/results/v2-add5b246b023554c.parquet`
- Fixture: [unified-knowledge-invoice.txt](ags_fixtures/unified-knowledge-invoice.txt)
- Live assertions and trace proof: [live-index-proof.json](../../docs/testing/results/unified-knowledge-2026-10-12/live-index-proof.json)
- Browser answers: [browser-answers.txt](../../docs/testing/results/unified-knowledge-2026-10-12/browser-answers.txt)
- Screenshots: [Review revision 2](../../docs/testing/results/unified-knowledge-2026-10-12/review-v2.png), [saved result answer](../../docs/testing/results/unified-knowledge-2026-10-12/agent-reviewed-result.png), [exact catalog](../../docs/testing/results/unified-knowledge-2026-10-12/agent-catalog.png), [skills regression](../../docs/testing/results/unified-knowledge-2026-10-12/agent-skills.png).

The fixture was intentionally left with its reviewed 1650 edit to demonstrate the distinction from original content; no user originals were edited or deleted. See [implementation and operational limits](../UNIFIED-KNOWLEDGE.md).
