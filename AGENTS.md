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

## Repository cleanup

Move retired files into the repository-root `delete/` folder, preserving their original relative paths, instead of permanently deleting them. Keep this archive outside application builds and active test discovery. Private state and generated artifacts must remain ignored by Git when moved there.

## Dashboard general-chat exception (17 October 2026)

The user now requires the separate Dashboard Dataset Knowledge Chat to answer greetings, small talk and clearly self-contained general-knowledge questions directly with the selected Chat model, without Unified Knowledge, embedding resolution or reranking. Use model-generated answers, never canned final replies. Keep authorization, model mapping/credentials, history isolation and post-inference access checks. Clearly disclose that no knowledge lookup was used; never invent citations or completed retrieval stages.

Mixed requests, Aegis/application guidance, private/business facts, dataset/document/extraction questions and ambiguous/context-dependent follow-ups retain the full scoped hybrid retrieval, reranking, grounded generation and citation-validation workflow. A greeting prefix must not bypass grounding for the rest of a question. This exception applies only to Dashboard Dataset Knowledge Chat; preserve the original Aegis Agent and processing/onboarding workflows.

## Application version and change history

For each feature/fix release, update `ags_frontend/app/application-version.json`, append the version's included changes to root `CHANGELOG.md`, and update the README's current version. The footer and About screen share that JSON. Preserve prior history; do not invent retroactive version tags or claim a local preview is deployed. After the relevant end-to-end checks pass, Git commits, version tags and pushes to the approved repository/branch are pre-authorized; do not ask for repeated push approval. Review the rendered result when UI changes are involved, report the tests and their limits, and never move an existing version tag. This standing user instruction was confirmed on 17 October 2026 and concerns Git publication.


## Data Governance branch and access (19 October 2026)

Keep Data Governance implementation and publication on `data-governance`. Do not add governance features to `ags_sprint1` without a new explicit user instruction. The initial enabled account is the exact persisted username `mani`; other users and administrators start disabled. Administrators manage per-user module access under Users & passwords > Feature access. Module grants do not confer administrator roles or dataset access. Enforce grants on the backend and preserve approved privacy protections and legal holds when a user's module access is disabled.
