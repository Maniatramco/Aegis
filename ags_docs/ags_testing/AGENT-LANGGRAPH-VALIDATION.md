# LangGraph Assistant validation — 2026-10-10

The updated application is running at http://localhost:3003 in Docker, using
Oracle Free 23.26.3.0 (AGS_OWNER), Qdrant and Ollama 0.35.1 with qwen3:4b.
Testing used a separate QA account and fictional resumes. Existing user data
was retained. No live Oracle Kubernetes deployment, git commit or push was made.

## What was exercised

| Scenario | Observed outcome |
|---|---|
| Browser login and dataset/model selection | Passed against the running application |
| Malformed JSON prompt | Validation error displayed; prompt not saved |
| Valid JSON prompt/update request | Exact saved filename/version acknowledged; available in Prompt templates; not mistaken for a document upload |
| Three attached resumes and extraction request | One semantic model decision produced upload → extract proposal; attachments moved into the sent question and cleared from composer |
| Multiple-file confirmation | Combined/independent choice required; selected combined, separate profile records |
| Upload → physical merge → indexing → extraction | Completed with a merged filename and three source files |
| Review | Opened from Assistant and displayed Arjun Rao, Meera Iyer and Nikhil Shah |
| Complete saved fields | Authenticated API comparison matched every field of all three profiles to manually specified fixture expectations |
| “If already extracted, summarize; do not extract again” | Read actual saved fields, answered for all three people, included extraction ID/version and opened Review; no workflow calls proposed |
| Kubernetes question about original files | Actual retrieval found Meera's passage on page 2, with a verified numeric citation and Sources in the browser |
| General knowledge with a dataset selected | Authenticated real-model request explained Kubernetes without proposing a workflow |
| CPU without GPU allocation | Real LangGraph proposal plus small known-value model extraction passed; Ollama reported zero VRAM use |
| Isolation/recovery/invalid tools | Focused backend tests passed, including dataset/owner filters, merged profile paging, proposed recovery, checkpoint persistence and confirmation boundaries |

The computer-use connector returned `Transport closed`. Browser verification
therefore used real Chromium/Playwright against the same Docker web service;
this was not a mocked UI or a successful native computer-use session.

## Measured timings

These observations include load, queue and other machine conditions, not
performance guarantees. The full browser workflow used an accessible NVIDIA
GPU; the CPU smoke used a separate Ollama container with no GPU DeviceRequests.

| Measurement | Seconds | Scope |
|---|---:|---|
| Prompt request including cold model classification | 51.04 | Full browser run |
| Attached-file extraction proposal, warm model | 1.96 | One semantic model decision; no extraction yet |
| Three-file upload, indexing and completed merged extraction | 186.88 | Full browser run, GPU available |
| Saved-result summary, final retest | 15.23 | All three profiles; no new extraction |
| Original-file Kubernetes answer, final retest | 98.83 | Retrieval plus model switching/loading and answer |
| General knowledge answer, warm model | 6.91 | Authenticated API request; no workflow proposed |
| CPU workflow proposal | 71.72 | Real graph; not confirmed |
| CPU proposal plus small known-value extraction | 77.86 | Zero VRAM; no worker jobs submitted |

The CPU smoke establishes actual CPU execution, not a full three-resume CPU
browser/worker benchmark or equal speed across hardware. Model loading and
switching remain noticeable on this laptop. The graph prepare request finishes
before its answer is returned through the existing stream; live token/tool
streaming during preparation is not implemented.

## Defects found and corrected

- Semantic classification initially confused extracting attachments with answering
  a document question. Intent and knowledge source are now separate decisions;
  resolved attached-file workflow requests prepare typed proposals directly.
- The Qwen/Ollama native tool template was unreliable. Qwen now uses validated
  JSON-schema tool decisions inside the same iterative graph.
- Generated filenames were used as document IDs. Tool contracts now constrain
  references to owned IDs, in addition to enforcing authorization at execution.
