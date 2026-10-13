# Aegis Agent runtime

Aegis Agent uses semantic knowledge-source selection followed by a
conversational LangGraph loop: model decision,
validated application tool, authoritative observation, then another decision
or an answer. It no longer routes the default assistant using a growing list
of phrases. The older assistant is available only as an explicit rollback.

## What the assistant can inspect

| Tool | Source / behavior |
|---|---|
| `read_prompt` | Saved prompt filename, version and validated schema |
| `list_documents` | Paginated authorized document filenames, IDs, sizes, versions and indexing states, including files without extraction results |
| `list_datasets` | Paginated authorized dataset names and activity state |
| `list_prompts` | Paginated saved prompt filenames and versions |
| `get_dataset_status` | Live document/extraction counts, scoped job progress and failures |
| `get_model_configuration` | Dataset model mappings, role defaults, names and versions; no credentials or configuration writes |
| `get_application_info` | Built-in application documentation and configured upload limits, distinguished from live processing status |
| `find_extractions` | Actual extraction status, coverage, version and review metadata |
| `read_extraction_results` | Saved structured results from external storage; paginated profiles and field projections |
| `search_documents` | Dataset-mapped embeddings and document passages, with numbered citations |
| `get_workflow_status` | Existing jobs and progress; never starts queued work during a read |
| `prepare_workflow` | Proposes upload, extraction or re-extraction for the confirmation UI |
| `prepare_recovery` | Proposes retry, continuing ready files or cancellation; requires a confirmation button |

Tools enforce ownership, the selected dataset and explicit document filters.
Metadata and application guidance are explicit semantic sources. The LangGraph
model node calls the chat agent to choose a read-only tool; the tool node validates
and runs it, then returns the observation for the next decision. Metadata starts
with catalog/status tools; guidance starts with built-in documentation. Subsequent
read-only calls may combine metadata, original evidence and saved values when the
semantic decision declares supplementary sources for the current question.
Pure metadata/status questions keep a small catalog/status menu throughout the
turn. Mutation-proposal tools are unavailable in these answer routes.
An answer before required reads, or before unfinished catalog pages are inspected,
returns to the model for repair within the eight-decision bound. A persistent
failure returns an explicit limitation. Metadata/help cannot inherit an older
extraction scope; a filter decision without a predicate is reclassified once before
any result reads. Canonical replies store `request_route` decisions/attempts and
`tool_trace` observations, without model reasoning. No filename phrase shortcuts
or spelling-specific handlers select the route.
Metadata/help model contexts carry selected scope rather than unrelated extraction
field catalogs and old workflow claims. Only the current user request is passed
to the metadata/help tool agent; the classifier resolves references from quoted
previous-user context. Completed unfiltered catalogs and completed status/model
reads leave the menu to prevent repeated reads. Dataset status retains real stage states and
timings but excludes redundant process telemetry. Built-in guidance includes the
actual product screens and controls as well as API descriptions; replies use
product language unless the user asks for developer details (`include_api`).
Named saved-extraction lookups can filter the catalog by extraction name before
reading selected fields. A document count plus a saved value uses metadata with
a declared saved-results supplementary source, rather than passage-search prefetch.
The supplementary-source decision is explicit in the classifier schema. The
graph requires those reads and unfinished saved-result/catalog pages before
accepting a reply. Once a combined request's declared reads are complete, final
composition uses the observations without resending the tool schema catalog.
Local required-tool calls reserve their actual 256-token output budget during
context preflight; final answers retain the registered answer budget.
Merged results are not readable through a filter containing only one of their
originals. Select the merged document or all its originals to read the complete
result. Large results require explicit field selection, rather than silent
truncation. Reads add verified review buttons and extraction IDs. Saved-result references
carry extraction ID, saved version, original record index and projected values.
These references identify stored results; they do not claim verified PDF field
coordinates or proof of expertise. Numbered references open the corresponding
extraction in Review. The Review directory filters by dataset, extraction ID,
filename and status, with profile counts computed from saved result JSON.

For saved-result questions, the graph obtains real extraction status and reads
all relevant profile pages before answering. The semantic source decision selects
fields from the verified result-field catalog; a skills question includes skills
rather than assuming them from a title or summary. Typed predicates are evaluated
against saved values, and counts are computed from result records. Filter, count and profile-summary answers are rendered from those facts instead
of allowing a model to guess membership, totals or verification claims. Classification receives the current question so a prior
filter is not silently applied to a new count request. Profile summaries use a small explicit field projection and saved values; Review
always exposes the complete saved result.
For original-content questions it retrieves passages before answering. A completed prompt-save event is acknowledged directly from
its verified receipt, so a model cannot rewrite that event as an unsaved upload.
Executed retrieval is passed as a tool-call/result pair. If a model omits numeric
citations, an exact quoted passage can be linked to its actual retrieved source;
otherwise the UI labels consulted passages without asserting claim support.

An uploaded JSON prompt is classified and validated in the frontend, validated
again by the template API, and saved using filename identity within the dataset.
The assistant receives a server-verified filename/version receipt. It does not
guess that an earlier selected prompt was just updated.

