"""Unified, rebuildable semantic index. SQL/files remain authoritative.

No conversation text, credentials or arbitrary configuration bodies enter this
index. Every hit is reconstructed from its current authorized canonical source.
"""
import copy
import hashlib
import json
import re
import time
import uuid
from sqlalchemy import select
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from . import core, dataset_models as routing, dataset_access as access, providers

TYPES = {'dataset', 'document', 'document_chunk', 'extraction', 'prompt', 'model', 'workflow', 'application'}
KINDS = {'knowledge_base', 'document', 'extraction', 'template', 'model', 'agent_plan', 'agent_onboarding'}
SCHEMA_VERSION = 1
PUBLICATION_VERSION = 3
TEXT_BYTES = 2400
GUIDE = {
    'cloud_sources': 'Any signed-in user can choose Dashboard > Add new knowledge to connect Amazon S3, SharePoint, Google Drive, Azure Blob Storage or OCI Object Storage to a dataset they can access. Each connection belongs to the user who saved it; administrators can see all connections. Connections use read-only AWS access keys or server IAM identity, a Microsoft Entra application, a Google service-account JSON key shared onto the selected Drive folder, an Azure container SAS token limited to read and list, or an OCI customer secret key for the S3-compatible endpoint. Test the connection, browse the configured folder or prefix, select up to 20 supported files and choose Vectorize after confirming that authorized dataset users may read the copies and allowing any external processing. Vectorize indexes copies with the dataset embedding model; they become usable in Agent and Dataset Knowledge Chat only after indexing succeeds. Extraction and review stay separate. Google Docs export as DOCX and Sheets/Slides as PDF. PDF, DOCX, TXT and JSON are supported. Imports are snapshots: source ACLs, deletes and updates are not automatically synchronized, disabled connections do not remove copies, and changed content creates another retained copy. Credentials never enter chat. Scheduled sync and delegated user sign-in are unavailable.',
    'datasets': 'Create a dataset with a name, optional description and embedding, chat and extraction model mappings in New dataset. Mapped defaults are preselected. Dataset onboarding alone does not upload documents, save a prompt or run extraction. Aegis Agent can collect these separately when explicitly requested. Dataset access governs shared documents and results.',
    'documents': 'Upload PDF, DOCX, TXT or JSON documents to a selected dataset. Originals remain in their configured persistent file storage. Parsing or configured OCR creates text chunks; the mapped embedding model publishes searchable knowledge. A ready indexed document does not mean field extraction has run. A prompt JSON file belongs to Prompt templates, not the document upload input.',
    'extraction': 'Select the dataset, documents, saved prompt and mapped extraction model, then confirm extraction. Aegis retrieves and reranks evidence, extracts fields, validates JSON Schema and saves versioned JSON and Parquet results. Re-extract uses saved documents and a selected prompt while preserving earlier results. A question about extraction does not authorize running it.',
    'review': 'Review filters saved runs by dataset, prompt template and extraction. Open a run to compare extracted fields with its unchanged source document side by side. Reload retrieves saved values; Download exports saved results. Reviewed saves checked values and permanently locks that extraction. Re-extract is available from the Review list and creates a separate result. Citations show recorded evidence; missing source locations are never guessed.',
    'models': 'Model Registration defines embedding, chat and extraction profiles under Manage workspace. Assign models while creating a dataset; mapped defaults are selected automatically. LangGraph orchestrates agents. Chat and extraction profiles may use the same weights with different limits. Actual endpoints, limits and availability come from configured model metadata, not assumptions in this guide.',
    'storage': 'Storage manages file storage, database and vector destinations and required connection settings. The Connections footer identifies Local or OCI for Storage, Database, Vector DB, FastAPI, WebApp, Worker and AI models. Existing deployments can use OCI files and Oracle vectors while AI models remain on a laptop through a private relay. Read configured destinations to report actual placement. Credentials are encrypted and must never appear in chat or the knowledge index.',
    'knowledge': 'Aegis Agent can explain Aegis, help onboard datasets and map models, upload and index documents, work with prompt templates, extract or re-extract fields, summarize or search saved knowledge, compare results, inspect Review and export saved results. Every chat question uses access-scoped hybrid vector and keyword retrieval, then CPU reranking, then a model answer and citation validation. Aegis help uses indexed application guidance; document and result questions retain dataset and document filters. Exact counts and complete lists use complete authorized published catalog facts in addition to ranked evidence. Previous chat text is not indexed knowledge. No web search or implicit processing is available.',
    'recovery': 'Confirmed processing jobs persist beyond the browser. Retry resumes accepted processing; restart repeats the confirmed workflow while preserving originals and earlier results. Chat questions do not start processing. Upload and extraction workflows require their existing confirmation. Laptop-hosted AI requires the laptop and relay to stay online; connection failures produce recoverable errors without switching to paid models.',
}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def fragments(text):
    # Split without breaking UTF-8 and without losing the tail of long fields.
    current = []; size = 0
    for char in text:
        length = len(char.encode())
        if size + length > TEXT_BYTES:
            yield ''.join(current); current = []; size = 0
        current.append(char); size += length
    if current: yield ''.join(current)


