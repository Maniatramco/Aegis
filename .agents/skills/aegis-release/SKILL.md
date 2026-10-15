---
name: aegis-release
description: Prepare Aegis source freezes, architecture handovers and releases to an already prepared local or OCI installation. Use for this repository release and support work.
---

# Aegis maintenance and release

Start at the repository root and read `AGENTS.md`; for UI work also read `ags_frontend/AGENTS.md`. Follow the user's requested deployment boundary. A documentation or GitHub push request does not authorize changing the running installation.

For source freezes and application releases, read [the README](../../../README.md), [architecture handover](../../../ags_docs/Aegis_Architecture_and_Deployment_Handover.docx) ([PDF](../../../ags_docs/Aegis_Architecture_and_Deployment_Handover.pdf)) and the dedicated [OCI Kubernetes deployment guide](../../../ags_docs/Aegis_OCI_Kubernetes_Deployment_Guide.docx). For database-only work, use the [Oracle database deployment PDF](../../../ags_docs/Aegis_OCI_Database_Deployment_Guide.pdf) and [database README](../../../ags_database/README.md); keep that work scoped to the database. Maintain the existing documents and keep the handover PDF synchronized with its Word source. For Word text extraction, use a document reader or Python python-docx. Do not create further document sets or external diagram assets.

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

For an explicitly requested fresh database schema installation, follow [ags_database/README.md](../../../ags_database/README.md#deploy-the-schema-to-another-oci-database). Use `ags_database/deploy-oci-database.ps1` with the destination wallet, owner, alias and full server service; `-CheckOnly` validates local inputs without connecting. Its shared `install.sql` preflight requires an empty owner and compatible Oracle features. For manual SQL execution, start the client in `ags_database`. Schema creation does not transfer live data or prepare OKE application state. For an existing workspace, use the read-only verification script instead of the fresh installer.

`ags_deploy/deploy-aegis-code.ps1` updates existing deployments; it is not a fresh installer. Require a prepared destination kubeconfig/context, registry and pull credentials, state, DB/schema, object storage, secrets and reranker. `ags_deploy/ags_oke/ags_legacy_provisioning.py` combines the historical Mumbai infrastructure and pilot registry helpers. It is not needed for normal code releases; its explicit subcommands retain pilot-specific settings and private-state requirements. Keep `ags_kubeconfig.py` separate because the existing kubeconfig uses it for authentication.

For an authorized code release, use the deployment guide, choose the correct architecture and dependency build flags, finish active jobs, preserve backups and previous digests, then verify readiness and one focused workflow. No automatic rollback exists. After a partial rollout failure, inspect the saved receipt and actual versions before restoring compatible images. Keep the laptop model relay online when that registration depends on it.
