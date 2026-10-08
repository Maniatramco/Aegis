"""Learning notes alongside the live FastAPI contract; never read workspace data."""
import json
from fastapi import Depends, Response
from fastapi.routing import APIRoute

# Keyed by method and path so similar operations cannot share misleading notes.
NOTES = {
    'GET /api/auth/status': 'Check whether the first administrator has been created before showing login or setup.',
    'POST /api/auth/setup': 'Create the first administrator with the deployment bootstrap token and a password of at least 12 characters. Setup is disabled once an administrator exists.',
    'POST /api/auth/login': 'Verify credentials, set the HTTP-only session cookie, and return the user and CSRF token. Login attempts are rate limited.',
    'GET /api/auth/me': 'Read the signed-in user and the CSRF token used for subsequent cookie-authenticated changes.',
    'POST /api/auth/logout': 'Invalidate the current session and clear its cookie.',
    'POST /api/auth/recovery/prepare': 'Prepare the loopback-only browser recovery challenge using a privately issued short-lived grant token. This is a local recovery flow, not a general remote password-reset API. The application API proxy blocks this route; use the private recovery page.',
    'POST /api/auth/recovery/reset': 'Complete local recovery using the prepared grant token, recovery cookie, X-CSRF-Token, and matching new passwords. Loopback and same-origin checks still apply. The application API proxy blocks this route.',
    'GET /health': 'Basic process liveness check. A running API does not by itself prove that its dependencies are ready.',
    'GET /ready': 'Check the database, the vector service when configured, and the reranker when enabled. This is not a full model-inference test. Inspect the response before sending processing work.',
    'GET /api/overview': 'Read workspace totals and recent activity for the dashboard.',
    'GET /api/knowledge-bases': 'List owned datasets through the older knowledge-base route. New integrations should use /api/datasets.',
    'POST /api/knowledge-bases': 'Create a dataset through the older knowledge-base route. Register and map its models before processing documents.',
    'GET /api/datasets': 'List the signed-in user’s datasets, their model mappings, and index-generation state.',
    'POST /api/datasets': 'Create a dataset. A new dataset has no automatic model mappings; configure Embedding, Chat, and Extraction explicitly.',
    'GET /api/datasets/{id}': 'Read one owned dataset and its configuration.',
    'PATCH /api/datasets/{id}/status': 'Activate or deactivate a dataset. Inactive datasets cannot start new processing work.',
    'GET /api/datasets/{id}/models': 'Read the dataset’s enabled model mappings and the selected models for its three roles.',
    'PUT /api/datasets/{id}/models': 'Save the three required roles: Embedding, Chat, and Extraction. The next operation uses these mappings. Changing embeddings creates a new index generation and requires acknowledgement when documents already exist.',
    'POST /api/datasets/{id}/migrate-settings': 'Explicitly import legacy deployment settings into an unmapped dataset. This convenience route cannot overwrite existing mappings.',
    'POST /api/datasets/{id}/assign-documents': 'Assign unassigned legacy documents to a dataset. Existing dataset documents cannot be moved; assigned documents need reindexing.',
    'POST /api/datasets/{id}/local-models': 'Map already-installed local Ollama models without downloading models. Existing embedding selections are preserved.',
    'GET /api/models': 'List registered models, capabilities, and public connection information. Credential values are not returned.',
    'POST /api/models': 'Register a model against an existing connection profile. For a complete generic connection registration, use /api/model-registrations.',
    'PUT /api/models/{id}': 'Update a catalog model against an existing profile. Dataset mappings validate its capabilities and enabled state.',
    'POST /api/model-registrations': 'Register a model together with protocol, endpoint, authentication, category, and timeout. Connection credentials are stored encrypted and omitted from public responses.',
    'PUT /api/model-registrations/{id}': 'Update a registered model and its versioned connection. Existing pinned processing runs retain their execution configuration.',
    'POST /api/model-registrations/test': 'Send a small synthetic probe using the same adapter as processing. This does not save the registration or transmit document content. Remote probes require consent and an enabled cloud deployment.',
    'GET /api/local-models': 'List models installed in the configured local Ollama service. This call does not install or download anything.',
    'GET /api/documents': 'List owned documents, optionally scoped by dataset_id or the older kb_id parameter, with processing and reindex status.',
    'POST /api/documents/upload': 'Upload up to 20 PDF, DOCX, or UTF-8 TXT files using multipart form data: repeated files fields plus dataset_id. Per-file size uses max_upload_mb from deployment settings. Originals are stored, document records are created, and indexing jobs are queued. Upload acceptance is not indexing completion; follow /api/jobs.',
    'GET /api/documents/{id}': 'Read document metadata, processing status, and dataset/index compatibility.',
    'GET /api/documents/{id}/preview': 'Read a JSON text preview containing text, chunks, and document metadata. Before processing finishes, the text explains that it is not available yet. Use /source to view supported original files.',
    'GET /api/documents/{id}/download': 'Download the original uploaded file with a download filename.',
    'GET /api/documents/{id}/source': 'Return an original PDF or UTF-8 TXT file inline for source viewing. DOCX inline viewing is rejected with 415; download DOCX to inspect its original layout.',
    'POST /api/documents/{id}/reindex': 'Queue a new index build using the dataset’s selected embedding configuration. Follow the returned job rather than assuming immediate readiness.',
    'POST /api/documents/{id}/reextract': 'Reprocess the original document into a new document version and index. This is source reprocessing, not template-based structured extraction; use /api/extractions for that.',
    'DELETE /api/documents/{id}': 'Cancel active document jobs and remove the original, parsed content, index files, and vectors. Vector cleanup must succeed before deletion finishes.',
    'POST /api/documents/{id}/keep': 'Promote a temporarily retained document to permanent retention.',
    'GET /api/conversations': 'List saved conversations owned by the current user.',
    'POST /api/conversations': 'Create a conversation scoped to a dataset and optional documents. A conversation with messages stays within its original dataset.',
    'GET /api/conversations/{id}': 'Read a saved conversation and its messages.',
    'POST /api/conversations/{id}/messages': 'Retrieve evidence using the dataset’s embedding/index configuration, generate an answer using its Chat model, and persist messages with citations and model selection.',
    'POST /api/conversations/{id}/messages/stream': 'Stream a grounded answer as server-sent events. Read the event stream through its terminal event; HTTP 200 alone does not prove generation completed.',
    'GET /api/conversations/{id}/export': 'Download the stored conversation as JSON.',
    'POST /api/messages/{id}/feedback': 'Save up/down (or positive/negative) feedback on an owned conversation message.',
    'POST /api/temporary-chat/messages': 'Answer with supplied temporary history without saving a conversation, messages, execution snapshot, or history. Uploaded temporary files have a separate retention lifecycle.',
    'POST /api/temporary-chat/sessions': 'Create a temporary file-retention session, returning its id, expiry, and retention_seconds (one hour).',
    'DELETE /api/temporary-chat/sessions/{id}': 'Clean up files attached to a temporary session. Files used by saved conversations or extractions are preserved; inspect deleted, preserved, and pending document ids.',
    'GET /api/templates': 'List saved prompt templates and their strict JSON extraction schemas.',
    'POST /api/templates': 'Create a template with an object JSON Schema. Every object must set additionalProperties:false and require every property; nullable fields represent optional values. Only local schema references are allowed.',
    'PUT /api/templates/{id}': 'Save a new template version. The dataset association cannot be changed on an existing template.',
    'GET /api/templates/{id}/versions': 'Read the saved versions of a template.',
    'GET /api/extractions': 'List structured extraction records and their review/model metadata.',
    'POST /api/extractions': 'Queue structured extraction for 1–20 ready documents from one dataset using a saved template and the mapped Extraction model. Returns the queued extraction with its job; poll before reading the final result.',
    'GET /api/extractions/{id}': 'Read an extraction, its current version, structured result, and saved source evidence when available.',
    'PATCH /api/extractions/{id}': 'Save a reviewed result that matches the template schema. Send the current version to prevent overwriting newer edits. Edited fields lose their verified evidence; original evidence is preserved.',
    'POST /api/extractions/{id}/reextract': 'Rerun a completed structured extraction using its saved template/schema. Send the current version and explicitly confirm replacement of reviewed edits; prior saved versions remain available.',
    'GET /api/extractions/{id}/versions': 'Read saved extraction versions, including earlier results and reviews.',
    'GET /api/extractions/{id}/export': 'Download a completed extraction in the requested format. Unsupported formats are rejected; incomplete extractions cannot be exported.',
    'GET /api/jobs': 'List owned jobs with status, completed-stage progress, and workflow details. Jobs may be queued, running, completed, failed, or cancelled; percentages describe stages, not estimated remaining time.',
    'POST /api/jobs/{id}/retry': 'Requeue a failed or cancelled job if its target still exists, its dataset is active, and no other job is active for that target.',
    'POST /api/jobs/{id}/cancel': 'Cancel a queued or running job and invalidate its lease so late worker results cannot complete it.',
    'GET /api/index': 'Inspect owned document chunks and index metadata, optionally scoped by document_id or dataset_id.',
    'POST /api/index/search': 'Diagnose retrieval in one dataset, including match scores, timing, scope, embedding fingerprint, and reranking diagnostics. Similarity scores are not probabilities.',
    'GET /api/settings': 'Read deployment settings and credential-configured flags. Actual stored credential values are not returned.',
    'PATCH /api/settings': 'Update supported deployment settings after validation. Active jobs/chats and existing storage data can prevent changes. Dataset model selection is managed through dataset mappings.',
    'GET /api/settings/export': 'Export deployment configuration as JSON.',
    'POST /api/settings/test': 'Check storage, database, vector service, and queue connectivity. This does not request model inference; key-presence checks are not live authentication checks. Inspect the per-service checks and note in the response.',
    'GET /api/capabilities': 'Read supported provider and deployment capabilities before configuring an integration.',
    'GET /api/settings/profiles': 'List saved configuration profiles with credential-configured flags.',
    'POST /api/settings/profiles': 'Snapshot current deployment settings into a versioned named profile.',
    'PUT /api/settings/profiles/{id}': 'Save a new profile version from current deployment settings. Model-registration profiles must be edited through Model Registration.',
    'POST /api/settings/profiles/{id}/activate': 'Activate a legacy deployment profile. Registered-model profiles are applied through dataset Model Mapping instead.',
    'GET /api/settings/profiles/{id}/export': 'Export a profile’s name, version, and settings as JSON.',
    'GET /api/documentation': 'Read this live API contract and learning notes. No document data, user records, or configured credential values are included.',
    'GET /api/documentation/export': 'Download the current OpenAPI JSON contract for offline study or import into API tools. This export contains schemas, not workspace data or configured credentials.',
}

