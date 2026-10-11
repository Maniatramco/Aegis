"""Dataset-scoped observations and proposals. Models cannot execute mutations.
Content and tool observations stay in external storage; SQL holds metadata.
"""
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from fastapi import HTTPException
from sqlalchemy import select
from . import core, dataset_models as routing, providers


class Args(BaseModel):
    model_config = ConfigDict(extra='forbid')

class ListArgs(Args):
    name: str = Field(default='', max_length=200)
    offset: int = Field(default=0, ge=0, le=10000)

class EmptyArgs(Args):
    pass

class HelpArgs(Args):
    topic: Literal['overview','datasets','documents','extractions','prompts','models','agent','review','workspace_access'] = 'overview'
    include_api: bool = False

class FindArgs(Args):
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    offset: int = Field(default=0, ge=0, le=10000)
    name: str = Field(default='',max_length=200)

class ResultFilter(Args):
    field: str = Field(min_length=1,max_length=200)
    operator: Literal['contains','not_contains','equals','gt','gte','lt','lte']
    value: str | float | bool | None

def matches_result_filter(data,condition):
    if not isinstance(data,dict) or condition['field'] not in data:return False
    actual=data[condition['field']];expected=condition['value'];op=condition['operator']
    if op in ('contains','not_contains'):
        if not isinstance(expected,str):return False
        values=actual if isinstance(actual,list) else [actual]
        found=any(isinstance(v,str) and (expected.casefold()==v.casefold() if isinstance(actual,list) else expected.casefold() in v.casefold()) for v in values)
        return found if op=='contains' else not found
    if op=='equals':return actual.casefold()==expected.casefold() if isinstance(actual,str) and isinstance(expected,str) else actual==expected
    if isinstance(actual,bool) or isinstance(expected,bool) or not isinstance(actual,(int,float)) or not isinstance(expected,(int,float)):return False
    return {'gt':lambda:actual>expected,'gte':lambda:actual>=expected,'lt':lambda:actual<expected,'lte':lambda:actual<=expected}[op]()

class ReadArgs(Args):
    extraction_id: str
    offset: int = Field(default=0, ge=0, le=10000)
    fields: list[str] = Field(default_factory=list, max_length=20)
    filters: list[ResultFilter] = Field(default_factory=list,max_length=3)

class SearchArgs(Args):
    query: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] = Field(default_factory=list, max_length=20)

class WorkflowArgs(Args):
    operation: Literal['upload', 'extract', 'reextract', 'upload_extract']
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    template_id: str = ''

class StatusArgs(Args):
    workflow_id: str = ''

class RecoveryArgs(Args):
    workflow_id: str
    action: Literal['retry','continue_ready','cancel']

class PromptArgs(Args):
    template_id: str = ''

CONTRACTS = {
    'list_datasets':(ListArgs,'List authorized dataset names and IDs. Page by next_offset; does not read document content.'),
    'get_dataset_status':(EmptyArgs,'Read live document/indexing and extraction counts, recent job progress and errors in the selected dataset/document scope. No processing is started.'),
    'get_model_configuration':(EmptyArgs,'Read selected dataset model names, versions, capabilities and default roles. No credentials or configuration changes.'),
    'get_application_info':(HelpArgs,'Read built-in Aegis product guidance for features and access rules. Set include_api=true only for explicit developer/API questions. This is guidance, not live workspace status.'),
    'list_prompts':(ListArgs,'List saved prompt filenames and versions in the selected dataset. Page by next_offset.'),
    'read_prompt':(PromptArgs,'Read the selected or named saved prompt schema, filename and version. Empty ID uses the selected prompt.'),
    'list_documents': (ListArgs, 'List actual document filenames, IDs, size, version and processing status in the selected dataset/document scope. Includes files without extraction results. For all files leave name empty and read every next_offset page.'),
    'find_extractions': (FindArgs, 'Check real saved extraction status/coverage for document IDs; latest results first. Use name to narrow an explicitly named saved extraction. Page by next_offset.'),
    'read_extraction_results': (ReadArgs, 'Read saved fields, version and review state. Each page has up to two profiles; read all required pages. Optional fields selects top-level field names.'),
    'search_documents': (SearchArgs, 'Search original document text for a question; return source passages with citation numbers.'),
    'get_workflow_status': (StatusArgs, 'Read progress/failures of this conversation workflow; empty ID means latest.'),
    'prepare_workflow': (WorkflowArgs, 'Propose requested upload/extract/reextract. Does NOT run it. The UI collects missing inputs, merge choice and confirmation.'),
    'prepare_recovery': (RecoveryArgs, 'Propose retry, continue_ready or cancel for a workflow in this conversation. Requires user confirmation; no immediate changes.'),
}


