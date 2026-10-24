# Aegis model integrations

`catalog.py` supplies the authenticated frontend Provider choices: Ollama,
OpenAI, direct Anthropic Claude, Gemini API, Azure OpenAI v1, Bedrock, Vertex AI, OCI and another
OpenAI-compatible API. The form initializes endpoint/authentication defaults
and requires a successful synthetic test before saving. Chat tests validate
function calling; extraction tests validate JSON Schema; embedding tests
validate vectors. Save the model, then enable it for the dataset in Model Mapping.

Agent tool calling supports all these protocol families. Native serializers
live in the provider `agent.py` files (Claude uses `ags_anthropic/native.py`)
and execute through `agent_connection.py`.
Claude/Vertex signatures and Bedrock assistant state survive private graph checkpoints
without appearing in the final answer. Native completed responses use the
existing event channel; incremental token streaming remains specific to the
Ollama and OpenAI-compatible transports.

The account must already expose the model/deployment and grant inference
access. Chat models must support function calling; extraction and embedding
models must support their requested contracts. Another model using an existing
API needs no source changes. A different API still requires an adapter.

All provider contracts have HTTP/SDK mock coverage. Gemini has live free-tier
verification. Other accounts need their own successful registration tests;
no Anthropic, Azure, AWS, Vertex or OCI model credentials are bundled with Aegis.

Protocol references: [Bedrock Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use-client-side.html),
[Vertex function calling](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling),
[Vertex signatures](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thought-signatures),
[OCI SDK](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/generative_ai_inference.html),
[Claude Messages](https://platform.claude.com/docs/en/api/messages/create).

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
| `providers/ags_anthropic` | Direct Claude Messages and native Chat tool calls; no embeddings or extraction |
| `providers/ags_aws` | Native Bedrock client, generation and embeddings |
| `providers/ags_oci` | Native OCI and existing Enterprise AI adapters |

Optional cloud SDKs load only when the corresponding client is used. Local
Ollama execution continues through `ags_local/ollama.py`; it is not silently
routed through the cloud facade. Legacy root imports alias the canonical
modules, preserving older callers and saved protocol/configuration formats.

## Direct Claude Chat

Choose `anthropic` for direct Claude API keys, not Bedrock, Vertex or the
OpenAI compatibility protocol. Only Chat is exposed. The official endpoint
`https://api.anthropic.com/v1` is recognized without an environment allowlist;
custom hosts are rejected for this protocol, including otherwise approved gateways.
The key comes exclusively from the pinned encrypted registration profile.
Optional `workspace_id` supplies `anthropic-workspace-id`; workspace-scoped
keys can leave it blank. No global Anthropic environment credentials are read.

Requests use `x-api-key`, explicit API version `2026-10-21`, native tool schemas,
assistant content blocks and user-role tool results. The adapter uses `auto`
tool choice because forced modes are model-specific; Aegis still rejects missing
required calls, unknown tools and invalid tool schemas. No sampling overrides
are exposed in this API version. Refused, truncated, malformed and inconsistent
responses fail closed without exposing the provider body. Reported input usage
includes cache creation/read tokens when present. Thinking signatures are
retained privately for subsequent tool turns and never become answer text.

Registration, Agent routing/grounded generation and Dashboard routing/general
and grounded generation have isolated mock HTTP coverage. A real key/model
must pass Test Connection and an authorized live chat check before its account
readiness is established. Existing Embedding/Extraction mappings and processing
agents keep their contracts. Publish backend and frontend together when a live
release is requested; no database schema change is needed.

## Cloud OCR and cloud-only datasets

Model Mapping exposes a separate `ocr_model_id` choice. A registered compatible
OpenAI/Gemini extraction model can be selected independently of the extraction
default. `null` uses a compatible cloud extraction default. Local OCR choices
are rejected, and dataset image processing never falls back to Ollama. A dataset
without a cloud vision selection can still read native text; scanned content
requires choosing an eligible cloud OCR registration. The selected model must be enabled, mapped and
accessible to the dataset owner; embeddings and chat-only registrations are
ineligible. Legacy clients omitting the field preserve its saved value. Changing
OCR does not change embeddings or index generation; reindex documents to rerun OCR.

A dataset mapped to a `gemini-*` extraction model on the Gemini Developer API
also uses that registration for scanned PDF pages and embedded DOCX images.
Index jobs pin its model, profile version and encrypted credential reference;
the API key is never copied into jobs or document metadata. Upload approval
lists Gemini OCR as an image destination.

Datasets whose default extraction registration uses GPT-4o or GPT-4o Mini on
`https://api.openai.com/v1` use that saved OpenAI connection for scanned PDF
pages and embedded DOCX images. Dated GPT-4o and GPT-4o Mini snapshots are
supported too. OpenAI OCR is disclosed as an image destination, including when
embeddings are local. Consent identities include the OCR endpoint, model and
pinned credential-profile version. Unsupported OpenAI extraction models fail
before inference; embedding models cannot transcribe images.

Other datasets retain their own local OCR setup. Cloud OCR failures never fall
back to Ollama. The embedding registration remains independent: changing OCR
does not change dataset embeddings or index generation. Previously queued jobs
retain their saved configuration, including job retries. Use the document's
Reindex action after release to create a new cloud OCR snapshot.

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