def payload_metadata(value):
    """Preserve exact audit/OCR metadata through vector backends' JSON codecs.

    Qdrant may round floating-point payload numbers during a JSON round trip.
    Business values remain numeric in the canonical JSON text, which assemble()
    decodes. Only auxiliary metadata floats use lossless decimal strings.
    """
    if isinstance(value,float):return repr(value)
    if isinstance(value,dict):return {key:payload_metadata(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [payload_metadata(item) for item in value]
    return value


def point(source_type, entity_id, dataset_id, owner, title, text, version=1, **extra):
    pieces=list(fragments(text))
    for part, excerpt in enumerate(pieces):
        payload = dict(source_type=source_type, entity_id=entity_id, dataset_id=dataset_id or '',
            owner_id=owner, title=title, text=excerpt, source_version=version, part=part, part_count=len(pieces), **payload_metadata(extra))
        payload['content_digest'] = digest(payload)
        id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'aegis-knowledge:{source_type}:{entity_id}:{version}:{part}'))
        yield {'id': id, 'payload': payload}


def application_sources():
    return [p for topic, text in GUIDE.items() for p in point('application', topic, '', '', 'Aegis · '+topic, text)]

def call_extraction_ids(call):
    result=call.get('result',{})
    return [e['extraction_id'] for e in result.get('extractions',[]) if not e.get('superseded')] or ([result['extraction_id']] if result.get('extraction_id') else [])


