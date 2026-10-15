# Aegis

Aegis turns documents into searchable knowledge and structured, reviewable results. It uses a Next.js interface, FastAPI, LangGraph agents and a durable Python worker.

**Final handover branch: `ags_sprint1`.** The source freeze remains tagged `aegis-freeze-2026-10-15`.

Read the architecture handover in [Word](ags_docs/Aegis_Architecture_and_Deployment_Handover.docx) or [PDF](ags_docs/Aegis_Architecture_and_Deployment_Handover.pdf). It includes the recently finalized Mural diagram, end-to-end workflows, verified OCI resources, deployed technology versions and model placement.

Use the dedicated [OCI Kubernetes deployment guide](ags_docs/Aegis_OCI_Kubernetes_Deployment_Guide.docx) for destination setup requirements, cluster access, registry configuration, application release, verification and rollback.

The live inspection on 15 October 2026 at 22:26 IST confirmed OKE hosting the web app, API, worker and CPU reranker; Oracle Autonomous AI Database 26ai storing records, the durable queue and native vectors; and OCI Object Storage holding documents and saved results. The three active datasets use Google Gemini. Laptop Ollama is a retained, stopped alternative.

Application source is under `ags_backend/` and `ags_frontend/`; Oracle scripts under `ags_database/`; release tooling under `ags_deploy/`; separate laptop launchers and Compose profiles under `local/`.

The reusable [release skill](.agents/skills/aegis-release/SKILL.md) remains discoverable by AI tools. It requires a prepared destination and explicit deployment instructions. Preserve the [Unified Chat workflow](AGENTS.md).

Earlier guides and verification reports remain in Git history at documentation commit `a33d5fb`. `ags_docs/` contains the handover in Word/PDF and the dedicated deployment guide. The architecture diagram stays embedded in the handover. Reusable QA inputs live under `ags_scripts/ags_qa/ags_fixtures/`. This documentation push does not deploy or change the running application.
