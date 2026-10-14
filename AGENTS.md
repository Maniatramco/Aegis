# Aegis Unified Chat workflow requirement

User instruction recorded on 14 October 2026:

Every Unified Chat Agent question must follow this order:

1. Resolve the question and enforce user access, selected dataset and document scope.
2. Retrieve from unified knowledge using hybrid search (semantic/vector and keyword retrieval).
3. Rerank the retrieved candidates.
4. Generate the model answer from the resulting evidence.
5. Validate the answer and its citations before displaying it.

This applies to every question, including General chat, Aegis capabilities/help, catalogs, document questions and saved-result questions. Application guidance must participate in retrieval; loading its exact catalog alone must not bypass hybrid search and reranking. Do not bypass these stages with canned or deterministic final answers.

Preserve dataset/access filters throughout retrieval and reranking. Exact counts and complete lists must use complete authorized catalog data as supplementary evidence; a ranked subset must never be presented as a complete count or list. Routing/access checks happen before retrieval, while answer validation happens after model generation. Report actual stages and failures; never fabricate successful retrieval or reranking.

Implemented and verified for the production Unified Chat path on 14 October 2026. Keep the other processing agents (Onboarding, Upload, Extract and Re-extract) unchanged when maintaining this chat workflow. Chat-only citation formatting and validation must not alter their shared model contracts. Preserve failure guards when retrieval, reranking or evidence is unavailable; never claim successful stages that did not run.
