"""Direct Re-extract handoff and durable publication of saved reruns."""
import time
from fastapi import HTTPException
from .. import core, dataset_models as routing

LEASE_SECONDS=900

class ReextractAgent:
    name='reextract'
    def __init__(self,tools):self.tools=tools

    def prepare(self,decision):
        if decision['operation']=='retry':
            workflows=[(r,d) for r,d in self.tools.workflows() if not d.get('superseded') and
                any(c['status']=='failed' for c in d['calls'])]
            if not workflows:raise HTTPException(409,'No failed workflow in this conversation is available to retry.')
            record,data=workflows[0]
            if any(c.get('publication_error') for c in data['calls']):
                return {'tool':'prepare_recovery','arguments':{'workflow_id':record.id,'action':'retry'},
                    'result':{'executed':False,'publication_retry_required':True,'workflow_id':record.id},
                    'answer':'The saved results are preserved. Use Retry knowledge update on the failed workflow to publish them without repeating extraction.'}
            arguments={'workflow_id':record.id,'action':'retry'}
            result=self.tools.run('prepare_recovery',arguments)
            return {'tool':'prepare_recovery','arguments':arguments,'result':result,
                'answer':'Review and confirm retry of the failed step. Successful files and earlier results are preserved.'}
        if decision['operation']!='reextract':raise HTTPException(422,'Unsupported Re-extract operation.')
        attached={name.casefold() for name in self.tools.body.attached_filenames}
        names=[name for name in decision.get('document_names',[]) if name.casefold() not in attached]
        if attached:
            # The confirmed chain consumes only its own returned upload references.
            self.tools.body.document_ids=[]
        elif names:
            docs=self.tools.documents();selected=[]
            for name in names:
                matches=[d for d in docs if d.name.casefold()==name.casefold()]
                if len(matches)!=1:raise HTTPException(422,'Select the specific saved document in the file filter: '+name+'.')
                selected.append(matches[0].id)
            self.tools.body.document_ids=list(dict.fromkeys(selected))
        arguments={'operation':'reextract','document_ids':self.tools.body.document_ids,'template_id':self.tools.body.template_id}
        result=self.tools.run('prepare_workflow',arguments)
        self.tools.proposal['agent']=self.name
        return {'tool':'prepare_workflow','arguments':arguments,'result':result,
            'answer':('Choose the dataset and prompt below, then confirm upload and re-extraction. The attached files will be uploaded and indexed first.' if attached else 'Choose the saved documents and prompt below, then confirm Re-extract.')+' Earlier results are retained. Completion includes verified Parquet and published vector knowledge.'}

def publish_pending(record,main):
    """Worker-owned lease; release the plan lock during file/vector I/O."""
    from .agent_workspace import save_plan, plan_public
    with core.document_lock('agent-'+record.id):
        data=core.store.json(record.ref)
        if data.get('agent')!='reextract' or data.get('superseded'):return
        index=next((i for i,c in enumerate(data['calls']) if c['status']=='waiting' and c.get('publication_pending')),None)
        if index is None:return
        call=data['calls'][index]
        if call.get('publication_lease_until',0)>time.time():return
        token=core.uid();call.update(publication_token=token,publication_lease_until=time.time()+LEASE_SECONDS,
            publication_status='running',publication_started_at=time.time())
        save_plan(record,data)
    error=False
    try:
        routing.owned(record.id,record.owner,'agent_plan')
        from .onboard_extract_agent import publish_call
        publish_call(record,data,call)
    except Exception:error=True
    with core.document_lock('agent-'+record.id):
        latest=core.store.json(record.ref);current=latest['calls'][index]
        if latest.get('superseded') or current.get('publication_token')!=token:return
        current.update(publication_token='',publication_lease_until=0,publication_pending=False,
            publication_duration_ms=round((time.time()-current['publication_started_at'])*1000))
        if error:
            current['publication_auto_continue']=latest.get('auto_continue',False)
            current.update(status='failed',publication_status='failed',publication_error=True,
                error='Updated files are saved, but knowledge publication needs retry.')
            latest['auto_continue']=False
        else:
            current.update(vector_publication=call['vector_publication'],publication_status='completed',
                status='completed',finished_at=time.time())
            current.pop('publication_error',None);current.pop('error',None)
        save_plan(record,latest)
        plan_public(record,main)

