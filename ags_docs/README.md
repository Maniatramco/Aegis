# Documentation

For the live OCI manager handover on branch `ags_sprint1`, start with [architecture](../ARCHITECTURE.md), [Word handover](../Aegis_Architecture_and_Deployment_Handover.docx), [running technologies](../TECH-STACK.md), [verified OCI resources](../OCI-LIVE-RESOURCES.md), [deployment](../DEPLOYMENT.md) and [freeze evidence](../RELEASE-FREEZE.md).

| Topic | Start here |
| --- | --- |
| Architecture and agents | [Current live OCI architecture](../ARCHITECTURE.md) |
| Dataset onboarding | [Datasets](DATASETS.md), [agent onboarding](AGENT-ONBOARDING.md) |
| Answers and retrieval | [Current answer workflow](../ARCHITECTURE.md), [unified knowledge](UNIFIED-KNOWLEDGE.md) |
| Re-extraction and review | [Re-extract Agent](REEXTRACT-AGENT.md), [Extract table](EXTRACT-DATA.md) |
| Models and OCR | [Models](MODEL_CONFIGURATION.md), [OCR](OCR.md), [Ollama](OLLAMA.md) |
| Destinations | [Storage](STORAGE-CONFIGURATION.md), [Oracle](ORACLE.md) |
| Database schema | [Database scripts](../ags_database/README.md), [relational model](../ags_database/ags_docs/DATA-MODEL.md) |
| Accounts and access | [Dataset access](DATASET-ACCESS.md), [users](USER-MANAGEMENT.md) |
| Deployment and recovery | [Deployment and onboarding](../DEPLOYMENT.md), [backup/restore](BACKUP_RESTORE.md), [password recovery](PASSWORD_RECOVERY.md) |
| UI conventions | [Workflow](WORKFLOW-DESIGN.md), [agent identity](AGENT-BRAND.md) |
| Historical verification | [Verification](VERIFICATION.md), [test records](ags_testing/README.md), [design QA](ags_design/design-qa.md) |

Manual Python verification helpers live in `ags_scripts/ags_qa/`. `ags_docs/ags_testing/` retains
dated reports and fictional fixtures. Generated screenshots, logs and raw results
in `docs/testing/results/`, `output/` and `work/` are ignored local evidence; CI
publishes its own artifacts. Older reports may reference files on the original
operator's laptop.

Superseded OCI planning and earlier agent architecture documents have been removed. Current manager documents and the diagram live at the repository root. Dated verification reports remain explicitly historical.
