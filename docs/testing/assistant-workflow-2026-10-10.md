# Assistant upload, extraction and recovery verification

Tested the real Docker app at `http://localhost:3003` on 10 October 2026.
Oracle Free, Qdrant, Ollama Qwen3 4B and Nomic embeddings were used. Browser
actions used the computer-use skill. Database inspection was read-only.
All resumes and context-limit fixtures were fictional test data.

## Current behavior

- Sending moves attachment cards out of the composer into the submitted question.
  Uploaded document references are not restored as composer attachments or filters.
- Multiple documents require an explicit **Merge into one result** or
  **Extract independently** choice. The saved template determines the output schema.
  Merge combines document text for one extraction; originals remain separate and unchanged.
- **Confirm upload and extraction** authorizes the complete chain. The worker
  reconciles indexed documents and submits extraction without a second confirmation
  or an open browser. A page reload restores actual job progress.
- Upload/indexing success is reported separately from field-extraction success.
  Each completed result has its own **Review result and evidence** button,
  including successful siblings when another independent job fails.
- A failed extraction offers scope adjustment, retry with current model settings,
  model-registration guidance and ending the request. Successful results are kept;
  only remaining documents are submitted again. Content is never silently truncated.
- Failed indexing can be retried, or the user can explicitly continue using only
  successfully indexed documents. An uncertain submission requires inspection of
  accepted work before resubmitting, to avoid duplicates.

## Observed end-to-end results

| Case | Observed outcome | Time |
| --- | --- | --- |
| Five fictional PDF resumes, independent | Five indexed documents and five completed results. Every nested field matched the pack's expected JSON exactly. All five Review buttons appeared; Meera's result and original PDF were opened in Review. | 260.89 seconds from workflow confirmation to last saved result; 28.44 seconds upload/indexing; 232.14 seconds from extraction submission to last result, including queue time. |
| Two parts of one fictional resume, merge | One result contained the name/email from part 1 and employer/all four skills from part 2. Review opened the single result and switched to the second original. | 65.91 seconds from confirmation to saved result; extraction 49.74 seconds. |
| Deliberately oversized merged context | Both documents indexed, then extraction stopped: configured 8,192 tokens, estimated requirement 22,792. Assistant showed failure-specific recovery choices, not workflow completion. | Upload/indexing 20.01 seconds; context guard rejected generation before model inference. |
| Reduced-scope recovery | Used **Adjust scope and retry extraction**, selected the already uploaded small file, confirmed, completed and opened Review. No files were uploaded again. Missing employer remained `null`, skills remained `[]`. | Fresh extraction 50.10 seconds. Time spent making the manual recovery selection is excluded. |

The model container reported **100% GPU, context 8,192** during this run. These
measurements describe this laptop/run, not CPU performance or a deployment SLA.
The earlier real CPU-only Arjun extraction completed in 370.82 seconds; see the
[earlier CPU/startup verification](assistant-resume-2026-10-10.md).
The same application containers and CPU-default/optional-GPU deployment artifacts
are retained. No live Oracle Kubernetes deployment or cluster acceptance test occurred.

No verified field-level quotes were returned in these cases. The Review screen
explicitly warns users to check values against the originals. Matching the test
fixtures does not establish accuracy for arbitrary documents.

## Original error diagnosis

The reported 4,096-token / 4,784-token requirement belongs to historical failed
extraction `daca4ec7-91a1-4a19-906d-2f38b81d4a06` in **Resume Dataset**. Its immutable
job snapshot used context 4,096, output 1,024 and timeout 300. Both resume datasets
now resolve **Qwen3 Extraction**, context 8,192, output 2,048 and timeout 1,200.
Retrying through Assistant creates a fresh job with current settings; it does not
reuse or overwrite the failed job's snapshot.

## Checks and evidence

- Targeted backend tests cover merge scope, mandatory choice, independent partial
  failure, no duplicate successful work on retry, current-settings pinning,
  ownership/scope restrictions, uncertain submissions, and worker continuation
  without browser polling. Existing routing, worker and review checks passed.
- All 92 frontend unit checks passed; the Docker production build includes type checking.
- The backend, worker and web Docker images were rebuilt with the changes.
- The final container smoke test passed: installed models, real structured
  generation, real embedding and API readiness. It observed GPU offload with
  2,874,062,929 VRAM bytes; tiny generation took 42.275 seconds and the whole
  smoke test 52.428 seconds. This is not a full-document benchmark.
- After the final rebuild, restored the merged workflow, verified zero composer
  attachments and zero uploaded-document filters, reopened Review and switched sources.
- [Completed Assistant workflow with an empty composer](assistant-workflow-complete.jpg)
- [Merged result and source review](merged-resume-review.jpg)
- [Context failure and recovery options](context-failure-options.jpg)
- [Reproducible merged test inputs](fixtures/merged-resume-prompt.json)

The existing single-candidate resume template was used in independent mode.
The merged fixture's template explicitly describes two parts of one candidate;
merging multiple candidates with a single-candidate schema would be ambiguous.
