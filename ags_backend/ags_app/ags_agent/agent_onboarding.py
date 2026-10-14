"""Confirmed, durable dataset onboarding through upload and extraction."""
import copy
import time
import uuid
import hashlib
import io
import asyncio
from typing import Literal
from fastapi import Depends, HTTPException, File, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from .. import core, dataset_models as routing, dataset_access as access


class DocumentManifest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)
    size: int = Field(gt=0)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class Processing(BaseModel):
    model_config = ConfigDict(extra='forbid')
    documents: list[DocumentManifest] = Field(min_length=1, max_length=20)
    prompt_name: str = Field(min_length=1, max_length=200, pattern=r'(?i)^[^/\\\x00-\x1f\x7f]+\.json$')
    schema_: dict = Field(alias='schema')
    instructions: str = Field(default='', max_length=12000)
    extraction_mode: Literal['merge', 'independent'] = 'independent'
    merge_strategy: Literal['records', 'single'] = 'records'
    allow_external: bool = False


class Setup(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=10000)
    embedding_model_id: str
    default_chat_model_id: str
    default_extraction_model_id: str
    plan_id: str = ''
    processing: Processing | None = None


ROLES = [('embedding', 'embedding_model_id'), ('chat', 'default_chat_model_id'),
         ('extraction', 'default_extraction_model_id')]
LABELS = ['Validate setup', 'Create dataset', 'Map models', 'Publish knowledge', 'Ready for documents']
FULL_LABELS = LABELS[:3] + ['Save prompt', 'Upload documents', 'Index documents', 'Extract fields', 'Publish knowledge', 'Ready for review']

class AdvanceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    retry: bool = False

def persist(record, data):
    core.store.put_json(record.ref, data)
    with core.Session.begin() as session:
        current=session.get(core.Record,record.id)
        current.status=data['status'];current.updated_at=time.time()
        current.error='knowledge_publication_pending' if data.get('publication_pending') else ''
        if data.get('dataset_id'):current.parent_id=data['dataset_id']

def publish_knowledge(data,owner):
    """Completion requires canonical result files and acknowledged vectors."""
    from .. import knowledge, providers, parquet_results
    required=[data['dataset_id']]+data.get('document_ids',[])+data.get('extraction_ids',[])
    dataset=routing.dataset_public(routing.owned(data['dataset_id'],owner,'knowledge_base'))
    required.extend(dataset[key] for _,key in ROLES if dataset.get(key))
    required=list(dict.fromkeys(required))
    if data.get('template_id'):required.append(data['template_id'])
    outputs=[];artifacts=[]
    for id in data.get('extraction_ids',[]):
        record=routing.owned(id,owner,'extraction');saved=core.store.json(record.ref)
        reference=saved.get('output_reference')
        if record.status!='ready' or not reference or not reference.endswith('.parquet'):
            raise HTTPException(409,'A complete saved Parquet result is required before publishing knowledge.')
        parquet_results.load(saved)
        outputs.append(reference)
        from ..storage_config import route
        destination=route(reference)
        artifacts.append({'extraction_id':id,'version':record.version,'reference':reference,'sha256':saved['output_sha256'],
            'storage_provider':destination['storage_provider'],
            'bucket':destination.get('oci_storage_bucket','') if destination['storage_provider']=='oci' else ''})
    snapshot,receipt=knowledge.sync(owner,data['dataset_id'])
    manifest=core.local_store.json(knowledge._manifest_ref(snapshot))
    ids=[]
    for id in required:
        record=access.get_record(id,owner)
        expected=knowledge.record_sources(record)
        if not expected or any(point['id'] not in manifest['points'] or
            manifest['points'][point['id']]['content_digest']!=point['payload']['content_digest'] for point in expected):
            raise HTTPException(503,'Knowledge publication is incomplete. Retry to publish the saved results; completed files are preserved.')
        ids.extend(point['id'] for point in expected)
    ids=list(dict.fromkeys(ids));provider=snapshot['settings']['search_provider']
    with core.execution_context(snapshot):
        if provider in ('oracle','qdrant'):
            from qdrant_client.models import Filter,HasIdCondition
            count=providers.client().count(snapshot['knowledge_collection'],count_filter=Filter(must=[HasIdCondition(has_id=ids)]),exact=True).count
        else:count=sum(id in manifest.get('vectors',{}) for id in ids)
    if count!=len(ids):raise HTTPException(503,'Saved files are ready, but vector verification failed. Retry knowledge publication.')
    if provider in ('oracle','qdrant'):
        with core.execution_context(snapshot):
            client=providers.client();offset=None;seen=set()
            while True:
                page,offset=client.scroll(snapshot['knowledge_collection'],scroll_filter=Filter(must=[HasIdCondition(has_id=ids)]),
                    offset=offset,limit=256,with_payload=True,with_vectors=False)
                for point in page:
                    key=str(point.id);payload=point.payload
                    expected=manifest['points'].get(key)
                    if not expected or payload.get('content_digest')!=expected['content_digest'] or knowledge.digest({k:v for k,v in payload.items() if k!='content_digest'})!=expected['content_digest']:
                        raise HTTPException(503,'Published vector contents do not match the saved results. Retry knowledge publication.')
                    seen.add(key)
                if offset is None:break
            if seen!=set(ids):raise HTTPException(503,'Published vector records are incomplete. Retry knowledge publication.')
    data['vector_publication']={'provider':provider,'collection':snapshot['knowledge_collection'],
        'verified_vectors':count,'entity_ids':required,'parquet_files':outputs,'verified_artifacts':artifacts,'verified_at':time.time(),
        'upserted':receipt['upserted']}