GROUPS = {
    'auth': 'Authentication', 'datasets': 'Datasets', 'knowledge-bases': 'Datasets',
    'models': 'Models', 'model-registrations': 'Models', 'local-models': 'Models',
    'documents': 'Documents', 'conversations': 'Chat', 'messages': 'Chat',
    'temporary-chat': 'Temporary chat', 'templates': 'Prompt templates',
    'extractions': 'Extraction & review', 'jobs': 'Jobs & workflow',
    'index': 'Index & search', 'settings': 'Settings & connections',
    'overview': 'Workspace & services', 'capabilities': 'Workspace & services',
    'documentation': 'Workspace & services',
}
PUBLIC = {'GET /health', 'GET /ready', 'GET /api/auth/status', 'POST /api/auth/setup',
          'POST /api/auth/login', 'POST /api/auth/recovery/prepare', 'POST /api/auth/recovery/reset'}

# Illustrative, abridged envelopes from the handlers. Placeholders are never live data.
EXAMPLES = {
    'POST /api/auth/login': {'user': {'id': '<user-id>', 'username': 'your-username'}, 'csrf_token': '<csrf-token>'},
    'GET /health': {'status': 'ok'},
    'GET /api/overview': {'documents': 10, 'ready': 8, 'jobs': 2, 'knowledge_bases': 1, 'failed': 0},
    'POST /api/documents/upload': {'documents': [{'id': '<document-id>', 'name': 'invoice.pdf', 'status': 'queued'}], 'jobs': [{'id': '<job-id>', 'kind': 'index', 'target_id': '<document-id>', 'status': 'queued', 'progress': 0}]},
    'GET /api/documents/{id}/preview': {'text': 'Invoice total: 42', 'chunks': [], 'document': {'id': '<document-id>', 'name': 'invoice.pdf', 'status': 'ready'}},
    'POST /api/conversations/{id}/messages': {'message': {'id': '<message-id>', 'role': 'assistant', 'text': 'The invoice total is 42 [1].', 'citations': [{'index': 1, 'document_id': '<document-id>', 'text': 'Invoice total: 42', 'url': '/api/documents/<document-id>/preview'}]}, 'conversation_id': '<conversation-id>'},
    'POST /api/extractions': {'id': '<extraction-id>', 'status': 'queued', 'result': None, 'template_version': 1, 'job': {'id': '<job-id>', 'kind': 'extract', 'status': 'queued'}},
    'GET /api/extractions/{id}': {'id': '<extraction-id>', 'status': 'ready', 'version': 1, 'result': {'total': 42}, 'document_ids': ['<document-id>']},
    'GET /api/jobs': [{'id': '<job-id>', 'kind': 'index', 'status': 'completed', 'progress': 100, 'stage': 'Ready', 'error': None, 'target_id': '<document-id>'}],
}