def record_sources(record):
    """Explicit allowlisted fields, never a generic dump of stored artifacts."""
    if record.kind not in KINDS: return []
    title = record.name or record.id; base = dict(status=record.status,source_updated_at=record.updated_at)
    if record.kind == 'model':
        data = routing.model_public(record)
        if data.get('archived') or not data.get('enabled', True): return []
        fields = {k: data.get(k) for k in ('name', 'provider_model', 'provider', 'capabilities', 'context_limit', 'max_output_tokens', 'timeout', 'enabled')}
        return list(point('model', record.id, '', record.owner, title, encoded(fields), record.version, **base))
    data = {} if record.kind=='document' else core.store.json(record.ref)
    dataset_id = record.id if record.kind == 'knowledge_base' else record.parent_id or ''
    if record.kind == 'knowledge_base':
        fields = {'name': title, 'description': data.get('description', ''), 'active': data.get('active', True),
            'embedding_model_id': data.get('embedding_model_id'), 'chat_model_id': data.get('default_chat_model_id'),
            'extraction_model_id': data.get('default_extraction_model_id')}
        return list(point('dataset', record.id, dataset_id, record.owner, title, encoded(fields), record.version, **base))
    if record.kind == 'document':
        output = list(point('document', record.id, dataset_id, record.owner, title,
            encoded({'filename': title, 'size': record.size, 'status': record.status, 'version': record.version}), record.version, document_ids=[record.id], **base))
        if record.status == 'ready':
            try: chunks = core.store.json('documents/'+record.id+'/chunks.json')['chunks']
            except FileNotFoundError: chunks = []
            for chunk in chunks:
                # Existing immutable chunk ID distinguishes pages within a document.
                output.extend(point('document_chunk', record.id+':'+chunk['id'], dataset_id, record.owner, title,
                    chunk['text'], record.version, document_ids=[record.id], document_id=record.id,
                    chunk_id=chunk['id'], page=chunk.get('page'), ocr=chunk.get('ocr'), **base))
        return output
    if record.kind == 'template':
        fields = {'filename': data.get('source_filename') or title, 'schema': data.get('schema', {}), 'instructions': data.get('instruction') or data.get('instructions', '')}
        return list(point('prompt', record.id, dataset_id, record.owner, title, encoded(fields), record.version, **base))
    if record.kind == 'agent_onboarding':
        fields={'name':data['name'],'status':data['status'],'dataset_id':data.get('dataset_id'),
            'steps':[{'label':s['label'],'status':s['status']} for s in data['steps']],
            'document_ids':data.get('document_ids',[]),'extraction_ids':data.get('extraction_ids',[]),
            'prompt_id':data.get('template_id'),'models':data.get('models',{})}
        return list(point('workflow',record.id,data.get('dataset_id',''),record.owner,title,encoded(fields),record.version,private=True,**base))
    if record.kind == 'agent_plan':
        if not data.get('calls'): return []
        fields = {'workflow_id': record.id, 'document_ids':data.get('document_ids',[]),'steps': [{'tool': c.get('tool'), 'status': c.get('status'), 'error': c.get('error','')[:300],
            'extraction_ids':call_extraction_ids(c)} for c in data.get('calls', [])],
            'goal_status': data.get('goal', {}).get('status')}
        return list(point('workflow', record.id, dataset_id or data.get('dataset_id', ''), record.owner, title,
            encoded(fields), record.version, private=True, **base))
    if record.kind == 'extraction':
        from .parquet_results import load
        documents = data.get('document_ids', [])
        extra = dict(document_ids=documents, merged_document_id=(data.get('merge') or {}).get('document_id'),review_status=data.get('review_status', 'unreviewed'), **base)
        output = list(point('extraction', record.id, dataset_id, record.owner, title,
            encoded({'extraction_id': record.id, 'name': title, 'status': record.status, 'review_status': extra['review_status']}), record.version, record_index=-1, **extra))
        if record.status != 'ready': return output
        result = load(data).get('result')
        items = result.get('records', []) if isinstance(result, dict) and isinstance(result.get('records'), list) else [{'fields': result}]
        for index, item in enumerate(items):
            fields = item.get('fields', item) if isinstance(item, dict) else item
            # Each result record is separately discoverable; complete exact values
            # remain in Parquet and are read by read_extraction_results.
            output.extend(point('extraction', record.id+':record:'+str(index), dataset_id, record.owner, title,
                encoded({'source_filename': item.get('source_filename') if isinstance(item, dict) else None, 'fields': fields}), record.version,
                extraction_id=record.id, record_index=index, **extra))
        return output
    return []


def eligible(actor, dataset_id='', document_ids=None):
    if dataset_id: access.get_record(dataset_id, actor, 'knowledge_base')
    selected = set(document_ids or [])
    for id in selected:
        doc = access.get_record(id, actor, 'document')
        if not dataset_id or doc.parent_id != dataset_id: raise HTTPException(400, 'Selected document is outside the selected dataset.')
    with core.Session() as session:
        datasets = access.dataset_ids(actor, session)
        records = session.scalars(select(core.Record).where(core.Record.kind.in_(KINDS))).all()
        result = []
        for record in records:
            if not access.allowed(record, actor, session, datasets): continue
            if record.kind=='agent_plan':
                if record.status=='query':continue
                saved=core.store.json(record.ref)
                status='workflow' if saved.get('calls') else 'query'
                if record.status!=status:
                    with core.Session.begin() as update_session:update_session.get(core.Record,record.id).status=status
                    record.status=status
                if status=='query':continue
            scope = record.id if record.kind == 'knowledge_base' else record.parent_id
            if record.kind in ('agent_plan','agent_onboarding') and not scope:
                scope=core.store.json(record.ref).get('dataset_id','')
                if scope in datasets:
                    with core.Session.begin() as update_session:update_session.get(core.Record,record.id).parent_id=scope
                    record.parent_id=scope
            if dataset_id and record.kind != 'model' and scope not in ('', dataset_id): continue
            if selected and record.kind == 'document' and record.id not in selected: continue
            if selected and record.kind == 'extraction':
                data = core.store.json(record.ref)
                if not set(data.get('document_ids', [])) <= selected: continue
            result.append(record)
    return result