def validate_setup(owner, data):
    if not data['name'].strip():
        raise HTTPException(422, 'Enter a dataset name.')
    versions = {}
    for role, key in ROLES:
        model = routing.owned(data[key], owner, 'model')
        public = routing.model_public(model)
        if not public['enabled'] or role not in public['capabilities']:
            raise HTTPException(422, f'Choose an enabled {role} model with that capability.')
        if not public['credential_configured']:
            raise HTTPException(422, f'Configure credentials for {public["name"]} in Model Registration first.')
        profile = routing.profile_snapshot(routing.owned(public['connection_profile_id'], model.owner, 'config_profile'), public.get('connection_profile_version'))
        cfg = profile['settings']
        if role == 'embedding' and cfg.get('embedding_connection') and cfg['search_provider'] == 'oci':
            raise HTTPException(422, 'This embedding connection requires Local or Qdrant vector storage.')
        try:
            core.enforce_local_only(cfg)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        versions[key] = {'id': model.id, 'name': model.name, 'version': model.version,
                         'connection_profile_version': profile['connection_profile_version']}
    return versions


def public(record):
    data=core.store.json(record.ref)
    if data.get('publication_pending'):
        data['status']='running';data['steps'][-1]['status']='running'
    return {'id': record.id, **data}


def publish_receipt(record, data, owner, completed=False):
    if not data.get('plan_id'):
        return
    with core.document_lock('agent-' + data['plan_id']):
        plan = routing.owned(data['plan_id'], owner, 'agent_plan'); value = core.store.json(plan.ref)
        if not value.get('onboarding'):
            raise HTTPException(409, 'This chat does not contain a dataset onboarding proposal.')
        value['onboarding_workflow_id'] = record.id
        if completed:
            names = ', '.join(role.title() + ': ' + data['models'][key]['name'] for role, key in ROLES)
            text = f'Dataset "{data["name"]}" is created with its model mappings saved ({names}). It is ready for documents and prompt templates.'
            if data.get('processing'):
                text = f'Dataset "{data["name"]}" is onboarded with its model mappings, {len(data["document_ids"])} documents and prompt "{data["processing"]["prompt_name"]}". All {len(data["extraction_ids"])} extraction results are ready for review.'
            value['explanation'] = text
            if value.get('conversation_id'):
                with core.document_lock('agent-turn-' + value['conversation_id']):
                    thread = routing.owned(value['conversation_id'], owner, 'conversation'); chat = core.store.json(thread.ref)
                    messages = chat.get('messages', [])
                    for i, message in enumerate(messages):
                        if message['id'] == value.get('reply_user_id'):
                            reply = next((m for m in messages[i+1:] if m['role'] == 'assistant'), None)
                            if reply:
                                reply.update(text=text, onboarding_workflow_id=record.id)
                            break
                    core.store.put_json(thread.ref, chat)
        core.store.put_json(plan.ref, value)


