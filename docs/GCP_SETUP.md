# Google Gemini API keys for Aegis

Use the managed `gemini-3.5-flash-lite` model for a small document QA and extraction test. No GPU, dedicated model server, training job, or provisioned throughput is required. Google hosts the base model; Aegis supplies evidence and instructions on each request.

## Recommended free-tier test: AI Studio

1. Open Google AI Studio → API Keys and choose a project whose Billing Tier is **Free**. A Gemini app or Google One subscription does not determine API billing.
2. Create a dedicated key such as **Aegis Small Gemini Test** and restrict it to the Generative Language API. Leave billing disabled for the free-tier test. Use `gemini-3.5-flash-lite`, subject to the project's current free quota.
3. After deploying this change, select **Google · Gemini** in Aegis Connections → Providers, then **Gemini API · AI Studio free tier available**. Enter the API key, select `gemini-3.5-flash-lite`, save settings, and save a named connection profile. No Cloud project ID, ADC login, or service-account JSON key is required for this route.
4. Register **Aegis Small Gemini** with chat and extraction capabilities, then map it to your dataset. Keep the existing local embedding mapping.
5. Test with a short synthetic TXT document and a small JSON extraction template. Free-tier prompts and responses may be used to improve Google products; choose sample data. Free quotas vary by model and account.

This route calls `generativelanguage.googleapis.com`. It does **not** consume the Google Cloud $300 welcome credit. The default API mode for new Google connections is the Developer API.

## Optional Google Cloud route

1. Use a billing-enabled Google Cloud project and enable the Agent Platform (Vertex AI) API.
2. Open Agent Studio and select `gemini-3.5-flash-lite`, location `global`. For a small synthetic smoke test, set minimal thinking, disable web grounding/tools, and cap output at 512 tokens.
3. Create a Google Cloud API key authorized for Agent Platform in that project. Restrict the key to the Agent Platform API and grant only the access needed for model requests. An ordinary AI Studio/Gemini Developer API key is a different connection and cannot replace a Google Cloud authorization key here. Some projects disallow authorized Cloud keys; leave their policy in place and use the Developer API route above for API-key-only testing.
4. Keep the key private. Enter it through Aegis Connections after deploying this change; do not commit it or embed it in browser code. This adapter uses an API key only.

Use the project ID shown in your Google Cloud project selector. Do not paste payment credentials or personal documents into a test prompt.

## Aegis

1. In Connections → Providers choose **Google · Gemini**, then **Google Cloud · eligible trial credits**.
2. Set the project ID, location `global`, model `gemini-3.5-flash-lite`, and Google Cloud API key. Defaults cap chat output at 512 tokens and extraction at 2048 tokens. Save settings, then save a named connection profile such as **Aegis GCP Small**.
3. Register **Aegis Small Gemini** using that profile and provider identifier `gemini-3.5-flash-lite`, with chat and extraction capabilities.
4. Keep local Sentence Transformers as the separate embedding model. Map the generation and embedding models to the dataset, choosing the new Gemini model as chat/extraction default. When adding only a generation mapping to an existing dataset, preserve its existing embedding mapping so a new index is not needed.
5. Upload a short synthetic TXT document, wait until it is ready, approve Google Cloud processing, and ask a question. Then try a small JSON extraction template and inspect citations and evidence.

Google Cloud keys are encrypted on the server and snapshotted into versioned connection profiles. Queued runs keep their original project, location, output limits, and credential references. Configuration exports omit credentials. Endpoints are fixed Google hosts, redirects are disabled, and test generation input is limited to 256 KiB. Requests that exceed the output limit, are blocked, or end without completion fail instead of being marked successful. Extraction JSON is validated locally against the submitted schema.

## Credits and limits

Managed Google Cloud model requests consume eligible Cloud credits or incur token charges. The separate AI Studio Gemini Developer API is excluded from the Google Cloud welcome credit; this adapter uses the Google Cloud Agent Platform endpoint. Verify eligible SKUs and trial balance in Billing. Stay in the trial account while testing; do not activate full pay-as-you-go, provision GPUs, or reserve throughput for this setup. A budget alert is a notification, not a hard spending cap.

The settings diagnostic checks whether a key is present; it does not authenticate to Google or request inference. Credential-free tests verify both API modes, native requests, streaming, extraction, consent, encrypted profiles, and immutable routing. A live Aegis test requires deployment of this change and a key for the chosen API. The saved Agent Studio prompt is a separate Cloud-side smoke test; Aegis sends its own evidence and instructions.

Sources: [Gemini API billing and free tier](https://ai.google.dev/gemini-api/docs/billing), [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing), [Gemini Flash-Lite](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash-lite), [Cloud API keys](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start/api-keys), [trial restrictions](https://docs.cloud.google.com/free/docs/free-cloud-features).