def embedding_snapshot(actor, dataset_id=''):
    candidates = [routing.owned(dataset_id, actor, 'knowledge_base')] if dataset_id else routing.rows(actor, 'knowledge_base')
    for dataset in candidates:
        try: snapshot = routing.embedding_snapshot(dataset)
        except HTTPException: continue
        cfg = copy.deepcopy(snapshot['settings'])
        if cfg['embedding_provider'] not in ('ollama', 'mock', 'sentence_transformers', 'openai', 'registered') or cfg['search_provider'] not in ('qdrant', 'oracle', 'local'): continue
        # One compatible embedding space across dataset-specific index namespaces.
        cfg['_index_namespace'] = 'unified-knowledge-v1'
        cfg['embedding_extra_parameters'] = {k:v for k,v in cfg.get('embedding_extra_parameters', {}).items() if k != 'truncate'}
        snapshot = dict(snapshot, settings=cfg)
        signature = digest({'schema': SCHEMA_VERSION, 'embedding': providers.fingerprint(cfg)})[:20]
        snapshot['knowledge_collection'] = 'aegis_knowledge_'+signature
        return snapshot
    raise HTTPException(409, 'Map an embedding model with Local, Qdrant, or Oracle vector storage to an accessible dataset before using unified semantic search.')


def _manifest_ref(snapshot): return 'knowledge/'+snapshot['knowledge_collection']+'/manifest.json'

def entity_stamp(record):
    return digest([PUBLICATION_VERSION,record.kind,record.name,record.status,record.version,record.ref,record.updated_at,record.size])