def create_dataset(record, data, owner):
    # A stable ID makes recovery safe even after process death between the
    # dataset commit and the workflow receipt. Never create a second dataset.
    id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'aegis:onboarding:dataset:' + record.id))
    with core.Session() as session:
        existing = session.get(core.Record, id)
    if existing:
        return routing.owned(id, owner, 'knowledge_base')
    ref = f'knowledge_base/{id}/v1.json'
    value = {'name': data['name'], 'description': data['description'], 'active': True,
             **copy.deepcopy(routing.ROUTING_DEFAULTS), 'routing_version': 1, 'onboarding_id': record.id}
    core.store.put_json(ref, value)
    with core.Session.begin() as session:
        dataset = core.Record(id=id, owner=owner, kind='knowledge_base', name=data['name'], ref=ref,
                              parent_id='', version=1, created_at=time.time(), updated_at=time.time())
        session.add(dataset)
    return dataset


def install(app, auth):
    from .. import main
    @app.get('/api/agent-v2/onboarding')
    def history(owner=Depends(auth)):
        access.require_admin(owner)
        return [public(r) for r in routing.rows(owner, 'agent_onboarding')][:20]

    @app.get('/api/agent-v2/onboarding/{id}')
    def read(id: str, owner=Depends(auth)):
        access.require_admin(owner)
        return public(routing.owned(id, owner, 'agent_onboarding'))

    @app.post('/api/agent-v2/onboarding')
    def prepare(body: Setup, owner=Depends(auth)):
        access.require_admin(owner)
        values = body.model_dump(mode='json', by_alias=True); values['name'] = values['name'].strip()
        if body.plan_id:
            plan = routing.owned(body.plan_id, owner, 'agent_plan')
            if not core.store.json(plan.ref).get('onboarding'):
                raise HTTPException(409, 'Choose a chat with a dataset onboarding proposal.')
        id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'aegis:onboarding:' + owner + ':' + str(body.request_id)))
        with core.document_lock('onboarding-' + id):
            with core.Session() as session:
                existing = session.get(core.Record, id)
            if existing:
                existing = routing.owned(id, owner, 'agent_onboarding')
                saved = core.store.json(existing.ref)
                if any(saved.get(k, '' if k == 'plan_id' else None) != v for k, v in values.items()):
                    raise HTTPException(409, 'This onboarding request already has different confirmed details.')
                publish_receipt(existing, saved, owner)
                return public(existing)
            models = validate_setup(owner, values)
            if body.processing:
                main.check_schema(body.processing.schema_)
                for role, key in ROLES:
                    if role != 'chat':
                        model = routing.owned(values[key], owner, 'model')
                        model_data = routing.model_public(model)
                        profile = routing.profile_snapshot(routing.owned(model_data['connection_profile_id'], model.owner, 'config_profile'), model_data.get('connection_profile_version'))
                        main.external_check(body.processing.allow_external, role == 'embedding', profile['settings'])
                limit = core.settings()['max_upload_mb'] * 1024 * 1024
                if any(d.size > limit or '/' in d.name or '\\' in d.name or d.name.rsplit('.', 1)[-1].lower() not in ('txt','pdf','docx','json') for d in body.processing.documents):
                    raise HTTPException(422, 'Choose supported PDF, DOCX, TXT or JSON documents within the upload limit.')
            data = {**values, 'agent':'onboard_extract','workflow_version':2,'models': models, 'dataset_id': '', 'status': 'pending', 'confirmed_at': time.time(),
                    'steps': [{'id': str(i), 'label': label, 'status': 'pending'} for i, label in enumerate(FULL_LABELS if body.processing else LABELS)]}
            ref = f'agent_onboarding/{id}/v1.json'; core.store.put_json(ref, data)
            with core.Session.begin() as session:
                record = core.Record(id=id, owner=owner, kind='agent_onboarding', name=values['name'], ref=ref,
                                     parent_id='', version=1, status='pending',created_at=time.time(), updated_at=time.time())
                session.add(record)
            publish_receipt(record, data, owner)
            return public(record)

    @app.post('/api/agent-v2/onboarding/{id}/files')
    async def stage_files(id: str, files: list[UploadFile] = File(...), owner=Depends(auth)):
        access.require_admin(owner)
        with core.document_lock('onboarding-' + id):
            record = routing.owned(id, owner, 'agent_onboarding'); data = core.store.json(record.ref)
            processing = data.get('processing')
            if not processing:
                raise HTTPException(409, 'This setup does not include document processing.')
            expected = processing['documents']
            if len(files) != len(expected):
                raise HTTPException(422, 'Reattach all of the confirmed documents.')
            accepted = []
            for file, manifest in zip(files, expected):
                raw = await file.read(core.settings()['max_upload_mb'] * 1024 * 1024 + 1)
                if file.filename != manifest['name'] or len(raw) != manifest['size'] or hashlib.sha256(raw).hexdigest() != manifest['sha256']:
                    raise HTTPException(409, 'Document contents differ from the confirmed setup. Reattach the original files.')
                if file.filename.lower().endswith('.txt'):
                    try: raw.decode('utf-8-sig')
                    except UnicodeDecodeError: raise HTTPException(422, 'TXT must use UTF-8 encoding.')
                if file.filename.lower().endswith('.json'):
                    try: main.json_document_text(raw)
                    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
                accepted.append(raw)
            for i, raw in enumerate(accepted):
                core.store.put(f'agent_onboarding/{id}/files/{i}', raw)
            data['files_saved'] = True; core.store.put_json(record.ref, data)
            return public(record)

    @app.post('/api/agent-v2/onboarding/{id}/advance')
    async def advance(id: str, body: AdvanceInput = AdvanceInput(), owner=Depends(auth)):
        return await advance_workflow(id, owner, body.retry)


