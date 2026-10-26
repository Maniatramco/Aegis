"""Learning notes alongside the live FastAPI contract; never read workspace data."""
import json
from fastapi import Depends, Response
from fastapi.routing import APIRoute

# Keyed by method and path so similar operations cannot share misleading notes.
NOTES = {
    'GET /api/source-connections': 'Signed-in users with dataset access (own connections; administrators see all): list authorized dataset source connections and credential-configured flags without returning secret values. Imported copies follow Aegis dataset access; source permissions are not mirrored.',
    'POST /api/source-connections/test': 'Signed-in users with dataset access (own connections; administrators see all): test read access to a proposed scoped S3, SharePoint, Google Drive, Azure Blob or OCI Object Storage location without saving configuration, importing files or writing to the cloud source.',
    'POST /api/source-connections': 'Signed-in users with dataset access (own connections; administrators see all): save a dataset source connection with encrypted versioned credentials. Saving does not import files or synchronize source permissions, updates or deletions.',
    'PUT /api/source-connections/{identifier}': 'Signed-in users with dataset access (own connections; administrators see all): update an authorized source connection and its credential version. Changed locations require credentials again; disabling a connection preserves previously imported copies.',
    'GET /api/source-connections/{identifier}/files': 'Signed-in users with dataset access (own connections; administrators see all): browse an enabled scoped source location with expiring actor/dataset/connection-bound selection and pagination capabilities. No files are imported.',
    'POST /api/source-connections/{identifier}/import': 'Signed-in users with dataset access (own connections; administrators see all): explicitly publish selected source copies to an authorized dataset through the existing upload/index pipeline, with dataset-sharing acknowledgement and any required external-processing consent. Preserve provenance and completed duplicate submissions; inspect per-file failures. Remote files and permissions are not changed or synchronized.',
    'POST /api/source-connections/{identifier}/publish': 'Signed-in users with dataset access (own connections; administrators see all): publish the unified knowledge of the connection dataset after imported copies finish indexing, with any required external-processing consent, and report which selected documents are now available to chat. No cloud access or new imports.',
    'GET /api/dataset-chat/catalog': 'Read the authorized dataset, document, prompt and model catalog for Dashboard Dataset Knowledge Chat without starting a conversation or inference.',
    'GET /api/dataset-chat/conversations': 'List the signed-in user\'s separate Dashboard chat history, omitting conversations whose saved dataset/document scope is no longer accessible.',
    'GET /api/dataset-chat/conversations/{id}': 'Read an owned Dashboard conversation and its saved messages after rechecking access to its dataset and document scope.',
    'POST /api/dataset-chat/messages': 'Answer in the separate Dashboard chat using the selected mapped Chat model and persist its scoped history. Self-contained general questions skip knowledge lookup; dataset, private, mixed and uncertain questions use scoped retrieval, reranking and citation validation. Original Agent processing workflows are unchanged.',
    'POST /api/dataset-chat/reply': 'Stream the separate Dashboard chat response and actual workflow events as server-sent events, with the same scope, model routing and saved-history checks as the non-streaming messages route. Read the terminal done or error event; HTTP 200 alone does not prove an answer completed.',
    'GET /api/runtime-config': 'Administrator only: read validated operational settings and explicit overrides without credentials; this does not apply configuration changes.',
    'GET /api/dataset-trash': 'Administrator only: list recoverably deleted datasets and their retained archive information.',
    'DELETE /api/datasets/{id}': 'Administrator only: recoverably delete a dataset after confirmation while retaining its archived content for restoration.',
    'POST /api/dataset-trash/{id}/restore': 'Administrator only: restore a recoverably deleted dataset and its retained content after confirmation.',
    'POST /api/extractions/{id}/rerun': 'Prepare a confirmed, idempotent re-extraction using authorized saved documents and a selected prompt; rebuild stale indexes before creating a separate result and preserve prior versions.',
    'DELETE /api/users/{user_id}': 'Administrator only: confirm the acting password and exact target username, revoke sessions and dataset access, archive private history references and preserve shared content. The current account and last administrator are protected.',
    'GET /api/agent-v2/goals': 'Read the current user\'s authorized persistent agent requests and recovery status.',
    'GET /api/agent-v2/onboarding': 'List authorized dataset onboarding workflows.',
    'GET /api/agent-v2/onboarding/{id}': 'Read an authorized onboarding workflow and its saved input requirements.',
    'GET /api/documents/{id}/page-image': 'Read an authorized rendered source page for evidence comparison.',
    'GET /api/extract-data': 'Read authorized saved extraction records as rows for one dataset and prompt template.',
    'GET /api/extract-data/export': 'Export authorized saved extraction rows for one dataset and prompt template.',
    'GET /api/extractions/{id}/source-evidence': 'Read authorized extraction evidence and original document/page references.',
    'GET /api/knowledge/published-sources/{id}': 'Read a published vector source after checking current dataset access and source freshness.',
    'GET /api/knowledge/sources/{id}': 'Resolve an authorized unified knowledge source for citation inspection.',
    'GET /api/storage': 'Administrator only: read file destination configuration without secret values.',
    'GET /api/storage/database': 'Administrator only: read database and knowledge destination configuration without secret values.',
    'GET /api/storage/status': 'Read the active file, database and knowledge destination summary.',
    'GET /api/workspace/reset-preview': 'Administrator only: inspect workspace reset scope and retained archive information.',
    'POST /api/agent-v2/consent': 'Describe external processing destinations required by the selected workflow; this does not execute it.',
    'POST /api/agent-v2/onboarding': 'Prepare a dataset onboarding workflow; required inputs and confirmation precede mutations.',
    'POST /api/agent-v2/onboarding/{id}/advance': 'Advance an authorized onboarding workflow using supplied inputs and explicit confirmation.',
    'POST /api/agent-v2/onboarding/{id}/files': 'Attach confirmed documents to an authorized onboarding workflow.',
    'POST /api/agent-v2/plans/{id}/goal': 'Continue or control an authorized persistent request after its workflow actions.',
    'POST /api/agent-v2/plans/{id}/knowledge/retry': 'Retry pending knowledge publication for an authorized completed workflow.',
    'POST /api/agent-v2/plans/{id}/restart': 'Restart a failed authorized workflow while preserving files and completed results.',
    'POST /api/extractions/{id}/resume': 'Resume an authorized interrupted extraction from its durable checkpoint.',
    'POST /api/knowledge/search': 'Search scoped unified knowledge with dataset authorization and freshness checks.',
    'POST /api/storage/database/activate': 'Administrator only: verify and migrate the current catalog and compatible vectors before activating a database destination.',
    'POST /api/storage/database/prepare': 'Administrator only: create missing application and native vector tables in the selected schema.',
    'POST /api/storage/database/test': 'Administrator only: test database connectivity and vector support without creating tables or activating the destination.',
    'POST /api/storage/test': 'Administrator only: test the proposed file destination without saving it.',
    'POST /api/workspace/archives/{id}/restore': 'Administrator only: restore a retained workspace archive with explicit confirmation.',
    'POST /api/workspace/reset': 'Administrator only: archive and reset workspace content with explicit confirmation while preserving operator configuration.',
    'PUT /api/storage': 'Administrator only: save a verified file destination; stored files retain their individually pinned routes.',
    'PUT /api/storage/database': 'Administrator only: save verified database configuration and encrypted credentials without activating it.',
    'GET /api/auth/status': 'Check whether the first administrator has been created before showing login or setup.',
    'POST /api/auth/setup': 'Create the first administrator with the deployment bootstrap token and a password of at least 12 characters. Setup is disabled once an administrator exists.',
    'POST /api/auth/login': 'Verify credentials, set the HTTP-only session cookie, and return the user and CSRF token. Login attempts are rate limited.',
    'GET /api/auth/me': 'Read the signed-in user and the CSRF token used for subsequent cookie-authenticated changes.',
    'POST /api/auth/logout': 'Invalidate the current session and clear its cookie.',
    'GET /api/users': 'Administrator only: list account identity and audit metadata. Password hashes are never returned.',
    'POST /api/users': 'Administrator only: create a user with matching passwords of 12–200 characters and a unique username. The account starts with no dataset assignments.',
    'POST /api/users/{user_id}/password': 'Administrator only: verify the administrator current password, reset another user password, and revoke all target sessions. Existing documents and results are preserved.',
    'PATCH /api/users/{user_id}/role': 'Administrator only: verify the acting administrator password, change role, revoke target sessions, preserve dataset assignments, and protect the last administrator.',
    'POST /api/auth/password': 'Change your own password after verifying your current password. Revoke all your sessions and sign in again. Cookie authentication requires X-CSRF-Token.',
    'GET /api/users/{user_id}/datasets': 'Administrator only: read the user dataset assignments and their audit metadata. The administrator has automatic access to every dataset.',
    'PUT /api/users/{user_id}/datasets': 'Administrator only: replace dataset assignments atomically. Assigned users can use shared documents, prompts and extraction results; revoked access blocks new reads and operations immediately. Empty assignments remove all dataset access. Existing content is preserved.',
    'POST /api/auth/recovery/prepare': 'Prepare a loopback-only native SQLite recovery challenge. A private legacy grant token is optional; direct desktop recovery uses the recovery cookie and CSRF challenge. The application API proxy blocks this route. Oracle and network deployments do not enable it.',
    'POST /api/auth/recovery/reset': 'Complete native SQLite desktop recovery with its recovery cookie, X-CSRF-Token, and matching new passwords; supply a token only for the legacy private-grant flow. Loopback and origin checks apply. Oracle and network deployments do not enable this route.',
    'GET /health': 'Basic process liveness check. A running API does not by itself prove that its dependencies are ready.',
    'GET /ready': 'Check the database, the vector service when configured, and the reranker when enabled. This is not a full model-inference test. Inspect the response before sending processing work.',
    'GET /api/metadata-relationships': 'Read access-scoped workflow lineage, exact category counts, saved prompt/model versions and paginated metadata records. No inference or indexing is started.',
    'GET /api/overview': 'Read workspace totals and recent activity for the dashboard.',
    'GET /api/knowledge-bases': 'List assigned datasets (administrator sees all) through the older knowledge-base route. New integrations should use /api/datasets.',
    'POST /api/knowledge-bases': 'Create a dataset through the older knowledge-base route. Register and map its models before processing documents.',
    'GET /api/datasets': 'List the signed-in userâ€™s datasets, their model mappings, and index-generation state.',
    'POST /api/datasets': 'Create a dataset. A new dataset has no automatic model mappings; configure Embedding, Chat, and Extraction explicitly.',
    'GET /api/datasets/{id}': 'Read one authorized dataset and its configuration.',
    'PATCH /api/datasets/{id}/status': 'Activate or deactivate a dataset. Inactive datasets cannot start new processing work.',
    'GET /api/datasets/{id}/models': 'Read the datasetâ€™s enabled model mappings and the selected models for its three roles.',
    'PUT /api/datasets/{id}/models': 'Save the three required roles: Embedding, Chat, and Extraction. The next operation uses these mappings. Changing embeddings creates a new index generation and requires acknowledgement when documents already exist.',
    'POST /api/datasets/{id}/migrate-settings': 'Explicitly import legacy deployment settings into an unmapped dataset. This convenience route cannot overwrite existing mappings.',
    'POST /api/datasets/{id}/assign-documents': 'Assign unassigned legacy documents to a dataset. Existing dataset documents cannot be moved; assigned documents need reindexing.',
    'POST /api/datasets/{id}/local-models': 'Map already-installed local Ollama models without downloading models. Existing embedding selections are preserved.',
    'GET /api/models': 'List registered models, capabilities, and public connection information. Credential values are not returned.',
    'GET /api/model-providers': 'List supported model provider choices, protocol, endpoint defaults, categories and authentication modes. No credential values are returned.',
    'POST /api/models': 'Register a model against an existing connection profile. For a complete generic connection registration, use /api/model-registrations.',
    'PUT /api/models/{id}': 'Update a catalog model against an existing profile. Dataset mappings validate its capabilities and enabled state.',
    'POST /api/model-registrations': 'Register a model together with protocol, endpoint, authentication, category, and timeout. Connection credentials are stored encrypted and omitted from public responses.',
    'PUT /api/model-registrations/{id}': 'Update a registered model and its versioned connection. Existing pinned processing runs retain their execution configuration.',
    'POST /api/model-registrations/test': 'Send a small synthetic probe using the same adapter as processing. This does not save the registration or transmit document content. Remote probes require consent and an enabled cloud deployment.',
    'GET /api/local-models': 'List models installed in the configured local Ollama service. This call does not install or download anything.',
    'GET /api/documents': 'List documents in assigned datasets, optionally scoped by dataset_id or the older kb_id parameter, with processing and reindex status.',
    'POST /api/documents/upload': 'Upload up to 20 PDF, DOCX, UTF-8 TXT, or JSON files using multipart form data: repeated files fields plus dataset_id. Per-file size uses max_upload_mb from deployment settings. Originals are stored, document records are created, and indexing jobs are queued. Upload acceptance is not indexing completion; follow /api/jobs.',
    'GET /api/admin/documents': 'Administrator only: paginate application source files with dataset/search filters, pinned storage presence, saved indexing/model mapping and OCR status, and related extraction runs. No model service probes; live validation remains on processing submissions. Does not expose unrelated bucket objects.',
    'GET /api/admin/documents/{id}/deletion-preview': 'Administrator only: inspect the affected extraction runs, chats/workflows and cleanup stage. Return a version and impact token for permanent deletion confirmation.',
    'DELETE /api/admin/documents/{id}': 'Administrator only: confirm exact filename, expected_version and expected_impact from deletion-preview. Block active dataset work; permanently clean up this document and related artifacts/results. Partial failures remain quarantined and deletion can resume. Retain content-free terminal queue audit rows.',
    'POST /api/admin/documents/{id}/retry': 'Administrator only: queue fresh indexing using current dataset embedding/OCR models, with explicit external transmission consent. Use the existing extraction rerun endpoint to create new structured results.',
    'GET /api/documents/{id}': 'Read document metadata, processing status, and dataset/index compatibility.',
    'GET /api/documents/{id}/preview': 'Read a JSON text preview containing text, chunks, and document metadata. Before processing finishes, the text explains that it is not available yet. Use /source to view supported original files.',
    'GET /api/documents/{id}/download': 'Download the original uploaded file with a download filename.',
    'GET /api/documents/{id}/source': 'Return an original PDF, UTF-8 TXT, or JSON file inline for source viewing. DOCX inline viewing is rejected with 415; download DOCX to inspect its original layout.',
    'GET /api/documents/{id}/merged-sources/{key}/{action}': 'Read or download an original source retained in an authorized merged document. The source key comes from its merge manifest; only supported source/download actions are accepted.',
    'POST /api/documents/{id}/reindex': 'Queue a new index build using the datasetâ€™s selected embedding configuration. Follow the returned job rather than assuming immediate readiness.',
    'POST /api/documents/{id}/reextract': 'Reprocess the original document into a new document version and index. This is source reprocessing, not template-based structured extraction; use /api/extractions for that.',
    'DELETE /api/documents/{id}': 'Cancel active document jobs and remove the original, parsed content, index files, and vectors. Vector cleanup must succeed before deletion finishes.',
    'POST /api/documents/{id}/keep': 'Promote a temporarily retained document to permanent retention.',
    'GET /api/conversations': 'List saved conversations owned by the current user.',
    'POST /api/conversations': 'Create a conversation scoped to a dataset and optional documents. A conversation with messages stays within its original dataset.',
    'GET /api/conversations/{id}': 'Read a saved conversation and its messages.',
    'POST /api/conversations/{id}/messages': 'Retrieve evidence using the datasetâ€™s embedding/index configuration, generate an answer using its Chat model, and persist messages with citations and model selection.',
    'POST /api/conversations/{id}/messages/stream': 'Stream a grounded answer as server-sent events. Read the event stream through its terminal event; HTTP 200 alone does not prove generation completed.',
    'GET /api/conversations/{id}/export': 'Download the stored conversation as JSON.',
    'POST /api/messages/{id}/feedback': 'Save up/down (or positive/negative) feedback on an owned conversation message.',
    'POST /api/temporary-chat/messages': 'Answer directly from one temporary document using an enabled registered Chat model. No dataset, embedding model, vector search, reranker, indexing job, saved conversation, or execution file is involved. Send document_id and model_id with optional recent history. External Chat models require explicit consent.',
    'POST /api/temporary-chat/documents': 'Read exactly one PDF, DOCX, or UTF-8 TXT document into bounded server memory. Repeated uploads with the same client session_id replace its previous document. Parsed text is limited to 40 KB, expires after one hour, and is never added to dataset records, embeddings, indexes, or jobs.',
    'GET /api/temporary-chat/documents/{id}': 'Read the owned temporary documentâ€™s text pages from server memory. Expired documents and documents cleared by a server restart must be uploaded again.',
    'DELETE /api/temporary-chat/documents/{id}': 'Discard the owned temporary document from server memory. No permanent dataset content is affected.',
    'POST /api/temporary-chat/sessions': 'Legacy file-retention session creation. This is separate from direct Temporary chat; new temporary uploads must use /api/temporary-chat/documents. Indexed uploads with temporary_session_id are rejected.',
    'DELETE /api/temporary-chat/sessions/{id}': 'Clean up files attached to a temporary session. Files used by saved conversations or extractions are preserved; inspect deleted, preserved, and pending document ids.',
    'GET /api/templates': 'List saved prompt templates and their strict JSON extraction schemas.',
    'POST /api/templates/validate': 'Validate an uploaded prompt JSON Schema and optional dataset access before the user confirms it. Returns the reviewed name and schema without saving a template or starting extraction.',
    'POST /api/templates': 'Create a template with an object JSON Schema. Every object must set additionalProperties:false and require every property; nullable fields represent optional values. Only local schema references are allowed.',
    'PUT /api/templates/{id}': 'Save a new template version. The dataset association cannot be changed on an existing template.',
    'GET /api/templates/{id}/versions': 'Read the saved versions of a template.',
    'GET /api/templates/{id}/export': 'Download a saved prompt template as portable JSON; uploaded templates use their original filename. The optional version selects an earlier saved schema.',
    'GET /api/agent-v2/catalog': 'Read assigned datasets, eligible models, documents and saved templates for Aegis Assistant.',
    'POST /api/agent-v2/plans': 'Plan a general or document question, or propose upload/extraction tools. Planning does not authorize document execution.',
    'GET /api/agent-v2/plans/{id}': 'Read an owned assistant plan, its saved conversation and the current tool progress.',
    'GET /api/agent-v2/plans/{id}/events': 'Stream changes to an owned assistant plan using server-sent events.',
    'POST /api/agent-v2/plans/{id}/reply': 'Stream an assistant answer for a plan without document tools, using its pinned model and document scope.',
    'POST /api/agent-v2/plans/{id}/calls/{index}': 'Execute the next confirmed extraction or re-extraction tool. Earlier tool results and source documents are preserved.',
    'POST /api/agent-v2/plans/{id}/calls/{index}/upload': 'Upload attached documents for the next confirmed upload tool, with explicit dataset scope and any required external-processing consent.',
    'POST /api/agent-v2/plans/{id}/calls/{index}/recover': 'Apply an explicit recovery choice to failed Assistant work. Inspect accepted uploads, retry failed indexing, continue with ready files, or retry extraction with current settings without duplicating completed results.',
    'GET /api/extractions': 'List structured extraction records and their review/model metadata.',
    'POST /api/extractions': 'Queue structured extraction for 1–20 ready documents from one dataset using a saved template and the mapped Extraction model. Returns the queued extraction with its job; poll before reading the final result.',
    'GET /api/extractions/{id}': 'Read an extraction, its current version, structured result, and saved source evidence when available.',
    'PATCH /api/extractions/{id}': 'Save a reviewed result that matches the template schema. Send the current version to prevent overwriting newer edits. Edited fields lose their verified evidence; original evidence is preserved.',
    'POST /api/extractions/{id}/reextract': 'Rerun a completed structured extraction using its saved template/schema. Send the current version and explicitly confirm replacement of reviewed edits; prior saved versions remain available.',
    'GET /api/extractions/{id}/versions': 'Read saved extraction versions, including earlier results and reviews.',
    'GET /api/extractions/{id}/export': 'Download a completed extraction in the requested format. Unsupported formats are rejected; incomplete extractions cannot be exported.',
    'GET /api/extractions/{id}/merged-file': 'Download the physical merged file for an authorized extraction that has a merged document. Original source files remain available and unchanged.',
    'GET /api/jobs': 'List jobs for authorized dataset resources with status, completed-stage progress, and workflow details. Jobs may be queued, running, completed, failed, or cancelled; percentages describe stages, not estimated remaining time.',
    'POST /api/jobs/{id}/retry': 'Requeue a failed or cancelled job if its target still exists, its dataset is active, and no other job is active for that target.',
    'POST /api/jobs/{id}/cancel': 'Cancel a queued or running job and invalidate its lease so late worker results cannot complete it.',
    'GET /api/index': 'Inspect authorized document chunks and index metadata, optionally scoped by document_id or dataset_id.',
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
    'GET /api/settings/profiles/{id}/export': 'Export a profileâ€™s name, version, and settings as JSON.',
    'GET /api/documentation': 'Read this live API contract and learning notes. No document data, user records, or configured credential values are included.',
    'GET /api/documentation/export': 'Download the current OpenAPI JSON contract for offline study or import into API tools. This export contains schemas, not workspace data or configured credentials.',
}

