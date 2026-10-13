"""Durable, bounded continuation of confirmed plans; no second job queue.

Accepted extraction remains in the existing lease worker. The worker reconciles
the goal after its exact jobs finish, even without an open browser. Finalization
has a durable lease, bounded retries and a conversation-level deduplication key.
"""
import time
from fastapi import HTTPException
from . import core, dataset_models as routing, providers

ACTIVE = {'queued','running','retry_wait'}
MAX_ATTEMPTS = 3
LEASE_SECONDS = 900

def save(record,data):
    from .agent_workspace import save_plan
    save_plan(record,data)

def seed(data):
    if data.get('runtime')!='langgraph' or not data.get('calls') or 'goal' in data:return
    data['goal']={'status':'awaiting_confirmation','request':data['request'],'attempts':0,
        'created_at':time.time(),'criteria':['Finish every confirmed workflow step','Inspect saved results','Answer the original request with result references'],
        'steps':[]}

def refresh(data):
    goal=data.get('goal')
    if not goal:return
    if data.get('superseded') and goal['status']!='completed':
        goal.update(status='cancelled',lease_token='');return
    if goal['status'] in ('completed','cancelled','paused','blocked','failed') or goal['status'] in ACTIVE:return
    calls=data['calls']
    if any(c['status']=='failed' for c in calls):goal['status']='waiting_recovery'
    elif calls and all(c['status']=='completed' for c in calls):goal.update(status='queued',started_at=time.time())
    elif any(c.get('started_at') for c in calls):goal['status']='waiting_jobs'
    else:goal['status']='awaiting_confirmation'

def extraction_ids(data):
    return list(dict.fromkeys(id for c in data['calls'] if c['tool'] in ('extract','reextract')
        for id in ([e['extraction_id'] for e in c.get('result',{}).get('extractions',[]) if not e.get('superseded')]
                   or [c.get('result',{}).get('extraction_id')]) if id))

