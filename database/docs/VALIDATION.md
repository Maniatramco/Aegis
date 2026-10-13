# Local schema migration verification — 2026-10-10

The running Docker application was switched from AEGIS to AGS_OWNER. The source
schema was retained. Before committing, the migration compared every original
column and ID, including credential/session columns, in memory without logging
them. All original values matched.

| AGS_OWNER table | Rows immediately after migration |
| --- | ---: |
| USER_TBL | 1 |
| SESSIONS_TBL | 2 |
| AEGIS_ITEMS | 73 |
| DATASET_TBL | 3 |
| MODEL_CONFIG_TBL | 3 |
| DATASET_MODEL_TBL | 9 |
| DOCUMENT_TBL | 24 |
| PROMPT_TBL | 4 |
| EXTRACT_TBL | 17 |
| JOB_TBL | 42 |
| REVIEW_TBL | 1 |

Model rows include categories for chat, extraction and embedding. Category rows
are not necessarily distinct provider models. Counts can change through normal use.

Observed checks:

- New API/worker Docker images built and the updated stack started.
- Twenty Oracle compatibility tests passed, including an integration test against
  the isolated AEGIS_TEST Oracle schema. It exercises login, upload, extraction,
  review, model mappings/audits and competing worker claims with controlled model
  providers. This is not a real-model extraction benchmark.
- The final workflow/model/merge/review regression run passed all 67 tests
  (77.22 seconds). The final Oracle compatibility run passed 20 tests in
  3.29 seconds. Together these final suites contain 87 passing tests.
- Three relational workflow tests passed with SQLite foreign keys enabled,
  including upload, extraction, review history, invalid references and deletion.
- Oracle SQLcl using the VS Code saved Aegis-Local connection authenticated as
  AGS_OWNER. Every statement in the supplied query file passed.
- The existing three-profile merged extraction
  `6efc597a-01e6-445a-9372-aa7e2578f686` was returned with status `ready`.
- All eleven tables have six audit fields. Live metadata inspection found 45
  foreign keys, nine dataset/model mappings and a valid merged-document link.
  All three fictional profiles remained in the existing extracted JSON.
- Actual Qwen3 generation and Nomic embedding container smoke passed after the
  schema switch: 24.539 seconds generation, 44.852 seconds total, with GPU
  offload reported by Ollama. This tiny smoke is not full resume-extraction timing.
- CPU and GPU Kubernetes renders passed strict schema validation: 36 resources
  across both renders, zero invalid/error/skipped resources. CPU requires no GPU
  resource allocation; GPU remains an optional overlay.
- The web page returned HTTP 200 and API readiness passed after restart.

The post-migration browser check was blocked twice by computer-use's CDP
`Emulation.setFocusEmulationEnabled` timeout. A graphical worksheet/browser test
after migration is therefore not claimed. Earlier extraction UI validation is
documented separately in `docs/testing/assistant-resume-2026-10-10.md`.

No live Oracle Kubernetes cluster was deployed or tested. Cluster image publication,
storage provisioning, secret setup, readiness and the actual end-to-end smoke test
remain deployment prerequisites; see `docs/KUBERNETES.md`. Existing Oracle volumes
require the documented maintenance migration, not just an environment change.