def definitions():
    result = []
    for name, (model, description) in CONTRACTS.items():
        schema = model.model_json_schema()
        definitions=schema.pop('$defs',{})
        def inline(value):
            if isinstance(value,list):return [inline(v) for v in value]
            if not isinstance(value,dict):return value
            if '$ref' in value:return inline(definitions[value['$ref'].rsplit('/',1)[-1]])
            return {k:inline(v) for k,v in value.items()}
        schema=inline(schema)
        schema.pop('title', None)
        for value in schema.get('properties', {}).values(): value.pop('title', None)
        result.append({'type': 'function', 'function': {'name': name, 'description': description, 'parameters': schema}})
    return result


class Tools:
    def __init__(self, owner, body, conversation_id, main):
        self.owner = owner; self.body = body; self.conversation_id = conversation_id; self.main = main
        self.sources = []; self.review_actions = []; self.recovery_actions = []; self.proposal = None; self.observed_results = False

    def dataset(self):
        if not self.body.dataset_id: raise HTTPException(422, 'Choose a dataset to use documents or saved results.')
        return routing.owned(self.body.dataset_id, self.owner, 'knowledge_base')

    def definitions(self):
        """Constrain model-generated references to current owned IDs.

        This complements authorization; it cannot replace rechecking in tools.
        Attached filenames are not saved document IDs.
        """
        contracts = definitions()
        docs = [d.id for d in self.documents()] if self.body.dataset_id else []
        prompts = [t.id for t in routing.rows(self.owner,'template') if t.parent_id in ('',self.body.dataset_id)]
        extractions = [e.id for e in routing.rows(self.owner,'extraction') if e.parent_id==self.body.dataset_id]
        workflows = [w.id for w,_ in self.workflows()]
        for contract in contracts:
            props=contract['function']['parameters']['properties']
            if 'document_ids' in props:
                if docs:props['document_ids']['items']={'type':'string','enum':docs}
                else:props['document_ids']['maxItems']=0
            for key,values in [('template_id',['']+prompts),('extraction_id',extractions),('workflow_id',['']+workflows)]:
                if key in props and values:props[key]['enum']=values
        return contracts

    def documents(self, ids=None):
        dataset = self.dataset(); ids = ids or self.body.document_ids
        if self.body.document_ids and ids and not set(ids) <= set(self.body.document_ids):
            raise HTTPException(422, 'This request is limited to the documents selected in the filter.')
        _, docs = routing.documents_scope(self.owner, dataset.id, ids)
        return docs

    def workflows(self):
        found=[]
        for record in routing.rows(self.owner,'agent_plan'):
            if record.parent_id!=self.body.dataset_id:continue
            data=core.store.json(record.ref)
            # Read-only answers also have plan records. They must not hide the
            # most recent executable workflow in a follow-up conversation.
            if data.get('conversation_id')==self.conversation_id and data.get('calls'):
                found.append((record,data))
        return found

    def snapshot(self):
        from .agent_workspace import application_context
        state = application_context(self.body.model_dump(), self.owner)
        state['dataset_id'] = self.body.dataset_id
        state['selected_document_ids'] = self.body.document_ids
        state['selected_prompt_id'] = self.body.template_id
        counts = {};available_fields=[]
        for record in routing.rows(self.owner,'extraction'):
            if record.parent_id != self.body.dataset_id:continue
            counts[record.status] = counts.get(record.status,0)+1
            if record.status=='ready':
                value=core.store.json(record.ref)
                if self.visible(value):
                    result=value.get('result') or {}
                    items=result.get('records',[]) if isinstance(result,dict) and 'records' in result else [{'fields':result}]
                    for item in items:
                        fields=item.get('fields',item) if isinstance(item,dict) else {}
                        if isinstance(fields,dict):available_fields.extend(fields)
        state['extraction_counts'] = counts
        state['available_result_fields']=list(dict.fromkeys(available_fields))
        workflows = self.workflows()
        if workflows:
            record, data = workflows[0]
            # Accepted jobs may have finished since the original proposal was
            # written. Read their current status without submitting any work.
            current=self.get_workflow_status(record.id)
            state['latest_workflow']={'id':record.id,'document_ids':data.get('document_ids',[]),
                'calls':[{k:c[k] for k in ('tool','status','extraction_ids','error')} for c in current['calls']]}
        return state

    def run(self, name, arguments):
        if name not in CONTRACTS: raise ValueError('Unknown tool. Choose a defined application tool.')
        values = CONTRACTS[name][0].model_validate(arguments).model_dump()
        return getattr(self, name)(**values)

    def list_documents(self, name='', offset=0):
        dataset = self.dataset(); docs = self.documents()
        documents = [{'id': d.id, 'name': d.name, 'status': d.status, 'version': d.version,
            'size':d.size,'created_at':d.created_at,'updated_at':d.updated_at,'error':d.error or None} for d in docs if name.casefold() in d.name.casefold()]
        prompts = [{'id': t.id, 'name': t.name, 'version': t.version} for t in routing.rows(self.owner, 'template') if t.parent_id in ('', dataset.id)]
        return {'dataset':{'id':dataset.id,'name':dataset.name},'scope':'selected_documents' if self.body.document_ids else 'dataset',
            'documents': documents[offset:offset+20], 'document_count': len(documents),
            'next_offset':offset+20 if offset+20<len(documents) else None,'prompts': prompts[:20], 'prompt_count': len(prompts)}

    def list_datasets(self,name='',offset=0):
        datasets=[{'id':r.id,'name':r.name,'active':routing.dataset_config(r).get('active',True)}
            for r in routing.rows(self.owner,'knowledge_base') if name.casefold() in r.name.casefold()]
        return {'datasets':datasets[offset:offset+20],'dataset_count':len(datasets),'next_offset':offset+20 if offset+20<len(datasets) else None}

    def list_prompts(self,name='',offset=0):
        dataset=self.dataset()
        prompts=[{'id':r.id,'name':core.store.json(r.ref).get('source_filename') or r.name,'version':r.version}
            for r in routing.rows(self.owner,'template') if r.parent_id in ('',dataset.id)]
        prompts=[p for p in prompts if name.casefold() in p['name'].casefold()]
        return {'dataset':{'id':dataset.id,'name':dataset.name},'prompts':prompts[offset:offset+20],
            'prompt_count':len(prompts),'next_offset':offset+20 if offset+20<len(prompts) else None}

    def get_model_configuration(self):
        dataset=self.dataset();cfg=routing.dataset_config(dataset);models=[]
        for mapping in cfg.get('mappings',[]):
            try:
                model=routing.mapped_model(dataset,mapping['model_id']);data=routing.model_data(model)
            except HTTPException:continue
            models.append({'id':model.id,'name':model.name,'version':model.version,'provider_model':data['provider_model'],
                'capabilities':data['capabilities'],'enabled':data.get('enabled',True),'mapping_enabled':mapping.get('enabled',True)})
        return {'dataset':{'id':dataset.id,'name':dataset.name},'models':models,
            'default_roles':{role:cfg.get(key) for role,key in [('chat','default_chat_model_id'),('extraction','default_extraction_model_id'),('embedding','embedding_model_id')]},
            'index_generation':cfg.get('index_generation',0),'selected_agent_model_id':self.body.planner_model_id}

    def get_dataset_status(self):
        dataset=self.dataset();docs=self.documents();document_ids={d.id for d in docs};ids=set(document_ids);document_counts={};extraction_counts={}
        for doc in docs:document_counts[doc.status]=document_counts.get(doc.status,0)+1
        for record in routing.rows(self.owner,'extraction'):
            if record.parent_id!=dataset.id:continue
            value=core.store.json(record.ref)
            coverage=set(value.get('document_ids',[]))|{s.get('document_id') for s in (value.get('merge') or {}).get('sources',[])}
            if (value.get('merge') or {}).get('document_id'):coverage.add(value['merge']['document_id'])
            if not self.visible(value) or not coverage.intersection(document_ids):continue
            ids.add(record.id);extraction_counts[record.status]=extraction_counts.get(record.status,0)+1
        jobs=[]
        with core.Session() as session:
            from .dataset_access import job_allowed
            for job in session.scalars(select(core.Job).where(core.Job.target_id.in_(ids)).order_by(core.Job.created_at.desc())):
                if not job_allowed(job,self.owner,session):continue
                state=core.job_repr(job)
                # Preserve real stage/timing facts, excluding process telemetry
                # and redundant timestamps from the chat model's small window.
                workflow=state['workflow']
                state['workflow']={'current':workflow.get('current'),'stages':{
                    name:{key:stage[key] for key in ('status','seconds','started_at') if key in stage and (key!='started_at' or stage.get('status')=='running')}
                    for name,stage in workflow.get('stages',{}).items()}}
                jobs.append(state)
        return {'dataset':{'id':dataset.id,'name':dataset.name,'active':routing.dataset_config(dataset).get('active',True)},
            'scope':'selected_documents' if self.body.document_ids else 'dataset','document_count':len(docs),
            'document_status_counts':document_counts,'extraction_status_counts':extraction_counts,
            'active_job_count':sum(j['status'] not in ('completed','failed','cancelled') for j in jobs),'recent_jobs':jobs[:8]}

    def get_application_info(self,topic='overview',include_api=False):
        from .api_documentation import NOTES
        guide={
            'datasets':'Home and Datasets organize files by dataset. Select a dataset in Aegis Agent to scope questions; Documents narrows the file selection.',
            'documents':'Upload supported files in Datasets or attach them in Aegis Agent. Uploaded originals are retained and indexed for document questions.',
            'extractions':'Select a dataset, documents and saved prompt, then ask Aegis Agent to extract. Review the proposed workflow and confirm it. The live stepper shows actual job stages; completed replies link saved results.',
            'prompts':'Prompt templates stores JSON extraction schemas by filename and dataset. Uploading the same prompt filename updates its version. Saving a prompt does not itself run extraction.',
            'models':'Model Registration registers model capabilities. Model Mapping assigns chat, extraction and embedding roles per dataset. Agent Model selects the model answering the conversation.',
            'agent':'Ask Aegis Agent about dataset filenames, counts, processing status, mapped models, original document content or saved extracted values. Replies show the actual answer workflow and result references when available.',
            'review':'Open Extraction Review, select the dataset and open the saved extraction, or click Review result in an agent reply. Compare saved fields with the displayed original; source controls show available evidence. Edit incorrect values and use Save changes. Saved output is not automatically verified source evidence.',
            'workspace_access':'Only authorized datasets, documents and results are available. Manage workspace controls users and dataset access; chat cannot change permissions.'}
        groups={'datasets':('/api/datasets',),'documents':('/api/documents',),'extractions':('/api/extractions',),
            'prompts':('/api/templates',),'models':('/api/models','/api/model-registrations','/api/datasets/{id}/models'),
            'agent':('/api/agent-v2',),'review':('/api/extractions',),'workspace_access':('/api/users/{user_id}/datasets',)}
        if topic=='overview':
            keys=['GET /api/datasets','POST /api/documents/upload','POST /api/extractions','GET /api/templates',
                'GET /api/datasets/{id}/models','POST /api/agent-v2/plans']
            entries=[{'operation':key,'description':NOTES[key]} for key in keys if key in NOTES]
        else:
            entries=[{'operation':key,'description':description} for key,description in NOTES.items()
                if any(prefix in key for prefix in groups[topic])][:12]
        return {'source':'Aegis built-in application documentation','topic':topic,'entries':entries if include_api else [],
            'user_guide':guide if topic=='overview' else {topic:guide.get(topic,'')},
            'upload_limits':{'files_per_request':20,'max_file_mb':core.settings()['max_upload_mb'],'formats':['PDF','DOCX','TXT','JSON']},
            'agent_rules':['Read workspace metadata/status and indexed document evidence using authorized tools.',
                'Read saved extraction values and review state; extracted values require verification against originals.',
                'Upload/extract/re-extract/recovery are proposals requiring confirmation; chat does not change settings or delete files.',
                'No live web search tool is configured.']}

    def read_prompt(self,template_id=''):
        self.dataset();id=template_id or self.body.template_id
        if not id:return {'prompts':self.list_documents()['prompts'],'message':'Choose a saved prompt ID.'}
        record=routing.owned(id,self.owner,'template')
        if record.parent_id and record.parent_id!=self.body.dataset_id:raise HTTPException(404,'Prompt is outside the selected dataset.')
        value=core.store.json(record.ref)
        if len(json.dumps(value.get('schema',{})))>7000:
            return {'id':id,'name':record.name,'version':record.version,'error':'This schema is too large for a chat observation. Inspect its complete content in Prompt templates.'}
        return {'id':id,'name':value.get('source_filename') or record.name,'version':record.version,'schema':value.get('schema',{})}

    def find_extractions(self, document_ids=None, offset=0,name=''):
        allowed = {d.id for d in self.documents(document_ids)}
        found = []
        for record in routing.rows(self.owner, 'extraction'):
            if record.parent_id != self.body.dataset_id: continue
            if name.casefold() not in record.name.casefold():continue
            value = core.store.json(record.ref)
            coverage = set(value.get('document_ids', [])) | {s.get('document_id') for s in (value.get('merge') or {}).get('sources', [])}
            if (value.get('merge') or {}).get('document_id'): coverage.add(value['merge']['document_id'])
            if not coverage.intersection(allowed): continue
            # Never return values from unselected sources through a merged result.
            if self.body.document_ids and not self.visible(value):
                continue
            found.append({'id': record.id, 'name': record.name, 'status': record.status, 'version': record.version,
                'document_ids': value.get('document_ids', []), 'source_ids': sorted(id for id in coverage if id),
                'prompt_id': value.get('template_id'), 'prompt_version': value.get('template_version'),
                'review_status': value.get('review_status', 'unreviewed'), 'error': record.error or None,
                'profile_count': len((value.get('result') or {}).get('records', [])) if isinstance(value.get('result'), dict) and 'records' in value['result'] else (1 if record.status == 'ready' else 0),
                'field_names':list(((value.get('result') or {}).get('records') or [{}])[0].get('fields',{})) if isinstance(value.get('result'),dict) and 'records' in value['result'] else list(value.get('result') or {})})
        ready_coverage = {id for entry in found if entry['status'] == 'ready' for id in entry['source_ids']}
        return {'extractions': found[offset:offset+8], 'total': len(found), 'name_filter':name,'next_offset': offset+8 if offset+8 < len(found) else None,
            'requested_document_ids': sorted(allowed), 'missing_document_ids': sorted(allowed-ready_coverage)}

    def visible(self, value):
        if not self.body.document_ids: return True
        # Selecting the actual merged document selects its entire source set.
        merged_id = (value.get('merge') or {}).get('document_id')
        return merged_id in self.body.document_ids or set(value.get('document_ids', [])) <= set(self.body.document_ids)

    def read_extraction_results(self, extraction_id, offset=0, fields=None, filters=None):
        self.dataset(); record = routing.owned(extraction_id, self.owner, 'extraction')
        if record.parent_id != self.body.dataset_id: raise HTTPException(404, 'Extraction is outside the selected dataset.')
        value = core.store.json(record.ref)
        if not self.visible(value):
            raise HTTPException(422, 'This merged result includes files outside the selected document filter.')
        if record.status != 'ready': return {'id': record.id, 'status': record.status, 'error': record.error, 'result': None}
        from .parquet_results import load
        value=load(value)
        original = value.get('result')
        items = original['records'] if isinstance(original, dict) and isinstance(original.get('records'), list) else [{'fields': original}]
        available=list(dict.fromkeys(k for item in items for k in (item.get('fields',item) if isinstance(item,dict) else {})))
        requested=set(fields or [])|{f['field'] for f in filters or []}
        if requested-set(available):
            return {'id':record.id,'error':'Some requested fields do not exist in this saved result.',
                'available_fields':available,'unknown_fields':sorted(requested-set(available))}
        selected=[i for i,item in enumerate(items) if all(matches_result_filter(item.get('fields',item) if isinstance(item,dict) else item,f) for f in filters or [])]
        page = []
        indices=selected[offset:offset+2]
        for i in indices:
            item=items[i]
            data = item.get('fields') if isinstance(item, dict) and 'fields' in item else item
            if fields and isinstance(data, dict): data = {k:v for k,v in data.items() if k in fields}
            page.append({'source_filename': item.get('source_filename') if isinstance(item, dict) else None, 'fields': data})
        response = {'id': record.id, 'version': record.version, 'review_status': value.get('review_status', 'unreviewed'),
            'records': page, 'total_records': len(selected), 'total_source_records':len(items),'next_offset': offset+2 if offset+2 < len(selected) else None,
            'field_projection': fields or None,'available_fields':available,'applied_filters':filters or []}
        # Large fields use an explicit field projection rather than silent loss.
        if len(json.dumps(response, ensure_ascii=False)) > 7000:
            return {'id': record.id, 'error': 'Result page is too large. Call again with the top-level fields needed for the question.',
                'available_fields': list((items[offset].get('fields') or items[offset]).keys()) if isinstance(items[offset], dict) else [], 'total_records': len(items)}
        self.observed_results = True
        document_names={d.id:d.name for d in self.documents()}
        for i,item in zip(indices,page):
            key=f'extraction:{record.id}:v{record.version}:record:{i}'
            existing=next((s for s in self.sources if s['chunk_id']==key),None)
            if existing is None:
                filename=item['source_filename'] or document_names.get((value.get('document_ids') or [''])[0],record.name)
                existing={'kind':'extraction','index':len(self.sources)+1,'chunk_id':key,
                    'extraction_id':record.id,'dataset_id':record.parent_id,'version':record.version,
                    'record_index':i,'document_name':filename,'review_status':value.get('review_status','unreviewed'),
                    'record_label':(item['fields'].get('full_name') or item['fields'].get('name') or next(iter(item['fields'].values()),None)) if isinstance(item['fields'],dict) else None,
                    'text':json.dumps(item['fields'],ensure_ascii=False),'field_projection':fields or []}
                self.sources.append(existing)
            item['citation_index']=existing['index']
        if (not filters or page) and not any(a['extraction_id'] == record.id for a in self.review_actions):
            self.review_actions.append({'extraction_id': record.id, 'name': record.name, 'version': record.version, 'label': 'Review result','fields':fields or []})
        return response

    def search_documents(self, query, document_ids=None):
        dataset = self.dataset(); docs = [d for d in self.documents(document_ids) if d.status == 'ready']
        if not docs: return {'matches': [], 'message': 'No ready documents in this scope. Check upload/indexing status.'}
        snapshot = routing.execution_snapshot(dataset, 'embedding'); routing.require_indexes(docs, snapshot)
        self.main.external_check(self.body.allow_external, True, snapshot['settings'])
        with core.execution_context(snapshot): matches = providers.search(query, self.owner, docs, min(4, core.settings()['top_k']))
        results = []
        for source in matches:
            existing = next((s for s in self.sources if s['chunk_id'] == source['chunk_id']), None)
            if existing is None:
                existing = dict(source, index=len(self.sources)+1); self.sources.append(existing)
            results.append({key: existing[key] for key in ('index','document_id','document_name','page','text') if key in existing})
            if source.get('ocr'):results[-1]['ocr_notice']='AI OCR transcription; verify names, numbers and tables against the original image.'
        return {'matches': results, 'scoped_document_count': len(docs)}

    def get_workflow_status(self, workflow_id=''):
        workflows = self.workflows()
        found = next(((r,d) for r,d in workflows if r.id == workflow_id), None) if workflow_id else next(iter(workflows), None)
        if not found: return {'workflow': None, 'message': 'No matching workflow exists in this conversation.'}
        record, data = found
        # Reading status must never submit a queued action. Reconciliation stays
        # in the existing worker/polling path; tools only inspect accepted jobs.
        entries = []
        for call in data['calls']:
            jobs = []
            with core.Session() as session:
                for id in call.get('job_ids', []):
                    job = session.get(core.Job, id)
                    from .dataset_access import job_allowed
                    if job_allowed(job,self.owner,session): jobs.append(core.job_repr(job))
            status = call['status']
            if jobs and all(j['status'] == 'completed' for j in jobs): status = 'completed'
            elif jobs and all(j['status'] in ('completed','failed','cancelled') for j in jobs): status = 'failed'
            entries.append({'tool': call['tool'], 'status': status, 'jobs': jobs,
                'extraction_ids': [e['extraction_id'] for e in call.get('result', {}).get('extractions', [])], 'error': call.get('error')})
        return {'id': record.id, 'calls': entries, 'recovery_options': ['retry','continue_ready','cancel'] if any(c['status']=='failed' for c in entries) else []}

    def prepare_recovery(self, workflow_id, action):
        status = self.get_workflow_status(workflow_id)
        if not status.get('id'): raise HTTPException(404,'Choose a workflow from this conversation.')
        index = next((i for i,c in enumerate(status['calls']) if c['status'] in ('failed','pending')), None)
        if index is None: raise HTTPException(409,'This workflow has no failed or pending action to recover.')
        selected = status['calls'][index]
        if action != 'cancel' and selected['status'] != 'failed':
            raise HTTPException(409,'Only a failed action can be retried or continued.')
        if action == 'continue_ready' and (selected['tool']!='upload' or not any(j['status']=='completed' for j in selected['jobs'])):
            raise HTTPException(422,'Continue with ready files is available only for a partially completed upload.')
        value = {'workflow_id':workflow_id,'index':index,'action':action,'label':{'retry':'Confirm retry','continue_ready':'Confirm continue with ready files','cancel':'Confirm end request'}[action]}
        self.recovery_actions.append(value)
        return {'proposal':value,'executed':False,'confirmation_required':True}

    def prepare_workflow(self, operation, document_ids=None, template_id=''):
        if document_ids: self.documents(document_ids)
        template_id = template_id or self.body.template_id
        if template_id:
            template = routing.owned(template_id, self.owner, 'template')
            if template.parent_id and template.parent_id != self.body.dataset_id:
                raise HTTPException(422, 'Choose a prompt from the selected dataset.')
        if operation=='extract' and not self.body.attached_filenames:
            selected=set(document_ids or self.body.document_ids)
            for entry in self.find_extractions(list(selected) or None)['extractions']:
                if set(entry['document_ids'])==selected and entry.get('prompt_id')==template_id and entry['status'] in ('queued','processing','ready'):
                    return {'existing_extraction_id':entry['id'],'status':entry['status'],'executed':False,'message':'Follow this existing extraction. Explicit re-extract creates a new run.'}
        tools = {'upload':['upload'], 'extract':['extract'], 'reextract':['reextract'], 'upload_extract':['upload','extract']}[operation]
        if self.body.attached_filenames and operation == 'extract': tools.insert(0,'upload')
        if self.body.submitted_prompt_id and not self.body.attached_filenames and operation == 'upload':
            return {'proposal': None, 'completed_event':'prompt_saved', 'message': 'The attached prompt is already validated and saved. It is a template, not a document upload.'}
        if operation == 'reextract' and self.body.attached_filenames:
            raise HTTPException(422, 'Re-extract targets saved documents; upload newly attached files in a separate workflow.')
        self.proposal = {'document_ids': document_ids or self.body.document_ids, 'template_id': template_id,
            'calls': [{'tool': t, 'title': {'upload':'Upload documents','extract':'Extract fields','reextract':'Re-extract fields'}[t]} for t in tools]}
        return {'proposed': self.proposal, 'executed': False, 'confirmation_required': True,
            'message': 'The UI will collect missing inputs and ask combined or independent for multiple files before confirmation.'}