## Execution and storage

The model cannot run writes directly. `prepare_workflow` ends the current graph
turn with a proposal. The existing upload/extraction worker executes only after
the user confirms the dataset, prompt and combined/independent choice. That
worker retains extraction IDs, per-source records, progress, review versions and
failure recovery. This is not a new second execution queue.

| System | Stored information |
|---|---|
| Oracle | Ownership, IDs, relationships, statuses, versions, audit metadata and artifact references |
| Routed file/object storage | Originals, merged files, prompts, extraction/review JSON, conversations, tool traces, graph checkpoints |
| Qdrant | Search embeddings and retrieval metadata |

Graph checkpoints use `agent-state/<conversation-id>/checkpoints.json`; no
Oracle checkpoint payload table is added. They use JSON rather than pickle.
Recent graph snapshots are bounded; full completed conversations remain in
their separate artifacts. Hosted LangSmith tracing is disabled.

Completed conversation history is restored between requests. Worker jobs
continue independently of the browser. A failed model turn restarts from the
last completed conversation on retry; arbitrary mid-node crash replay is not
exposed as a supported user-facing resume operation.

## Model support

The runtime supports Ollama and OpenAI-compatible Chat Completions tool adapters.
No cloud provider is silently substituted. Unsupported protocols produce an
actionable model-selection error. Hosted-provider integration requires separate
provider credentials and testing; local validation uses Ollama.

The installed Qwen3/Ollama combination did not reliably return native tool
calls in direct probes. Qwen3 therefore uses a JSON-schema-constrained decision
envelope with the same typed tools and iterative graph. Other Ollama models use
native tool calls. All arguments are validated again at the tool boundary.

There are at most eight model decisions per turn. Input/tool observations and
output must fit the registered model's context limit. CPU-only execution remains
supported; model speed depends on accessible hardware and workload. This change
does not force GPU resources or change the existing optional GPU selection.

## Docker and Oracle Kubernetes

Set `AEGIS_AGENT_ENGINE=langgraph` (default) and build the API, worker and web
images from this checkout. `AEGIS_AGENT_ENGINE=legacy` is the rollback switch.
Dependencies are pinned in `ags_backend/requirements.lock`, resolved for Linux.
The same image runs locally and on Kubernetes; there are no laptop paths in the
application runtime.

The base Kubernetes ConfigMap enables LangGraph and disables hosted tracing.
Retain the established single API/worker Pod, shared writable storage and one
replica while using filesystem locks. Additional replicas require a distributed
conversation lock/checkpoint implementation, not just changing replica count.
CPU base manifests require no GPU driver; use the existing optional GPU overlay
only with compatible accessible resources. Production browser access requires
HTTPS. Cluster image pull, Oracle credentials/connectivity, object-store access,
PVC behavior and real model timing still require validation on the target OKE
cluster. No live deployment is performed by this change.

The graph computes its decisions in the prepare request; the completed answer is
then returned through the existing reply stream. This is not live token streaming
during every model/tool step. Long CPU turns show the workspace/request check
indicator; accepted extraction jobs retain their existing progress UI.

## Verification

Scripted tests exercise the real graph, storage, ownership, confirmations,
result paging, citations, recovery proposals and invalid tool handling without
claiming mocked calls prove model understanding. Actual model/browser results
are recorded separately in the implementation validation report.
See [the observed results and limitations](ags_testing/AGENT-LANGGRAPH-VALIDATION.md).

`ags_deploy/ags_docker/Dockerfile.agent-browser` is an opt-in QA image, not a required application
service. `ags_frontend/ags_tests/agent-live-e2e.js` accepts credentials on stdin, uses the
fictional resume fixtures, and writes screenshots and a JSON report to `/results`.
`python -m ags_app.agent_test_setup` explicitly provisions an isolated QA account and
dataset; it is never run at startup. Its credential artifact is encrypted using
the application's master key and is never printed.

`python -m ags_app.agent_smoke` uses that QA dataset to verify a real graph workflow
proposal and a small real extraction without confirming/submitting worker jobs.
For CPU verification, run an Ollama test container without `--gpus`, share the
installed model files, wait for `/api/tags`, and set `AEGIS_OLLAMA_URL` plus
`AEGIS_OLLAMA_ENDPOINT_HOSTS` for that test process only. `AEGIS_AGENT_SMOKE_DATASET`
can select an earlier isolated QA dataset. This smoke is distinct from a full
CPU browser/worker benchmark. Remove the temporary test container afterwards.

Confirmed extraction on existing documents checks the live embedding/index
signature. If any selected ready document has an outdated index, the server
adds a visible `Reindex selected documents` prerequisite and queues indexing
only for those stale documents. The same confirmation authorizes extraction
after all prerequisite jobs complete; the complete selected scope, extraction
mode and external consent are retained. An indexing failure pauses the chain
and exposes the standard restart/recovery controls. Original files and previous
extraction results are preserved. Merely selecting a document or template does
not submit indexing jobs.
