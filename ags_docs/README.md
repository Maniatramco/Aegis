# Documentation

For the 15 October 2026 manager handover, start with [architecture](ARCHITECTURE.md), [Word handover](Aegis_Architecture_and_Deployment_Handover.docx), [technology versions](TECH-STACK.md), [deployment](DEPLOYMENT.md) and [freeze evidence](RELEASE-FREEZE.md).

| Topic | Start here |
| --- | --- |
| Architecture | [Architecture](ARCHITECTURE.md), [LangGraph](AGENT-LANGGRAPH.md) |
| Dataset onboarding | [Datasets](DATASETS.md), [agent onboarding](AGENT-ONBOARDING.md) |
| Answers and retrieval | [Chat Agent](CHAT-AGENT.md), [unified knowledge](UNIFIED-KNOWLEDGE.md) |
| Re-extraction and review | [Re-extract Agent](REEXTRACT-AGENT.md), [Extract table](EXTRACT-DATA.md) |
| Models and OCR | [Models](MODEL_CONFIGURATION.md), [OCR](OCR.md), [Ollama](OLLAMA.md) |
| Destinations | [Storage](STORAGE-CONFIGURATION.md), [Oracle](ORACLE.md) |
| Database schema | [Database scripts](../ags_database/README.md), [relational model](../ags_database/ags_docs/DATA-MODEL.md) |
| Accounts and access | [Dataset access](DATASET-ACCESS.md), [users](USER-MANAGEMENT.md) |
| Deployment and recovery | [Kubernetes](KUBERNETES.md), [backup/restore](BACKUP_RESTORE.md), [password recovery](PASSWORD_RECOVERY.md) |
| UI conventions | [Workflow](WORKFLOW-DESIGN.md), [agent identity](AGENT-BRAND.md) |
| Historical verification | [Verification](VERIFICATION.md), [test records](ags_testing/README.md), [design QA](ags_design/design-qa.md) |

Manual Python verification helpers live in `ags_scripts/ags_qa/`. `ags_docs/ags_testing/` retains
dated reports and fictional fixtures. Generated screenshots, logs and raw results
in `docs/testing/results/`, `output/` and `work/` are ignored local evidence; CI
publishes its own artifacts. Older reports may reference files on the original
operator's laptop.

Planning documents such as `AEGIS-AGENT-REDESIGN.md` include future work. Check
current source and CI before treating a proposal or dated report as release status.