def sync(actor, dataset_id='', max_points=None, application_only=False):
    """Durable digest ledger; retries repeat deterministic IDs, not new records."""
    from .workspace_reset import paused
    if paused():raise HTTPException(503,'Workspace archive operation is running.')
    snapshot = embedding_snapshot(actor, dataset_id)
    name = snapshot['knowledge_collection']; ref = _manifest_ref(snapshot)
    records = [] if application_only else eligible(actor, dataset_id)
    with core.document_lock('unified-knowledge-'+name):
        if paused():raise HTTPException(503,'Workspace archive operation is running.')
        try: manifest = core.local_store.json(ref)
        except FileNotFoundError: manifest = {'entities': {}, 'points': {}, 'vectors': {}}
        entities = manifest['entities']; points = manifest['points']; pending = []; alive = set(); failures = []
        for record in records:
            key = record.id; alive.add(key)
            stamp = entity_stamp(record)
            # Live plan/goal phases are persisted outside SQL between leases.
            # Their public summaries must participate in change detection.
            if record.kind=='agent_plan': stamp=digest([PUBLICATION_VERSION,record_sources(record)])
            if entities.get(key, {}).get('stamp') == stamp: continue
            try: sources = record_sources(record)
            except (FileNotFoundError, ValueError, KeyError):
                failures.append(key); continue
            pending.append((key, stamp, sources))
        app_stamp = digest([PUBLICATION_VERSION,GUIDE])
        if entities.get('application', {}).get('stamp') != app_stamp: pending.append(('application', app_stamp, application_sources()))
        upserted = 0; removed = []
        with core.execution_context(snapshot):
            q = providers.client() if snapshot['settings']['search_provider'] in ('qdrant','oracle') else None
            if q and not q.collection_exists(name):
                probe = providers.embed(['Aegis unified knowledge.'])[0]
                from qdrant_client.models import VectorParams, Distance, PayloadSchemaType
                q.create_collection(name, vectors_config=VectorParams(size=len(probe), distance=Distance.COSINE))
                for field in ('dataset_id', 'source_type', 'owner_id', 'entity_id'):
                    q.create_payload_index(name, field, PayloadSchemaType.KEYWORD, wait=True)
            for key, stamp, sources in pending:
                if max_points is not None and upserted and upserted+len(sources)>max_points: break
                for start in range(0, len(sources), 24):
                    batch = sources[start:start+24]
                    vectors = providers.embed([p['payload']['text'] for p in batch])
                    if len(vectors) != len(batch): raise providers.ProviderError('Unified embedding batch returned an incomplete result.')
                    if q:
                        from qdrant_client.models import PointStruct
                        q.upsert(name, [PointStruct(id=p['id'], vector=v, payload=p['payload']) for p,v in zip(batch,vectors)], wait=True)
                    else:
                        manifest.setdefault('vectors', {}).update({p['id']:v for p,v in zip(batch,vectors)})
                old = entities.get(key, {}).get('ids', [])
                ids = [p['id'] for p in sources]
                removed.extend(id for id in old if id not in ids)
                for p in sources: points[p['id']] = p['payload']
                current_record=next((r for r in records if r.id==key),None)
                entities[key] = {'stamp': stamp, 'ids': ids,'revision_stamp':entity_stamp(current_record) if current_record else None}; upserted += len(sources)
            # Purge deleted or newly inaccessible records only inside this actor's
            # scope. Another user's entries must never be removed by a query.
            for key, entity in ([] if application_only else list(entities.items())):
                if key == 'application' or key in alive: continue
                with core.Session() as session: current = session.get(core.Record, key)
                if current is None:
                    removed.extend(entity['ids']); del entities[key]
            if removed:
                if q:
                    from qdrant_client.models import PointIdsList
                    q.delete(name, PointIdsList(points=removed), wait=True)
                for id in removed: points.pop(id, None); manifest.get('vectors', {}).pop(id, None)
        manifest.update(updated_at=time.time(), failures=failures)
        core.local_store.put_json(ref, manifest)
    return snapshot, {'collection': name, 'upserted': upserted, 'removed': len(removed), 'failed_entities': len(failures), 'points': len(points)}


def hydrate(actor, id, payload):
    kind = payload.get('source_type'); entity = payload.get('entity_id', '')
    if kind not in TYPES: return None
    if kind == 'application': sources = application_sources()
    else:
        record_id = entity.split(':', 1)[0]
        try: record = access.get_record(record_id, actor)
        except HTTPException: return None
        try: sources = record_sources(record)
        except (FileNotFoundError, ValueError, KeyError): return None
    source = next((p for p in sources if p['id'] == id), None)
    if not source or source['payload']['content_digest'] != payload.get('content_digest'): return None
    value = dict(source['payload'], knowledge_id=id)
    # Excerpts always come from reconstructed canonical content, never payload text.
    value['source_url'] = '/api/knowledge/sources/'+id
    return value


