---
name: aegis-release
description: Prepare Aegis source freezes, architecture handovers and releases to an already prepared local or OCI installation. Use for this repository release and support work.
---

# Aegis maintenance and release

Start at the repository root and read `AGENTS.md`; for UI work also read `ags_frontend/AGENTS.md`. Follow the user's requested deployment boundary. A documentation or GitHub push request does not authorize changing the running installation.

For source freezes and application releases, read [the README](../../../README.md), the [architecture handover](../../../ags_docs/Aegis_Architecture_Handover.docx) ([PDF](../../../ags_docs/Aegis_Architecture_Handover.pdf)) and the single [final OCI deployment PDF](../../../ags_docs/Aegis_OCI_Deployment_Guide.pdf). The final PDF covers both AI and JSON + PowerShell routes, including database-only selection. Use [the database README](../../../ags_database/README.md) as a script reference. Superseded guides under `delete/` are historical, not current instructions. Keep architecture Word/PDF synchronized and reuse the embedded approved Mural diagram; do not create additional guide sets.

Local launchers, runtime Compose profiles and alternative Kubernetes manifests live under [ags_local_use](../../../ags_local_use/README.md). Backend/frontend tests, fixtures, manual QA tools, test-only scripts and containers are centralized under [ags_testing](../../../ags_testing/README.md). Use its isolated backend runner and the frontend npm test commands; keep application startup checks with runtime code. OCI release and authentication tools remain under `ags_deploy/`.

## Preserve the application contracts

- Every Unified Chat question enforces scope, runs hybrid retrieval, CPU reranking, model generation and answer/citation validation. Keep complete authorized facts for exact counts; do not invent completed stages or bypass retrieval for help questions.
- Processing keeps its existing confirmation and external-consent boundaries. A question does not authorize a write. Keep the other agents' model contracts intact during chat changes.
- SQL and durable originals/results are authoritative. Keep storage routes, versions, Parquet integrity, model identities and access rechecks. API and worker share persistent state; do not scale the pilot independently without redesigning that contract.
- Operational settings live in `ags_backend/ags_app/ags_config/runtime.toml`. Saved registrations can set smaller model limits. Credentials, encryption keys, wallets and runtime payloads stay outside Git and images.
- Use the shared workflow stepper and Agent identity for UI changes. Load the real shared ActionButton in lightweight unit harnesses and locate icon actions by accessible name.

## Prepare a source freeze

Inspect branch, remote, existing changes and component Docker contexts. Include the intended application files and required assets; exclude private state, environment files, deployment receipts and session-only QA notes. Keep source-declared versions distinct from observed deployed versions.

Run backend regressions and frontend unit tests, type checking and a production build in an isolated environment. Diagnose failures and report unrun integration checks accurately. Update the handover and dedicated deployment guide when relevant, synchronize the handover PDF and reuse its embedded approved Mural diagram. Record actual validation in the handover. Preserve existing immutable tags; apply a new tag only when requested for a new source freeze. Push only the intended branch and tag without force.

## Deploy only when requested

For routine code deployment to existing OCI resources with configuration preserved,
use [aegis-deploy](../aegis-deploy/SKILL.md). It adds read-only before/after checks
around the existing release helper and distinguishes schema verification from a
fresh installation. Keep this release skill for source maintenance and handovers.
Follow its separate permission for read-only OCI discovery and final approval of
the detailed release plan before any image publication, workload update or schema
DDL. Access credentials or a general deployment request do not replace that review.

For a database object release, use the same `ags_deploy/deploy.ps1` entry point with DB_Object Y and the reviewed DB_ReleaseFile. Matching objects are preserved; listed missing objects and explicitly permitted missing app user/schema creation require final plan approval. Backend/frontend flags can both be N. Keep the legacy SQLcl empty-owner installer for support only; do not promote it as an alternative handover workflow or replay it over an initialized schema. Object creation does not transfer application data or prepare OKE state.

`ags_deploy/deploy-aegis-code.ps1` updates existing deployments; it is not a fresh installer. Require a prepared destination kubeconfig/context, registry and pull credentials, state, DB/schema, object storage, secrets and reranker. `ags_deploy/ags_oke/ags_legacy_provisioning.py` combines the historical Mumbai infrastructure and pilot registry helpers. It is not needed for normal code releases; its explicit subcommands retain pilot-specific settings and private-state requirements. Keep `ags_kubeconfig.py` separate because the existing kubeconfig uses it for authentication.

For an authorized code release, use the deployment guide, choose the correct architecture and dependency build flags, finish active jobs and retain previous image digests, then verify readiness and the authorized acceptance checks. A backup reference is optional and must not be required or prompted for by this object/code workflow. No automatic rollback exists. After a partial rollout failure, inspect the saved receipt and actual versions before restoring compatible images. Keep the laptop model relay online when that registration depends on it.