async def advance_workflow(id: str, owner: str, retry=False):
    from .. import main
    access.require_admin(owner)
    with core.document_lock('onboarding-' + id):
        record = routing.owned(id, owner, 'agent_onboarding'); data = core.store.json(record.ref)
        if data['status'] == 'completed':
            if data.get('publication_pending'):finish_publication(record,data,owner)
            return public(record)
        if data['status'] == 'failed' and not retry:return public(record)
        if data['status'] == 'failed':
            # Retry the whole setup and verify committed steps again.
            # Deterministic dataset ID and identical mapping check reuse them.
            for step in data['steps']:
                step.update(status='pending'); step.pop('error', None)
                step.pop('started_at', None); step.pop('finished_at', None)
            data['retry_count'] = data.get('retry_count', 0) + 1
        index = next(i for i, s in enumerate(data['steps']) if s['status'] != 'completed')
        step = data['steps'][index]; step['status'] = 'running'; step.setdefault('started_at', time.time())
        data['status'] = 'running'; data.pop('error', None); persist(record, data)
        try:
            if index in (0, 1, 2):
                current = validate_setup(owner, data)
                if current != data['models']:
                    raise HTTPException(409, 'A selected model changed. Restore its confirmed version or start a new onboarding setup with the updated model.')
            if index == 1:
                data['dataset_id'] = create_dataset(record, data, owner).id
            if index == 2:
                with core.document_lock('dataset-' + data['dataset_id']):
                    dataset = routing.owned(data['dataset_id'], owner, 'knowledge_base')
                    saved = routing.routing_public(dataset)
                    if not (saved['models_complete'] and all(saved[k] == data[k] for _, k in ROLES)):
                        body = routing.MappingInput(mappings=[{'model_id': mid, 'enabled': True} for mid in dict.fromkeys(data[k] for _, k in ROLES)],
                            **{k: data[k] for _, k in ROLES}, expected_version=1)
                        routing.save_mappings(dataset, body)
            if index == 3 and not data.get('processing'):
                publish_knowledge(data,owner)
            if not data.get('processing') and index==len(data['steps'])-1:
                dataset = routing.dataset_public(routing.owned(data['dataset_id'], owner, 'knowledge_base'))
                if not dataset['active'] or not dataset['models_complete'] or any(dataset[k] != data[k] for _, k in ROLES):
                    raise HTTPException(409, 'Dataset configuration changed. Review its model mappings before continuing.')
                data['dataset'] = dataset
            if data.get('processing') and index >= 3:
                waiting = await process_stage(record, data, index, owner, main)
                if waiting:
                    data['status'] = 'waiting'; persist(record, data)
                    return public(record)
            step.update(status='completed', finished_at=time.time())
            data['status'] = 'completed' if index == len(data['steps']) - 1 else 'pending'
        except Exception as exc:
            detail = str(exc.detail) if isinstance(exc, HTTPException) else 'Dataset setup could not finish. Retry to resume from the saved setup.'
            step.update(status='failed', error=detail, finished_at=time.time())
            data.update(status='failed', error=detail)
        if data['status']=='completed':data['publication_pending']=True
        persist(record, data)
        if data['status']=='completed':
            finish_publication(record,data,owner)
        return public(record)