def advance(record, main):
    """Worker-only entry. GET/SSE never runs a model or starts finalization."""
    with core.document_lock('agent-'+record.id):
        data=core.store.json(record.ref);refresh(data);goal=data.get('goal')
        if not goal:return
        now=time.time()
        if goal['status']=='running' and goal.get('lease_until',0)>now:return
        if goal['status'] not in ACTIVE or goal.get('next_attempt_at',0)>now:return
        if not all(c['status']=='completed' for c in data['calls']):return
        if goal['attempts']>=MAX_ATTEMPTS:
            goal.update(status='failed',error='Goal recovery attempts exhausted. Retry the answer to continue without rerunning extraction.')
            save(record,data);return
        token=core.uid();goal.update(status='running',lease_token=token,lease_until=now+LEASE_SECONDS,
                                   attempts=goal['attempts']+1,started_at=now)
        if goal.get('answer_workflow'):
            goal.setdefault('previous_answer_workflows',[]).append(goal.pop('answer_workflow'))
            goal['previous_answer_workflows']=goal['previous_answer_workflows'][-3:]
        goal.pop('error',None);save(record,data)
    try:
        # Permissions are checked on every recovery, not inherited from consent.
        routing.owned(record.id,record.owner,'agent_plan')
        dataset=routing.owned(data['dataset_id'],record.owner,'knowledge_base')
        ids=extraction_ids(data)
        if not ids and any(c['tool'] in ('extract','reextract') for c in data['calls']):
            raise ValueError('The confirmed extraction has no saved result reference. Check accepted processing before continuing.')
        if data.get('agent')!='reextract':
            snapshot=routing.execution_snapshot(dataset,'chat',data['planner']['id'])
            if snapshot['model_version']!=data['planner']['version']:
                raise ValueError('The Agent Model version changed. Send a new request using the current model.')
            main.external_check(data.get('workflow_allow_external',False),cfg=snapshot['settings'])
        conversation=routing.owned(data['conversation_id'],record.owner,'conversation')
        key=record.id+':'+str(data.get('restart_attempt',0))
        saved=next((m for m in core.store.json(conversation.ref)['messages'] if m.get('goal_id')==key and m.get('status')=='completed'),None)
        def progress(workflow):
            with core.document_lock('agent-'+record.id):
                latest=core.store.json(record.ref);current=latest['goal']
                if current.get('lease_token')!=token or current['status']!='running':
                    raise providers.ProviderError('Goal continuation was paused or cancelled.')
                current.update(answer_workflow=workflow,lease_until=time.time()+LEASE_SECONDS)
                save(record,latest)
        if saved:message=saved
        elif data.get('agent')=='reextract':
            from .reextract_agent import finish
            from .agent_progress import AnswerProgress
            message=finish(record,data,key,AnswerProgress(progress))
        elif not ids:
            # Upload-only goals have no extracted fields to invent.
            message={'text':'The confirmed upload and indexing workflow completed. Your documents are ready for questions.',
                     'status':'completed','citations':[],'review_actions':[]}
        else:
            expected=set(data.get('document_ids',[]));covered=set()
            for id in ids:
                extraction=routing.owned(id,record.owner,'extraction')
                if extraction.parent_id!=dataset.id or extraction.status!='ready':raise ValueError('A confirmed result is unavailable. Check the extraction before continuing.')
                covered.update(core.store.json(extraction.ref).get('document_ids',[]))
            if expected-covered:raise ValueError('Some confirmed documents have no completed result. Recover their processing before completing the goal.')
            from .agent_workspace import PlanInput
            from . import agent_graph
            body=PlanInput(text='Complete the confirmed request using its saved results: '+goal['request'],
                planner_model_id=data['planner']['id'],dataset_id=dataset.id,document_ids=list(covered),
                conversation_id=conversation.id,allow_external=data.get('workflow_allow_external',False))
            message=agent_graph.run(record.owner,body,snapshot,main,on_progress=progress,
                goal_context={'goal_id':key,'extraction_ids':ids,'request':goal['request']})['message']
        with core.document_lock('agent-'+record.id):
            latest=core.store.json(record.ref);current=latest['goal']
            if current.get('lease_token')!=token or current['status']!='running':return
            current.update(status='completed',answer=message,extraction_ids=ids,finished_at=time.time(),lease_token='',
                           coverage={'expected_documents':len(data.get('document_ids',[])),'completed_extractions':len(ids)})
            save(record,latest)
    except Exception as exc:
        with core.document_lock('agent-'+record.id):
            latest=core.store.json(record.ref);current=latest['goal']
            if current.get('lease_token')!=token:return
            # Error messages from permissions/validation are curated; unknown
            # exceptions and provider errors never expose provider payloads.
            retryable=isinstance(exc,providers.ProviderError)
            status='retry_wait' if retryable and current['attempts']<MAX_ATTEMPTS else 'blocked' if isinstance(exc,HTTPException) and exc.status_code in (403,404) else 'failed'
            detail=str(exc.detail) if isinstance(exc,HTTPException) else str(exc) if isinstance(exc,ValueError) else 'The result answer could not finish. Saved extractions are retained.'
            current.update(status=status,error=detail,next_attempt_at=time.time()+min(120,10*2**(current['attempts']-1)),lease_token='')
            if current.get('answer_workflow'):
                current['answer_workflow']['status']='failed'
            save(record,latest)

def control(record,action):
    with core.document_lock('agent-'+record.id):
        data=core.store.json(record.ref);goal=data.get('goal')
        if not goal or data.get('superseded'):raise HTTPException(409,'This goal is no longer active.')
        if action=='retry':
            if goal['status'] not in ('failed','blocked','paused'):raise HTTPException(409,'Only a stopped goal answer can be resumed.')
            if not all(c['status']=='completed' for c in data['calls']):raise HTTPException(409,'Recover the document workflow first.')
            goal.update(status='queued',attempts=0,next_attempt_at=0,lease_token='',started_at=time.time())
        elif action=='pause':
            if goal['status'] not in ACTIVE:raise HTTPException(409,'Only an active answer can be paused.')
            goal.update(status='paused',lease_token='')
        elif action=='cancel':
            if goal['status']=='completed':raise HTTPException(409,'This goal already completed.')
            goal.update(status='cancelled',lease_token='')
        goal.pop('error',None);save(record,data)
        return {'id':record.id,**data}
