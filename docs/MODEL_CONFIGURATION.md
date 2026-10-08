# Model registration and dataset mapping

Use **Model Registration** to save each model's category, connection protocol,
endpoint, model or deployment ID, authentication, and timeout. Use **Model
Mapping** to select the dataset's required **Embedding**, **Chat**, and
**Extraction** models, then choose **Save & Apply**. Different datasets can reuse
registrations or choose different connections. New registrations have one
category; existing combined chat/extraction registrations remain supported.

Test Connection sends synthetic input through the same adapter used for actual
operations. It reports latency and, for embeddings, the returned dimension. An
extraction test must produce JSON matching the requested schema. Testing does not
save the supplied credentials. Save Model stores credentials encrypted with the
deployment master key; they are not returned to the browser or safe exports.

## Token limits and extra parameters

Each registration stores its own inference settings:

- **Chat and Extraction:** Context token limit (default 32,768) and Maximum
  output tokens (default 4,096). The context must exceed the output reservation
  by more than 512 tokens. Aegis estimates input from UTF-8 text conservatively;
  this is not an exact provider tokenizer count. Oversized input fails clearly,
  without silent truncation. Ollama receives `num_ctx` and `num_predict`; cloud
  adapters send the corresponding native output-token field.
- **Embedding:** Input token limit per chunk or query (default 8,192 for new
  registrations), and optional output dimensions. Embeddings produce vectors,
  so they have no generated-output-token setting. Their limits and parameters
  stay separate from generation settings.
- **Add extra parameters:** Enter a JSON object, for example
  `{"temperature": 0.2, "top_p": 0.9, "seed": 42}` for Ollama. The screen lists
  supported keys for the chosen protocol and role. Bedrock/Vertex use native
  names such as `topP`; Ollama/OpenAI/OCI use `top_p`. Ollama also accepts
  `keep_alive`, including for embeddings. Supported keys can still be rejected
  by a particular deployed model, so use Test Connection before applying it.

Extra parameters cannot override prompts, transport, authentication, response
schemas, truncation, or the dedicated token fields. Unknown keys and invalid
types/ranges are rejected. Leave the object empty to use existing defaults.
These values are public configuration; credentials belong in Authentication.
Saved limits and parameters are versioned with the model. Chat/extraction use
them on the next run; queued work retains its submitted values. Embedding edits
require applying the dataset mapping and reindexing.