def finish_publication(record,data,owner):
    try:
        from .. import knowledge
        knowledge.sync(owner,data['dataset_id'])
        publish_receipt(record,data,owner,completed=True)
        data.pop('publication_pending',None)
        core.store.put_json(record.ref,data)
        # Clearing the internal recovery marker is not indexed content.
        with core.Session.begin() as session:session.get(core.Record,record.id).error=''
    except Exception:
        data.pop('publication_pending',None)
        data.update(status='failed',error='Saved results are preserved. Retry to finish publishing workflow knowledge.')
        data['steps'][-1].update(status='failed',error=data['error'])
        persist(record,data)

def run_pending():
    """Continue only confirmed workflows, independent of browser polling."""
    from sqlalchemy import select,or_
    from .. import relational
    with core.Session() as session:
        records=list(session.scalars(select(core.Record).where(core.Record.kind=='agent_onboarding',
            or_(core.Record.status.in_(['pending','waiting','running','ready']),core.Record.error=='knowledge_publication_pending')).order_by(core.Record.created_at).limit(8)))
    for record in records:
        data=core.store.json(record.ref)
        if data['status'] in ('completed','failed') and not data.get('publication_pending'):
            if record.status!=data['status']:persist(record,data)
            continue
        if not data.get('confirmed_at') or data.get('processing') and not data.get('files_saved'):continue
        with core.Session() as session:
            user=session.get(core.User,record.owner)
            # Synthetic internal fixtures have no HTTP account. They retain
            # their explicit test driver; real workflows require a live admin.
            if user is None:continue
            permitted=user.role=='administrator'
            if data['status']=='waiting':
                ids=data.get('extraction_ids') or data.get('document_ids',[])
                rows=list(session.scalars(select(core.Record).where(core.Record.id.in_(ids))))
                if len(rows)!=len(ids) or any(r.status not in ('ready','failed','cancelled') for r in rows):continue
        if not permitted:
            with core.document_lock('onboarding-'+record.id):
                data=core.store.json(record.ref)
                if data['status'] in ('completed','failed'):continue
                data.pop('publication_pending',None)
                data.update(status='failed',error='Administrator access changed. Restore authorized access before retrying.')
                next((s for s in data['steps'] if s['status']!='completed'),data['steps'][-1]).update(status='failed',error=data['error'])
                persist(record,data)
            return True
        actor=access.request_actor.set(record.owner);audit=relational.actor_override.set(record.owner)
        try:asyncio.run(advance_workflow(record.id,record.owner))
        finally:relational.actor_override.reset(audit);access.request_actor.reset(actor)
        return True
    return False

