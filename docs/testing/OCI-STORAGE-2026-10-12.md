# Storage configuration and fresh resume onboarding — 2026-10-12

## Delivered and verified

One admin Storage screen configures Local/OCI destinations, tests connections, saves configuration, and archives/restores a fresh workspace. OCI Object Storage is active with namespace `bmyljaecivrj`, bucket `mk-aegis`, region `ap-mumbai-1`, prefix `aegis`. API and worker are healthy with read-only OCI credential mounts and the SDK installed.

The old active workspace was reset through the browser. No existing local artifact was uploaded. The OCI prefix contained zero objects before and immediately after the reset. The archive `9933bdb7-be9e-4dd9-af85-ba1d2b3bc153` is local at `/data/workspace-archives/9933bdb7-be9e-4dd9-af85-ba1d2b3bc153`; it contains 2,083 verified files, including 192 legacy execution/checkpoint files added during final cleanup. The normal Restore action remains available once the active workspace is empty.

Old active counts: 31 datasets, 91 documents, 86 results, 33 prompts, 152 conversations, 408 plans, six onboarding workflows and 231 jobs. All 39 old Aegis Qdrant collections were cleared. Users, model profiles, secrets and weights were intentionally retained.

## New workspace

| Entity | Value |
| --- | --- |
| Dataset | `Resume Extraction` · `1c9f706e-6e7a-5be1-9373-3424f4e3cd27` |
| PDF | `maya-rao-sample-resume.pdf` · `a6046f29-0674-424e-b8e7-3744980a76b8` |
| Prompt | `resume-extraction-v1.json` · `0e46a3a9-865a-4a9b-8be8-ca2fab4d416e` |
| Extraction | `bb9d7c57-a331-4ff1-bf0b-9c8c3c4c344d` · ready, v1, unreviewed |
| Model mappings | Nomic Embedding / Qwen3 Chat / Qwen3 Extraction |

All eight Agent onboarding stages completed through the browser, including prompt setup, document upload, indexing and extraction. Exactly one active dataset, document, prompt, extraction and onboarding record remain. The two processing jobs completed. The new verification conversation and plan are the only active chat/plan records.

The PDF is explicitly fictional. Its ten top-level fields matched the complete expected object, including nested employment/education arrays: Maya Rao, Senior Data Engineer, Hyderabad, eight years, eight skills, two employers, graduation 2018 and the stated certification. JSON Schema validation passed. This validates this single fixture; it is not a general model accuracy benchmark.

Original SHA-256: `cf8b71309548bc4a2a4bd542d47f0a1c0b02fe94cf87d008fb8cbdf6eebb2c85`. The downloaded OCI original matched the locally authored PDF exactly. Saved Parquet passed checksum and typed/lossless result readback checks. Both original and results were visibly loaded side by side in Review; Save changes was disabled without edits.

## Agent and destination switching

Question submitted through Aegis Agent: “What name, years of experience and skills were saved in the extraction?”

The answer returned Maya Rao, eight years, Python, SQL, FastAPI, Docker, Apache Airflow, PostgreSQL, AWS and Git, citing the saved extraction and linking Review. The actual tool trace includes `read_extraction_results`. The response completed in 29 seconds on this laptop. Unified semantic search also discovered the new extracted record. Qdrant now has only the new document collection and the unified knowledge collection; no old entity/dataset payloads remain.

Through the Storage screen, Local `/data/resumes` was saved while the fresh dataset existed. Review then reopened the existing OCI original and fields successfully, and canonical reads passed unchanged. OCI was subsequently saved as the active destination again. No migration or extra document upload occurred. All new bucket object names were checked against the archived entity IDs: none referred to the old workspace. No secrets/configuration/models/archive files appeared in the bucket.

## Checks

- Backend storage, OCI, dataset model and knowledge suite: 74 passed before the final legacy-route regression was added. Final focused storage suite: 10 passed (75 distinct backend cases across these suites).
- Frontend suite: 125 existing tests and three new Storage screen tests passed; 128 total. TypeScript and production builds passed.
- New backend regressions cover destination/bucket switching, later entity files, older object routes, local roots, credential path checks, admin access, active-job refusal, archive/restore, legacy execution state and checksum tampering.
- New frontend tests cover test/save separation, exact fresh-start confirmation, and connection failure handling.
- API/worker were rebuilt and restarted after final routing/reset fixes. The final live verification ran against those containers and OCI was left active.

Proof: [final JSON](results/oci-storage-2026-10-12/final-proof.json), [Local switch JSON](results/oci-storage-2026-10-12/local-switch-proof.json).

![Storage configuration](results/oci-storage-2026-10-12/storage-configured.png)

![Completed onboarding](results/oci-storage-2026-10-12/resume-onboarding.png)

![Review original and extracted fields](results/oci-storage-2026-10-12/resume-review.png)

![Agent reads the saved extraction](results/oci-storage-2026-10-12/agent-resume-answer.png)

![Review still reads OCI after switching to Local](results/oci-storage-2026-10-12/review-after-local-switch.png)
