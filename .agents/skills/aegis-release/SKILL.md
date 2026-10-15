---
name: aegis-release
description: Prepare Aegis source freezes, architecture handovers and releases to an already prepared local or OCI installation. Use for this repository release and support work.
---

# Aegis maintenance and release

Start at the repository root and read `AGENTS.md`; for UI work also read `ags_frontend/AGENTS.md`. Follow the user's requested deployment boundary. A documentation or GitHub push request does not authorize changing the running installation.

Read [the README](../../../README.md), [architecture](../../../ags_docs/ags_architecture/ARCHITECTURE.md), [deployment](../../../ags_docs/ags_deployment/DEPLOYMENT.md) and [freeze evidence](../../../ags_docs/ags_deployment/RELEASE-FREEZE.md) for the task at hand. Resolve these links from this skill directory, three levels below the repository root.

## Preserve the application contracts

- Every Unified Chat question enforces scope, runs hybrid retrieval, CPU reranking, model generation and answer/citation validation. Keep complete authorized facts for exact counts; do not invent completed stages or bypass retrieval for help questions.
- Processing keeps its existing confirmation and external-consent boundaries. A question does not authorize a write. Keep the other agents' model contracts intact during chat changes.
- SQL and durable originals/results are authoritative. Keep storage routes, versions, Parquet integrity, model identities and access rechecks. API and worker share persistent state; do not scale the pilot independently without redesigning that contract.
- Operational settings live in `ags_backend/ags_app/ags_config/runtime.toml`. Saved registrations can set smaller model limits. Credentials, encryption keys, wallets and runtime payloads stay outside Git and images.
- Use the shared workflow stepper and Agent identity for UI changes. Load the real shared ActionButton in lightweight unit harnesses and locate icon actions by accessible name.

## Prepare a source freeze

Inspect branch, remote, existing changes and component Docker contexts. Include the intended application files and required assets; exclude private state, environment files, deployment receipts and session-only QA notes. Keep source-declared versions distinct from observed deployed versions.

Run backend regressions and frontend unit tests, type checking and a production build in an isolated environment. Diagnose failures and report unrun integration checks accurately. Refresh the source manifest, architecture PNG and handover when relevant. Record actual results in `ags_docs/ags_deployment/RELEASE-FREEZE.md` before committing and applying a new immutable tag. Push only the intended branch and tag without force.

## Deploy only when requested

`ags_deploy/deploy-aegis-code.ps1` updates existing deployments; it is not a fresh installer. Require a prepared destination kubeconfig/context, registry and pull credentials, state, DB/schema, object storage, secrets and reranker. Historical `ags_oke` helpers contain pilot-specific assumptions and require private runtime records; inspect before reuse.

For an authorized code release, use the deployment guide, choose the correct architecture and dependency build flags, finish active jobs, preserve backups and previous digests, then verify readiness and one focused workflow. No automatic rollback exists. After a partial rollout failure, inspect the saved receipt and actual versions before restoring compatible images. Keep the laptop model relay online when that registration depends on it.