async def process_stage(record, data, index, owner, main):
    """Reuse the normal upload/index/extraction pipeline and its durable receipts."""
    cfg = data['processing']; retry = data.get('retry_count', 0)
    dataset = routing.dataset_public(routing.owned(data['dataset_id'], owner, 'knowledge_base'))
    if not dataset['active'] or any(dataset[key] != data[key] for _, key in ROLES) or validate_setup(owner, data) != data['models']:
        raise HTTPException(409, 'Dataset or model configuration changed after confirmation. Restore the confirmed configuration before resuming.')
    if index >= 4:
        prompt = core.store.json(routing.owned(data['template_id'], owner, 'template').ref)
        if prompt['schema'] != cfg['schema'] or prompt.get('instructions', '') != cfg['instructions']:
            raise HTTPException(409, 'The saved prompt changed after confirmation. Restore the confirmed prompt before resuming.')
    if index == 3:
        body = main.TemplateInput(name=cfg['prompt_name'], source_filename=cfg['prompt_name'], dataset_id=data['dataset_id'], schema=cfg['schema'], instructions=cfg['instructions'])
        previous = main.uploaded_template(body, owner)
        if previous:
            saved = core.store.json(previous.ref)
            if saved['schema'] != cfg['schema'] or saved.get('instructions', '') != cfg['instructions']:
                raise HTTPException(409, 'The saved prompt changed. Restore the confirmed prompt before retrying.')
            data['template_id'] = previous.id
        else:
            data['template_id'] = main.create_template(body, owner)['id']
    if index == 4:
        if not data.get('files_saved'):
            raise HTTPException(422, 'Reattach the confirmed documents to resume this onboarding workflow.')
        files = [UploadFile(filename=d['name'], file=io.BytesIO(core.store.get(f'agent_onboarding/{record.id}/files/{i}'))) for i, d in enumerate(cfg['documents'])]
        result = await main.upload(files=files, dataset_id=data['dataset_id'], kb_id='', allow_external=cfg['allow_external'], temporary_session_id='', owner=owner, merge_files=False, template_id='', display_name='', idempotency_key='onboarding-' + record.id, merge_records=False)
        data['document_ids'] = [d['id'] for d in result['documents']]
        data['upload_jobs'] = [j['id'] for j in result['jobs']]
    if index == 5:
        documents = [routing.owned(id, owner, 'document') for id in data['document_ids']]
        snapshot = routing.execution_snapshot(routing.owned(data['dataset_id'], owner, 'knowledge_base'), 'extraction')
        for doc in documents:
            if doc.status in ('failed', 'cancelled') or doc.status == 'ready' and not routing.index_matches(doc, snapshot):
                if data.get('retried_targets', {}).get(doc.id, 0) >= retry:
                    raise HTTPException(409, doc.error or 'Document indexing failed or configuration changed. Retry the workflow to reindex.')
                main.reindex(doc.id, main.Consent(allow_external=cfg['allow_external']), owner)
                data.setdefault('retried_targets', {})[doc.id] = retry
                core.store.put_json(record.ref, data)
                return True
        if any(d.status != 'ready' for d in documents): return True
        routing.require_indexes(documents, snapshot)
    if index == 6:
        ids = data['document_ids']; groups = [[id] for id in ids] if cfg['extraction_mode'] == 'independent' else [ids]
        data.setdefault('extraction_ids', [])
        for group in groups:
            result = main.create_extraction(main.ExtractInput(dataset_id=data['dataset_id'], document_ids=group, template_id=data['template_id'], allow_external=cfg['allow_external'], merge_records=cfg['extraction_mode']=='merge' and cfg['merge_strategy']=='records', idempotency_key='onboard-extract-' + record.id + '-' + hashlib.sha256(','.join(group).encode()).hexdigest()), owner)
            if result['id'] not in data['extraction_ids']:
                data['extraction_ids'].append(result['id']); core.store.put_json(record.ref, data)
        results = [routing.owned(id, owner, 'extraction') for id in data['extraction_ids']]
        data['results'] = [{'id': r.id, 'name': r.name, 'status': 'completed'} for r in results if r.status == 'ready']
        for result in results:
            if result.status in ('failed', 'cancelled'):
                if data.get('retried_targets', {}).get(result.id, 0) >= retry:
                    raise HTTPException(409, result.error or 'Extraction failed. Retry the workflow to resume the failed result.')
                if result.status == 'cancelled':
                    from sqlalchemy import select
                    with core.Session() as session:
                        job = session.scalar(select(core.Job).where(core.Job.target_id == result.id).order_by(core.Job.created_at.desc()))
                    main.retry_job(job.id, owner)
                else:
                    main.resume_extraction(result.id, main.ResumeExtraction(version=result.version, template_id=data['template_id'], allow_external=cfg['allow_external']), owner)
                data.setdefault('retried_targets', {})[result.id] = retry; core.store.put_json(record.ref, data)
                return True
        if any(r.status != 'ready' for r in results): return True
    if index == 7:
        publish_knowledge(data,owner)
    if index == len(data['steps'])-1:
        data['dataset'] = routing.dataset_public(routing.owned(data['dataset_id'], owner, 'knowledge_base'))
    return False
