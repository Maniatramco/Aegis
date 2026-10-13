# Maximum configured context — 12 October 2026

At the user's request, updated the existing Qwen3 Chat and Qwen3 Extraction registrations through the normal versioned registration service. Both context ceilings are now **262,144 tokens**, matching the installed Ollama package's advertised context length. The live values before this change were 32,768 for Chat and 8,192 for Extraction.

| Registration | Context ceiling | Output limit | Saved version |
| --- | ---: | ---: | ---: |
| Qwen3 Chat | 262,144 | 1,024 | 4 |
| Qwen3 Extraction | 262,144 | 2,048 | 5 |
| Nomic Embedding | 2,048 | N/A | 1, unchanged |

The before/after configuration receipt is retained in persistent storage at `diagnostics/model-context-max/1791801010.json`. Existing immutable configuration versions remain available. New requests resolve the updated generation profiles without changing embedding mappings or reindexing documents.

The existing Ollama adapter grows its allocated context according to the actual input plus reserved output and safety margin. It does not reserve the entire configured ceiling for every question. Verified against both real dataset execution snapshots:

- Small request: `num_ctx=8192` with the 262,144 ceiling.
- Large synthetic payload: allocation grows to 262,144; this check exercised request construction only, without running large-context inference.
- Payload exceeding the configured ceiling: rejected before dispatch.
- No full conversation history is introduced by this settings change.

## Verification

- 66 model-registration/context checks passed; 32 Ollama checks passed, with one optional test skipped.
- Computer-use verification showed both saved limits on Model Registration. A real Agent question completed under the updated Chat profile. Its model-configuration tool did not expose token-limit fields, and the answer correctly stated that those values were unavailable in its tool observation; the registration page and execution snapshots provide the authoritative values.
- Real extraction through the mapped Extraction profile returned supplier `Northstar Example` and total `1250` from a synthetic invoice, with JSON schema validation. It used an 8,192-token allocation, a 2,048-token output limit and completed in approximately one second.

The installed package's advertised 262,144-token maximum differs from the original Qwen3-4B model card's native 32,768-token specification. Full 262k-context memory use, latency and answer quality have **not** been stress-tested on this laptop. Raising a configuration ceiling does not establish that every request up to that size can complete on its hardware.

![Saved limits](../../docs/testing/results/model-context-max-2026-10-12/registered-limits.png)
