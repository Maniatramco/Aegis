# Aegis Agent latency investigation — 12 October 2026

The selected local model is Qwen3 Chat (`qwen3:4b`, 8192-token context) on an RTX 3050 6 GB GPU. Testing uses the existing synthetic **Agent full onboarding browser QA** dataset and real browser requests. Answers continue to read authorized current records through LangGraph tools; no answer cache or keyword-based routing was added.

## Findings and configuration

The active low-memory overlay set `OLLAMA_KEEP_ALIVE=0`. Consequently each classifier/tool/answer request unloads the weights and discards the prompt cache. The overlay now defaults to a five-minute idle lifetime, configurable using `AEGIS_AGENT_KEEP_ALIVE`. The limits remain one resident model and one parallel request. Switching to the embedding model can still evict chat on this profile.

The overlay also supports an optional `AEGIS_AGENT_CUDA_BACKEND` override; its default leaves automatic hardware detection enabled. This host's local `.env.oracle` selects the bundled `cuda_v12` backend. Inference was verified at **100% GPU**, with one `qwen3:4b` model resident and an expiration about five minutes away. The model weights, dataset mappings, extraction outputs and context limit were not changed.

Model loading stalled before any prompt evaluation while Windows reported under 1 GB of available physical memory, eventually about 150 MB, with roughly 6.8 GB in the Memory Compression process. A `GGML_CUDA_NO_PINNED` experiment did not resolve that stall and was removed. Changing CUDA backends alone was not demonstrated to eliminate the cold-start problem.

Unused WSL file cache was released and memory compacted using the [Microsoft-documented memory reclamation commands](https://devblogs.microsoft.com/commandline/memory-reclaim-in-the-windows-subsystem-for-linux-2/). Docker restart alone did not clear the remaining backlog. With zero queued/running Aegis jobs or goals, and the other WSL distribution stopped, Docker was stopped and WSL reset. Available Windows physical memory then rose to approximately 5 GB. The four Aegis data volumes were verified intact; the service images needed restoration after restart.

## Live measurements before the complete runtime reset

| Request | Observed elapsed time | Result |
| --- | --- | --- |
| Filename list and extraction completion, earlier baseline | 94 seconds | Both original filenames and both completed extractions reported correctly |
| Same request, cold CUDA 12 model during memory pressure/reclamation | 264 seconds | Correct answer; cold start remains a separate limitation |
| Same request, resident model | 30 seconds | Correct original filenames and completion status |
| Document count, resident model | 29 seconds | Correct count of 2 and both filenames |

The 30-second run spent about 14 seconds classifying, 6 seconds selecting tools, 0.4 seconds reading dataset status and 9 seconds generating. SQL/workspace reading was not the main delay. These are observations under different memory conditions, not a controlled hardware benchmark or a promise for every request.

## Final implementation and verification

The semantic classifier now selects basic metadata reads in the same inference call. Its metadata schema prevents inherited saved-field filters, mutation operations and historical result scope. Requests needing nondefault arguments or other evidence use the normal tool loop. Document-count-only questions can select a deterministic response rendered from the freshly authorized document count. A test adds another file and verifies that the next answer reflects the new count; no factual answer cache is involved.

Completed metadata reads compose an answer without the redundant tool catalog. Product-help requests similarly stop calling tools after their documentation read succeeds, while questions requiring additional document/result evidence retain those source checks. This repairs the observed Review-help loop that repeated `get_application_info` five times and accumulated duplicate observations.

Tool contracts and observations use compact JSON. `list_documents` includes scoped extraction counts and explicitly distinguishes indexing-ready from extraction completion. Pagination, ownership checks, failed-read repair and confirmation for mutations remain enforced.

The bundled llama-server advertised an 8192 MiB RAM prompt cache. The low-memory profile now caps it at 512 MiB through `LLAMA_ARG_CACHE_RAM`, configurable with `AEGIS_AGENT_PROMPT_CACHE_MIB`. Runner logs confirmed the 512 MiB limit. See the [upstream cache option](https://github.com/ggml-org/llama.cpp/blob/master/common/arg.cpp) and [Ollama subprocess environment inheritance](https://github.com/ollama/ollama/blob/v0.35.1/llm/llama_server.go).

The registered Qwen3 Chat model still has an **8192-token context** and **1024-token answer limit**. Its installed Ollama metadata advertises a larger 262144-token maximum; that does not change the configured execution window. Aegis currently uses a conservative UTF-8 byte estimate, reserves answer space and adds a 512-token safety margin. Thus the standard final-answer input budget is estimated at 6656 tokens; classifier/tool-selection calls reserve their smaller 256-token output budget. No context limit or model weights were increased to bypass failures.

All six local services were restored. The preexisting synthetic dataset, both original document records and both saved extraction records were verified preserved after the runtime reset.

| Final real-browser request | Elapsed time | Verified result |
| --- | --- | --- |
| How many documents are available in this dataset? | 12 seconds | There are 2 documents; one semantic model call followed by the authorized catalog read |
| List document filenames and tell whether extraction finished | 16 seconds | Both original filenames and both completed extractions; actual document/status reads, with no extra tool-selection call |
| How to open Review and save edited extracted fields | 9 seconds | One `get_application_info` read, then the final answer; three model calls, without repeat reads or a context-budget error |

The completed filename/status workflow reported approximately 5.3 seconds understanding the request, 1.7 seconds reading documents, 0.5 seconds reading status and 8.6 seconds composing the answer. [Browser proof](results/agent-latency-2026-10-12/browser-proof.png) shows both successful answers and their displayed elapsed times. The count displayed 12 seconds (its saved step durations total approximately 13 seconds). [Help-answer proof](results/agent-latency-2026-10-12/application-help-proof.png) shows the repaired help request completing in 9 seconds at the unchanged context limit.

The [real-model regression report](results/agent-latency-2026-10-12/real-model-benchmark.json) passed **7/7 cases**: actual extraction, misspelled filename listing, document count, saved fields, short follow-up summary, original document evidence with citations, and a confirmation-only re-extraction proposal. This separate synthetic fixture uses the registered LangGraph QA model backed by the same `qwen3:4b` weights. Its measured count/list calls were 1.86/5.89 seconds; fixture size, prompt cache and registered settings differ from the browser dataset, so these do not promise equivalent latency for every request.

The final graph/metadata/onboarding suite passed **65 tests**, and the added product-help loop regression passed independently (**66 unique passing checks**). Compose builds and service health checks passed. `git diff --check` passed. All timing values above are observations from this local run, rather than service-level guarantees.

Cold starts remain slower: a post-reset first count request took 49 seconds before the final count-response optimization. The chat model can be evicted by embedding work under the one-model profile, or unloaded after five idle minutes. Warm-request timings should not be advertised as cold-start guarantees.