- Large saved-result contexts caused memory pressure. Profile paging and explicit
  field projections keep summaries small; full results remain in Review.
- One full browser run failed its final citation assertion: the model named the
  correct candidate and quoted evidence but omitted `[n]`. Exact matching quoted
  passages are now linked to retrieved evidence; the final browser retest passed.
  The original failed report is retained and is not relabeled as passing.
- Preflight retrieval observations now preserve executed tool-call/result pairs,
  reducing redundant retrieval and model reloads.

## Checks and evidence

- 108 backend graph/workflow regression tests passed before the final citation
  and observation-pair refinement; all 16 graph tests then passed on final code.
- 96 frontend tests passed; production build, type checking and static generation
  succeeded with the review links and projection notice.
- Hardware-selection script: four checks passed, including CPU without a GPU probe.
- CPU and optional-GPU Kubernetes configurations were rendered and schema checked:
  each had 18 valid resources, zero invalid resources and zero errors;
  see the deployment guide for prerequisites. Rendering changes no cluster resources.
- Final API/worker images include the current graph code; API/web/Oracle/Ollama
  health checks passed. The temporary CPU model container was removed.

Evidence files alongside this report retain the initial full browser outcome,
final document/summary retests, CPU smoke and exact-field comparison. Screenshots
show the completed Assistant, merged review, saved summary and document search.

[Initial browser report](../../ags_runtime/ags_archive/ags_cleanup_2026_10_14/ags_docs/ags_testing/langgraph-browser-initial.json) ·
[Document retest](../../ags_runtime/ags_archive/ags_cleanup_2026_10_14/ags_docs/ags_testing/langgraph-document-retest.json) ·
[Saved-summary retest](../../ags_runtime/ags_archive/ags_cleanup_2026_10_14/ags_docs/ags_testing/langgraph-summary-retest.json) ·
[CPU smoke](../../ags_runtime/ags_archive/ags_cleanup_2026_10_14/ags_docs/ags_testing/langgraph-cpu-smoke.json) ·
[Exact-field comparison](../../ags_runtime/ags_archive/ags_cleanup_2026_10_14/ags_docs/ags_testing/langgraph-extraction-fields.json) ·
[General answer](../../ags_runtime/ags_archive/ags_cleanup_2026_10_14/ags_docs/ags_testing/langgraph-general-answer.json)

[Merged review screenshot](../../ags_runtime/ags_archive/ags_cleanup_2026_10_14/ags_docs/ags_testing/langgraph-merged-review.png) ·
[Saved-summary screenshot](../../ags_runtime/ags_archive/ags_cleanup_2026_10_14/ags_docs/ags_testing/langgraph-saved-summary.png) ·
[Document-search screenshot](../../ags_runtime/ags_archive/ags_cleanup_2026_10_14/ags_docs/ags_testing/langgraph-document-search.png)

Verified extraction: `9dd182c7-999b-417b-ba0e-e1b07b9b50e7`, ready, version 1,
three profiles. Merged file:
`merged-01-arjun-rao-backend-3-files-208daf2c.pdf`.

## Remaining validation boundaries

The same application images and storage routing are used for Docker and OKE.
The CPU base has no GPU requirement; the optional NVIDIA overlay requires usable
allocated resources. Actual OKE scheduling, image pulls, credentials, Oracle and
object-store connectivity, PVC behavior, ingress HTTPS/timeouts and real inference
still need validation on the target cluster. No cluster access was used here.

Hosted OpenAI-compatible adapters are implemented but were not exercised with
real provider credentials. Unsupported protocols fail explicitly. Arbitrary
mid-node crash replay and multi-replica distributed checkpoint locks are not
supported by this pilot; keep the established single API/worker Pod and replica.

Oracle stores metadata and artifact references. Original/merged files, prompt and
result JSON, conversations, tool traces and graph checkpoints remain outside SQL.
Qdrant remains the retrieval index. No Oracle checkpoint payload table was added.