def install(app, auth):
    @app.get('/api/documentation', summary='API documentation')
    def documentation(owner=Depends(auth)):
        return {'schema': app.openapi(), 'operations': operations(app)}

    @app.get('/api/documentation/export', summary='Export OpenAPI contract')
    def export_documentation(owner=Depends(auth)):
        return Response(json.dumps(app.openapi(), indent=2), media_type='application/json',
                        headers={'Content-Disposition': 'attachment; filename="aegis-openapi.json"'})

    # Enrich Swagger and the in-app reference from the same route catalog.
    for route in documented_routes(app):
        key = f'{sorted(route.methods)[0]} {route.path}'
        segment = route.path.removeprefix('/api/').split('/')[0]
        route.tags = [GROUPS.get(segment, 'Workspace & services')]
        if key in NOTES:
            route.description = NOTES[key]
        if '/auth/recovery/' in route.path:
            properties = {'token': {'type': 'string', 'minLength': 40, 'maxLength': 100,
                                    'description': 'Privately issued short-lived recovery grant.'}}
            if route.path.endswith('/reset'):
                properties.update(password={'type': 'string', 'minLength': 12, 'maxLength': 200},
                                  confirmation={'type': 'string', 'description': 'Must match password.'})
            route.openapi_extra = {'requestBody': {'required': True, 'content': {
                'application/json': {'schema': {'type': 'object', 'properties': properties,
                                               'required': list(properties)}}}}}
    app.openapi_schema = None


def operations(app):
    result = {}
    for route in documented_routes(app):
        if not route.include_in_schema:
            continue
        for method in route.methods:
            key = f'{method} {route.path}'
            result[key] = {
                'authentication': 'Local recovery challenge' if '/recovery/' in route.path else 'Public' if key in PUBLIC else 'Session or bearer token',
                'csrf_required': key not in PUBLIC and method not in {'GET', 'HEAD', 'OPTIONS'},
                'source': f'{route.endpoint.__module__.split(".")[-1]}.py · {route.endpoint.__name__}()',
                'curated': key in NOTES,
                **({'response_example': EXAMPLES[key]} if key in EXAMPLES else {}),
            }
    return result


def documented_routes(app):
    """Include the recovery router on both eager and lazy FastAPI versions."""
    seen = set()
    from .browser_recovery import router
    for route in [*app.routes, *router.routes]:
        if isinstance(route, APIRoute) and (route.path, frozenset(route.methods)) not in seen:
            seen.add((route.path, frozenset(route.methods)))
            yield route
