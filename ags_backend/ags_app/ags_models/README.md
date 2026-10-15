# Aegis model integrations

`catalog.py` supplies the authenticated frontend Provider choices: Ollama,
OpenAI, Gemini API, Azure OpenAI v1, Bedrock, Vertex AI, OCI and another
OpenAI-compatible API. The form initializes endpoint/authentication defaults
and requires a successful synthetic test before saving. Chat tests validate
function calling; extraction tests validate JSON Schema; embedding tests
validate vectors. Save the model, then enable it for the dataset in Model Mapping.

Agent tool calling supports all these protocol families. Native serializers
live in the provider `agent.py` files and execute through `agent_connection.py`.
Vertex signatures and Bedrock assistant state survive private graph checkpoints
without appearing in the final answer. Native completed responses use the
existing event channel; incremental token streaming remains specific to the
Ollama and OpenAI-compatible transports.

The account must already expose the model/deployment and grant inference
access. Chat models must support function calling; extraction and embedding
models must support their requested contracts. Another model using an existing
API needs no source changes. A different API still requires an adapter.

All provider contracts have HTTP/SDK mock coverage. Gemini has live free-tier
verification. Other accounts need their own successful registration tests;
no Azure, AWS, Vertex or OCI model credentials are bundled with Aegis.

Protocol references: [Bedrock Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use-client-side.html),
[Vertex function calling](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling),
[Vertex signatures](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thought-signatures),
[OCI SDK](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/generative_ai_inference.html).

`registration.py` manages model registration and encrypted, versioned
credentials. `registry.py` manages registration identity and consolidation.
`parameters.py` validates model settings. `validation.py` owns destination,
protocol and credential policy. `connection.py` is the guarded execution
facade: bounded HTTPS transport, generation schema checks and vector checks.

`provider_registry.py` selects fixed implementation modules from saved
protocol IDs. It never imports a path supplied by a user or substitutes a
different provider after a failure. Providers are:

| Folder | Implementation |
| --- | --- |
| `providers/ags_local` | Existing Ollama transport and model operations |
| `providers/ags_gcp` | Gemini Developer API compatibility and native Vertex |
| `providers/ags_azure` | Azure OpenAI v1, sharing the compatible wire contract |
| `providers/ags_openai` | Shared OpenAI-compatible generation and embeddings |
| `providers/ags_aws` | Native Bedrock client, generation and embeddings |
| `providers/ags_oci` | Native OCI and existing Enterprise AI adapters |

Optional cloud SDKs load only when the corresponding client is used. Local
Ollama execution continues through `ags_local/ollama.py`; it is not silently
routed through the cloud facade. Legacy root imports alias the canonical
modules, preserving older callers and saved protocol/configuration formats.

## Gemini OCR and cloud-only datasets

A dataset mapped to a `gemini-*` extraction model on the Gemini Developer API
also uses that registration for scanned PDF pages and embedded DOCX images.
Index jobs pin its model, profile version and encrypted credential reference;
the API key is never copied into jobs or document metadata. Upload approval
lists Gemini OCR as an image destination. Other datasets retain their own
local OCR setup. A cloud OCR failure never falls back to Ollama.

The adapter in `providers/ags_gcp/ocr.py` uses Google's
[image input API](https://ai.google.dev/gemini-api/docs/openai#image-understanding).
The shared OCR path still rejects incomplete, invalid, unreadable and blank
transcriptions, retains original/native text and labels OCR as unverified.
Cloud cache identities pin configuration versions, not unavailable weight
digests. OCR output/context limits also respect the extraction registration.

Gemini routing declares union-shaped tool contracts as separate bounded
functions. Returned arguments are validated against the selected branch and
the original canonical schema before any agent acts.

## Add another model using a supported protocol

Use Aegis Model Registration: name, category, protocol, endpoint, model or
deployment ID, authentication and supported limits. Run the synthetic
connection test, save, then assign the model in Model Mapping. No folder or
new adapter is needed for another model using the same protocol. Register
chat and extraction roles separately. An embedding change requires applying
the mapping and reindexing existing documents.

Azure OpenAI v1 uses `https://RESOURCE.openai.azure.com/openai/v1` and the
Azure **deployment name** in Model / deployment ID. Enter the key through
Authentication. Verify tool calling for Agent chat and structured output for
extraction with the deployed model. A custom gateway requires a specific
server-approved hostname. Local Ollama models must already be available at
the approved local service.

## Add a provider with a different API protocol

1. Implement `generate(connection, instruction, text, schema, output_tokens,
   extra)` and `embed(connection, texts, query, dimensions, extra)` in its
   provider folder. Generation returns text; embeddings return raw vectors.
   The shared facade retains completion, schema and vector validation.
2. Add its fixed module and authentication modes to `provider_registry.py`.
   Add endpoint/credential validation and permitted inference parameters.
3. Expose the supported protocol and fields in backend registration schemas
   and the frontend Model Registration form. If its tool-call protocol is
   different, add the Agent transport/serialization support explicitly;
   generation support alone does not imply Agent support.
4. Test generation, embeddings, schema failures, vector count/order/dimensions,
   credentials, immutable queued profiles and endpoint restrictions without
   real secrets. Then perform a small authorized live smoke test.

Do not copy dataset/storage logic into provider implementations. Do not add
an arbitrary endpoint, insecure transport, implicit credential reuse or
automatic provider fallback to make a test pass.
