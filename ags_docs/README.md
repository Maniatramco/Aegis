# Aegis documentation

Current manager handover: **ags_sprint1**. Live OCI and application facts were inspected read-only on **15 October 2026 at 22:26 IST**. They describe that snapshot, not continuous monitoring. The source freeze remains tagged `aegis-freeze-2026-10-15`.

## Architecture and manager handover

All current architecture material is in **ags_architecture/**.

| Document | Purpose |
| --- | --- |
| [Word handover](ags_architecture/Aegis_Architecture_and_Deployment_Handover.docx) | End-to-end architecture, workflows, running versions and OCI placement for Swamy |
| [Architecture](ags_architecture/ARCHITECTURE.md) | Current browser, API, agents, worker, data and model boundaries |
| [Running technologies](ags_architecture/TECH-STACK.md) | Observed versions and active Gemini mappings; optional laptop models distinguished |
| [OCI resources](ags_architecture/OCI-LIVE-RESOURCES.md) | Verified compute, database, network, storage and container allocations |
| [Sanitized snapshot](ags_architecture/OCI-LIVE-SNAPSHOT.json) | Inspection evidence and deployed image references |
| [Architecture image](ags_architecture/aegis-architecture.png) · [editable SVG](ags_architecture/aegis-architecture.svg) | One current diagram, reused by the root README and Word handover |
| [Unified knowledge](ags_architecture/UNIFIED-KNOWLEDGE.md) | Publication, integrity and retrieval implementation |

## Design

**ags_design/** contains the current [workflow display standard](ags_design/WORKFLOW-DESIGN.md), [Agent identity](ags_design/AGENT-BRAND.md), approved workflow reference image and original Agent brand asset. Dated design QA is kept with historical verification below. The retired standalone HTML demo remains available through the freeze tag linked in the workflow standard.

## Deployment

**ags_deployment/** contains [deployment and onboarding](ags_deployment/DEPLOYMENT.md), [freeze and validation evidence](ags_deployment/RELEASE-FREEZE.md) and the original [source manifest](ags_deployment/RELEASE-MANIFEST.json). The discoverable [release skill](../.agents/skills/aegis-release/SKILL.md) remains under `.agents/skills/`; a documentation push does not deploy the app. A new tenancy needs provisioned resources and application initialization before the code release script can run.

## Operations

| Guide | Scope |
| --- | --- |
| [Runtime settings](ags_operations/RUNTIME-CONFIG.md) | Shared runtime.toml values and profiles |
| [Storage configuration](ags_operations/STORAGE-CONFIGURATION.md) | Database, vectors and file destinations |
| [Model configuration](ags_operations/MODEL_CONFIGURATION.md) | Registration, limits and dataset mappings |
| [CPU reranking](ags_operations/RERANKING.md) | Reranker setup and checks; live execution is inside OCI |
| [Agent reliability](ags_operations/AGENT-RELIABILITY.md) | Operator benchmarks and persistent goals |
| [Stop/start with PowerShell](ags_operations/AEGIS_DAILY_STOP_START.md) | Application replicas; leaves the node running |
| [Stop/start in OCI Console](ags_operations/AEGIS_PORTAL_STOP_START.md) | Existing worker VM; preserves its disks and data |

## User guides

**ags_guides/** contains [datasets](ags_guides/DATASETS.md), [Agent onboarding](ags_guides/AGENT-ONBOARDING.md), [dataset access](ags_guides/DATASET-ACCESS.md), [users and roles](ags_guides/USER-MANAGEMENT.md), [Extract Data and exports](ags_guides/EXTRACT-DATA.md) and [re-extraction](ags_guides/REEXTRACT-AGENT.md).

## Separate local installation

**ags_local/** covers optional development configurations, not the current OKE topology: [Oracle Free](ags_local/ORACLE.md), [VS Code Oracle access](ags_local/ORACLE-VSCODE.md), [Ollama](ags_local/OLLAMA.md), [Qwen OCR](ags_local/OCR.md), [local password recovery](ags_local/PASSWORD_RECOVERY.md) and [local PostgreSQL backup/restore](ags_local/BACKUP_RESTORE.md). Launch commands and Compose files are documented in [local setup](../local/README.md).

Canonical schema and migration documentation stays beside SQL under [ags_database](../ags_database/README.md), including the [relational model](../ags_database/ags_docs/DATA-MODEL.md). It is separate from the manager architecture summary.

## Historical verification

**ags_testing/** holds dated test reports, the [earlier verification history](ags_testing/VERIFICATION-HISTORY.md), [design QA history](ags_testing/DESIGN-QA-HISTORY.md) and fictional inputs in `ags_fixtures/`. These describe the revision and environment tested then. Old test counts, retired controls and local evidence links are not claims about the current deployment.

Manual executables belong in [ags_scripts/ags_qa](../ags_scripts/ags_qa/README.md). Generated screenshots, logs and raw results are ignored local evidence; CI publishes its own artifacts. Some historical links resolve only on the original operator's laptop. Earlier committed material remains in Git history, and previously retired guides are linked at the freeze tag when needed.

## Why the remaining README files exist

There are **eight** READMEs, each serving a different entry point. Additional README files are not needed in each documentation group; this page indexes them all.

| Location | Responsibility |
| --- | --- |
| [Repository root](../README.md) | Project introduction and manager entry point |
| This document | Single documentation index |
| [local](../local/README.md) | Compose setup and launcher commands |
| [ags_database](../ags_database/README.md) | SQL installation and migration boundaries |
| [Agent package](../ags_backend/ags_app/ags_agent/README.md) | Agent module ownership and contracts |
| [Model package](../ags_backend/ags_app/ags_models/README.md) | Provider adapters and extension contracts |
| [Frontend tests](../ags_frontend/ags_tests/README.md) | Unit/browser commands and disposable test setup |
| [Manual QA tools](../ags_scripts/ags_qa/README.md) | Opt-in benchmarks and session-specific tools |

Keep a single current document per subject. Update the document in its group and this index when its path changes. Preserve the live inspection timestamp when editing the wording; publish a newer runtime claim only after another read-only verification.