def finish(record,data,key,progress):
    """Verified execution receipt; no classification, tool selection or answer LLM."""
    from .agent_goals import extraction_ids
    ids=extraction_ids(data);proofs={}
    for call in data['calls']:
        receipt=call.get('vector_publication') or {}
        if call['status']!='completed' or not receipt.get('verified_vectors'):
            raise ValueError('Re-extraction has not completed verified knowledge publication.')
        for artifact in receipt.get('verified_artifacts',[]):proofs[artifact['extraction_id']]=artifact
    if not ids:raise ValueError('No updated extraction result is available.')
    actions=[];citations=[];covered=set();providers=set()
    with progress.step('Verify saved Parquet and vector publication'):
        for id in ids:
            result=routing.owned(id,record.owner,'extraction');saved=core.store.json(result.ref);proof=proofs.get(id)
            if not proof or result.parent_id!=data['dataset_id'] or result.status!='ready' or result.version!=proof['version'] or saved.get('output_reference')!=proof['reference'] or saved.get('output_sha256')!=proof['sha256']:
                raise ValueError('The updated result changed after publication. Republish the saved result before completing this workflow.')
            covered.update(saved['document_ids'])
            actions.append({'extraction_id':id,'name':result.name,'version':result.version,'label':'Review result'})
            citations.append({'kind':'extraction','index':len(citations)+1,'extraction_id':id,
                'document_name':result.name,'version':result.version,'document_ids':saved['document_ids']})
            if len(saved['document_ids'])==1:citations[-1]['document_id']=saved['document_ids'][0]
        providers={c['vector_publication']['provider'] for c in data['calls']}
        if set(data['document_ids'])-covered:raise ValueError('Some confirmed documents have no published updated result.')
    destination='OCI vector store' if providers=={'oracle'} else 'published vector knowledge'
    storage=' in OCI storage' if {a.get('storage_provider') for a in proofs.values()}=={'oci'} else ''
    message={'id':core.uid(),'role':'assistant','status':'completed','runtime':'langgraph','goal_id':key,
        'text':f'Re-extraction completed. {len(ids)} updated result'+(' is' if len(ids)==1 else 's are')+
            ' saved as verified Parquet'+storage+' and published to '+destination+'. Earlier results are preserved. Open Review to inspect the new result.',
        'citations':citations,'review_actions':actions,'recovery_actions':[],'created_at':time.time(),
        'request_route':{'agent':'reextract','model_calls':0},
        'tool_trace':[{'tool':'verify_reextract_publication','agent':'reextract','result':{
            'extraction_ids':ids,'verified_artifacts':list(proofs.values()),'providers':sorted(providers)}}]}
    with progress.step('Save completion receipt'):
        conversation=routing.owned(data['conversation_id'],record.owner,'conversation')
        with core.document_lock('agent-turn-'+conversation.id):
            thread=core.store.json(conversation.ref)
            previous=next((m for m in thread['messages'] if m.get('goal_id')==key and m.get('status')=='completed'),None)
            if previous:return previous
            thread['messages'].append(message);core.store.put_json(conversation.ref,thread)
    progress.complete();message['answer_workflow']=progress.snapshot()
    with core.document_lock('agent-turn-'+conversation.id):
        thread=core.store.json(conversation.ref)
        next(m for m in thread['messages'] if m.get('id')==message['id'])['answer_workflow']=message['answer_workflow']
        core.store.put_json(conversation.ref,thread)
    return message