GROUPS = {
    'source-connections': 'Source connections',
    'auth': 'Authentication', 'datasets': 'Datasets', 'knowledge-bases': 'Datasets',
    'models': 'Models', 'model-registrations': 'Models', 'model-providers': 'Models', 'local-models': 'Models',
    'documents': 'Documents', 'conversations': 'Chat', 'messages': 'Chat',
    'temporary-chat': 'Temporary chat', 'dataset-chat': 'Dashboard knowledge chat', 'templates': 'Prompt templates',
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
    'GET /api/metadata-relationships': {'level':'overview','dataset_ids':['<dataset-id>'],'nodes':[{'id':'Dataset','type':'Dataset','label':'Dataset','count':1}],'edges':[],'totals':{'nodes':1,'edges':0,'categories':{'Dataset':1}}},
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
            required = ['password', 'confirmation'] if route.path.endswith('/reset') else []
            route.openapi_extra = {'requestBody': {'required': True, 'content': {
                'application/json': {'schema': {'type': 'object', 'properties': properties,
                                               'required': required}}}}}
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
    """Include separately declared routers on eager and lazy FastAPI versions."""
    seen = set()
    from .browser_recovery import router
    from .user_management import router as account_router
    for route in [*app.routes, *router.routes, *account_router.routes]:
        if isinstance(route, APIRoute) and (route.path, frozenset(route.methods)) not in seen:
            seen.add((route.path, frozenset(route.methods)))
            yield route