Set limits within the deployed model's actual capacity. The UI's validation
ceiling is not a claim of model support. Larger limits can consume more memory,
time, or cloud credits. Provider request formats follow the official
[Ollama chat](https://docs.ollama.com/api/chat),
[Ollama embeddings](https://docs.ollama.com/api/embed),
[Bedrock inference configuration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InferenceConfiguration.html),
[Vertex inference](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference), and
[OCI chat](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/generative_ai_inference/models/oci.generative_ai_inference.models.GenericChatRequest.html)
documentation.

## Connection protocols

| Protocol | Endpoint and model | Authentication | Model roles |
| --- | --- | --- | --- |
| Ollama | `http://127.0.0.1:11434` or `:11435`; installed model name | No credentials | Embedding, chat, extraction |
| OpenAI-compatible API | HTTPS base URL, typically ending in `/v1`; model ID | API key or bearer token | `/embeddings` and `/chat/completions` |
| Azure OpenAI v1 | `https://RESOURCE.openai.azure.com/openai/v1`; deployment name | API key or bearer token | Embedding, chat, extraction |
| Amazon Bedrock | `https://bedrock-runtime.REGION.amazonaws.com`; model ID or supported inference profile | Access key/secret with optional session token, or server identity | Converse generation; Titan or Cohere v3/v4 embeddings |
| Google Vertex AI | `https://LOCATION-aiplatform.googleapis.com`, or global endpoint; Google publisher model ID, project, location | Service account JSON, server identity, or bearer token | GenerateContent generation; Predict embeddings |
| OCI Generative AI | `https://inference.generativeai.REGION.oci.oraclecloud.com`; model ID or dedicated endpoint OCID, compartment | Signing credentials, resource principal, or server config profile | Generic/Cohere chat; EmbedText embeddings |

The selected model must support the role and request format. This is a supported
protocol interface, not automatic detection of arbitrary APIs or model families.
OpenAI-compatible extraction can request native JSON-schema output or use
JSON-only prompting; both paths validate the result. Bedrock and OCI request
formats must match the chosen model. Optional embedding dimensions must be
supported by that model. Bearer and temporary session tokens need replacement
when they expire; server identity uses the SDK's configured identity chain.

Remote endpoints require HTTPS on port 443, a service hostname, and no embedded
credentials, query parameters, or fragment. Known service hosts are accepted.
Custom compatible gateway hostnames require the administrator's
`AEGIS_MODEL_ENDPOINT_HOSTS` comma-separated allowlist. Remote HTTP redirects and
environment proxies are disabled. Native SDK errors are returned without raw
provider response bodies or credential values.

## Applying changes

- Chat and extraction use the latest saved registration on the next run. A global
  profile activation or application restart is unnecessary.
- A queued operation retains its submitted model, connection, and credential
  version, even if a registration changes later.
- Editing an embedding registration blocks new use of its previous pinned
  mapping. Apply the updated mapping, acknowledge reindexing when documents
  exist, and reindex them. Originals remain stored. Credentials-only embedding
  edits also create a new index generation.
- All three enabled role selections are required before new document processing,
  chat, or extraction. A stale mapping save is rejected rather than overwriting
  a newer dataset revision. Unsaved choices survive a workspace refresh.
- Registered direct embedding connections require Local or Qdrant vector storage.
  The legacy OCI managed retrieval service owns its embedding configuration and
  cannot silently substitute for a registered embedding model.

Changing an endpoint, protocol, or authentication method requires new credentials;
saved credentials do not follow a new destination implicitly. With the same
destination, leaving all credential fields empty retains the saved bundle. A new
nonempty bundle replaces it. Disabling a registration allows explicitly clearing
its credentials. Disabled mappings block new work; queued work remains pinned.

## Deployment

The existing `AEGIS_LOCAL_ONLY=true` setting is honored. Cloud connections may be
registered for later use, but cannot be tested, mapped, or executed while this
policy is active. The local workspace is not automatically opened to cloud use.
An administrator must deliberately configure a deployment permitting external
processing; users still acknowledge external requests before content is sent.

Native AWS, GCP, and OCI adapters need the optional SDKs on **both API and worker**:

```sh
python -m pip install -r backend/requirements-models.txt -c backend/requirements.lock
```

Compose installs them by default using `INSTALL_CLOUD_MODELS=true`. A minimal
deployment can set this build argument false. OpenAI-compatible/Azure HTTP and
Ollama do not require these SDKs. The cloud account still needs region availability,
model access, quotas, network access, and the necessary identity permissions.
Changing model settings uses the next run; installing dependencies or changing
deployment policy requires restarting the affected service once.

The model registration routes are `POST /api/model-registrations`,
`PUT /api/model-registrations/{id}`, and `POST /api/model-registrations/test`.
The existing `GET /api/models` returns safe registration details. Dataset mapping
uses `PUT /api/datasets/{id}/models` with the three defaults, enabled mappings,
`expected_version`, and `acknowledge_reindex` when appropriate.

## Validation boundary

Contract tests cover all five remote protocols in all three roles using mocked
network/SDK responses, plus secret storage, ownership, local-only policy, next-run
changes, pinned queued operations, and embedding reindexing. Local Ollama is
tested live through the application. Real cloud account credentials were not
supplied, so a live cloud model must pass Test Connection in its deployment before
use. SDK dependency resolution is checked separately; that is not a Docker image
build or a cloud deployment test.