def search(query, actor, dataset_id='', document_ids=None, source_types=None, limit=5):
    if not query.strip(): raise HTTPException(400, 'Enter a semantic search question.')
    source_types = set(source_types or TYPES)
    if source_types-TYPES: raise HTTPException(400, 'Unknown knowledge source type.')
    records = eligible(actor, dataset_id, document_ids)
    snapshot, indexing = sync(actor, dataset_id)
    manifest = core.local_store.json(_manifest_ref(snapshot))
    permitted_ids = {r.id for r in records}
    ids = [id for id,p in manifest['points'].items() if p['source_type'] in source_types and
        (p['source_type']=='application' or p['entity_id'].split(':',1)[0] in permitted_ids)]
    if not ids: return {'matches': [], 'count': 0, 'index': indexing}
    with core.execution_context(snapshot):
        vector = providers.embed([query], query=True)[0]
        if snapshot['settings']['search_provider'] in ('qdrant','oracle'):
            from qdrant_client.models import Filter, HasIdCondition
            q = providers.client()
            hits = q.query_points(snapshot['knowledge_collection'], query=vector,
                query_filter=Filter(must=[HasIdCondition(has_id=ids)]), limit=min(100, limit*5)).points
            hits = [(str(p.id), p.payload, p.score) for p in hits]
        else:
            hits = [(id,manifest['points'][id],sum(a*b for a,b in zip(vector,manifest['vectors'][id]))) for id in ids]
            hits = sorted(hits,key=lambda p:p[2],reverse=True)[:limit*5]
    matches = []
    for id, payload, score in hits:
        source = hydrate(actor, id, payload)
        if source:
            source.update(knowledge_collection=snapshot['knowledge_collection'],source_url=source['source_url']+'?collection='+snapshot['knowledge_collection'])
            matches.append(dict(source, score=score))
            if len(matches) >= limit: break
    return {'matches': matches, 'count': len(matches), 'index': indexing,
        'complete_catalog': False, 'note': 'Semantic matches discover relevant sources; exact counts, complete lists and live status require authoritative reads.'}


def reconcile():
    """Worker background sync; optional search failure cannot fail document jobs."""
    with core.Session() as session: users = session.scalars(select(core.User)).all()
    for user in users:
        token = access.request_actor.set(user.id)
        try:
            # Publish each dataset through its own mapped embedding provider.
            # A cloud mapping must not send another dataset's document text to
            # that provider merely because it is first in the actor's catalog.
            for dataset in routing.rows(user.id, 'knowledge_base'):
                try: sync(user.id, dataset.id, max_points=256)
                except Exception: pass  # A failed provider cannot block other datasets.
        except Exception: pass  # No provider bodies/secrets in background logs.
        finally: access.request_actor.reset(token)


class SearchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=2000)
    dataset_id: str = ''
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    source_types: list[str] = Field(default_factory=list, max_length=8)
    limit: int = Field(default=5, ge=1, le=12)


def install(app, auth):
    @app.get('/api/knowledge/published-sources/{id}')
    def published_source(id:str,collection:str='',dataset_id:str='',actor=Depends(auth)):
        from .chat_knowledge import PublishedKnowledge,assemble
        if collection and not re.fullmatch(r'aegis_knowledge_[0-9a-f]{20}',collection):raise HTTPException(400,'Invalid knowledge collection.')
        view=PublishedKnowledge(actor,dataset_id)
        if collection and collection!=view.snapshot['knowledge_collection']:raise HTTPException(409,'The embedding configuration changed. Query the current knowledge index again.')
        payload=view.manifest['points'].get(id)
        if not payload:raise HTTPException(404,'Published knowledge source is unavailable.')
        root=payload['entity_id'].split(':',1)[0]
        ids=view.candidate_ids([payload['source_type']],{root})
        if id not in ids:raise HTTPException(404,'Source access removed.')
        values=assemble(view.fetch([key for key in ids if view.manifest['points'][key]['entity_id']==payload['entity_id']]))
        return values[0]

    @app.post('/api/knowledge/search')
    def query(body: SearchInput, actor=Depends(auth)):
        return search(body.text, actor, body.dataset_id, body.document_ids, body.source_types, body.limit)

    @app.get('/api/knowledge/sources/{id}')
    def source(id: str, collection: str='', actor=Depends(auth)):
        if collection and not re.fullmatch(r'aegis_knowledge_[0-9a-f]{20}',collection): raise HTTPException(400,'Invalid knowledge collection.')
        name=collection or embedding_snapshot(actor)['knowledge_collection']
        try: payload = core.local_store.json('knowledge/'+name+'/manifest.json')['points'].get(id)
        except FileNotFoundError: payload = None
        value = hydrate(actor, id, payload) if payload else None
        if not value: raise HTTPException(404, 'Knowledge source is unavailable, changed, or access was removed.')
        return value
