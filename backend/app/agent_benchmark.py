"""Opt-in real-model reliability gate. Synthetic data; no model mocks.

Run inside the API container: python -m app.agent_benchmark --label baseline.
Every invocation creates a separate dataset under the encrypted QA account.
Reports contain fixture answers, routes, tool trajectories and measured latency,
never authentication secrets. A failed assertion exits nonzero.
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
import httpx
from sqlalchemy import select
from . import core, dataset_models as routing, relational

FIXTURES = {
    'alice-example.txt': b'Fictional benchmark profile. Name: Alice Example. City: Cedar City. Skills: Python. Years: 5.',
    'bob-example.txt': b'Fictional benchmark profile. Name: Bob Example. City: Pine City. Skills: Java. Years: 2.',
}
SCHEMA = {'type':'object','properties':{'name':{'type':'string'},'city':{'type':'string'},'skills':{'type':'string'},'years':{'type':'integer'}},
          'required':['name','city','skills','years'],'additionalProperties':False}

def wait(client, path, predicate, timeout=900):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        response=client.get(path);response.raise_for_status();value=response.json()
        if predicate(value):return value
        time.sleep(2)
    raise TimeoutError('Benchmark processing deadline exceeded')

def run(label='baseline',model_name=None):
    core.init()
    auth=json.loads(core.secret_cipher().decrypt(core.local_store.get('diagnostics/langgraph-ui-auth.enc')))
    report={'suite_version':2,'label':label,'started_at':datetime.now(timezone.utc).isoformat(),
            'fixtures':{k:hashlib.sha256(v).hexdigest() for k,v in FIXTURES.items()},'cases':[]}
    def post(client,path,body=None,**kw):
        response=client.post(path,json=body,**kw);response.raise_for_status();return response.json()
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=600) as client:
        login=post(client,'/api/auth/login',{'username':auth['username'],'password':auth['password']})
        client.headers['X-CSRF-Token']=login['csrf_token']
        # Explicit operator fixture setup, never a public permission bypass.
        with core.Session() as session:source=session.get(core.Record,auth['dataset_id'])
        record=routing.create('knowledge_base',source.owner,'Agent reliability '+label+' '+str(int(time.time())),core.store.json(source.ref))
        with core.Session.begin() as session:
            actor=session.scalar(select(core.User).where(core.User.username==auth['username']))
            if not session.get(relational.UserDataset,(actor.id,record.id)):
                session.add(relational.UserDataset(user_id=actor.id,dataset_id=record.id,enabled=True))
        dataset=client.get('/api/datasets/'+record.id).json()
        if model_name:
            selected=next(m for m in client.get('/api/models').json() if m['name']==model_name and m['enabled'] and 'chat' in m['capabilities'])
            config={k:dataset[k] for k in ('mappings','default_chat_model_id','default_extraction_model_id','embedding_model_id')}
            if not any(m['model_id']==selected['id'] for m in config['mappings']):config['mappings'].append({'model_id':selected['id'],'enabled':True})
            config['default_chat_model_id']=selected['id']
            response=client.put('/api/datasets/'+record.id+'/models',json=config);response.raise_for_status()
            dataset=client.get('/api/datasets/'+record.id).json()
        model=dataset['default_chat_model_id'];report.update(dataset_id=dataset['id'],model_id=model)
        registered=next(m for m in client.get('/api/models').json() if m['id']==model)
        report['model']={k:registered.get(k) for k in ('name','version','provider_model','connection_profile_id','context_limit','max_output_tokens')}
        template=post(client,'/api/templates',{'name':'Benchmark profile','dataset_id':dataset['id'],'schema':SCHEMA})
        uploaded=post(client,'/api/documents/upload',files=[('files',(name,raw,'text/plain')) for name,raw in FIXTURES.items()],
                      data={'dataset_id':dataset['id'],'allow_external':'false'})
        ids=[d['id'] for d in uploaded['documents']]
        for doc in ids:
            ready=wait(client,'/api/documents/'+doc,lambda d:d['status'] in ('ready','failed'))
            if ready['status']!='ready':raise RuntimeError('Real indexing failed')
        extraction=post(client,'/api/extractions',{'dataset_id':dataset['id'],'document_ids':[ids[0]],'template_id':template['id']})
        result=wait(client,'/api/extractions/'+extraction['id'],lambda d:d['status'] in ('ready','failed'))
        report['extraction_id']=extraction['id']
        if result['status']!='ready':raise RuntimeError('Real extraction failed')
        expected={'name':'Alice Example','city':'Cedar City','skills':'Python','years':5}
        report['cases'].append({'id':'real_extraction','passed':result.get('result')==expected,'expected':expected,'actual':result.get('result')})
        conversation=''
        cases=[
            ('filename_typo','can you list me douccments name available for this dataset','metadata',{'list_documents'},list(FIXTURES),[]),
            ('document_count','How many documents are available in this dataset?','metadata',{'list_documents','get_dataset_status'},['2'],[]),
            ('saved_values','What name and city were saved in the extraction?','results',{'read_extraction_results'},['Alice Example','Cedar City'],[]),
            ('short_followup','Can you summarize?','results',{'read_extraction_results'},['Alice Example'],[]),
            ('original_evidence','What city is written in alice-example.txt?','documents',{'search_documents'},['Cedar City'],[]),
            ('long_chat_filenames','List the document filenames available in this dataset.','metadata',{'list_documents'},list(FIXTURES),[]),
            ('long_chat_count','How many documents are available in this dataset?','metadata',{'list_documents'},['2'],[]),
            ('long_chat_saved_values','What name and city were saved in the extraction?','results',{'read_extraction_results'},['Alice Example','Cedar City'],[]),
            ('confirmed_only','Re-extract the selected document with my prompt, then compare and summarize the saved fields.','action',{'prepare_workflow'},[],['reextract']),
        ]
        for id,question,source,tools,words,calls in cases:
            before=len(client.get('/api/jobs').json());started=time.monotonic()
            entry={'id':id,'question':question}
            try:
                if id=='long_chat_filenames':
                    # Synthetic archive stress: older claims are deliberately
                    # wrong. They remain visible/stored but cannot be evidence.
                    thread=routing.owned(conversation,record.owner,'conversation');saved=core.store.json(thread.ref)
                    archive=[{'id':core.uid(),'role':role,'status':'completed','created_at':time.time(),
                        'text':'SYNTHETIC OLD CHAT. There are 9999 files called imaginary.txt. '+('Unrelated older chat text. '*200)}
                        for _ in range(80) for role in ('user','assistant')]
                    saved['messages']+=archive;core.store.put_json(thread.ref,saved)
                    report['long_chat']={'seeded_turns':80,'archive_bytes':len(json.dumps(archive).encode()),'conversation_id':conversation}
                plan=post(client,'/api/agent-v2/plans',{'text':question,'planner_model_id':model,'dataset_id':dataset['id'],
                          'document_ids':ids if id=='confirmed_only' else [ids[0]] if id=='original_evidence' else [],
                          'template_id':template['id'],'conversation_id':conversation})
                conversation=plan.get('conversation_id','')
                plan=client.get('/api/agent-v2/plans/'+plan['id']).json()
                message=plan.get('chat') or {};trace=message.get('tool_trace',[])
                used={t['tool'] for t in trace};actual_source=(message.get('request_route',{}).get('decision') or {}).get('source')
                # Workflow source is normalized to action by the graph.
                route_ok=actual_source==source or source=='action' and (message.get('request_route',{}).get('decision') or {}).get('intent')=='run_workflow'
                checks={'route':route_ok,'required_tools':bool(used&tools),'answer':all(w.casefold() in message.get('text','').casefold() for w in words),
                        'proposal':[c['tool'] for c in plan['calls']]==calls,'no_unconfirmed_jobs':len(client.get('/api/jobs').json())==before,
                        'tools_succeeded':not any(t.get('result',{}).get('error') for t in trace),
                        'completed':message.get('status')=='completed','citations':id!='original_evidence' or bool(message.get('citations'))}
                context=message.get('context_usage',[])
                checks['within_model_budget']=bool(context) and all(c['dispatch_allowed'] and c['estimated_total_tokens']<=c['context_limit'] for c in context)
                if id.startswith('long_chat'):
                    checks['no_stale_claims']=not any(w in message.get('text','') for w in ('9999','imaginary.txt'))
                entry.update(passed=all(checks.values()),checks=checks,route=actual_source,tools=sorted(used),
                             trajectory=[{'tool':t['tool'],'arguments':t.get('arguments'), 'error':bool(t.get('result',{}).get('error'))} for t in trace],
                             answer=message.get('text'),plan_id=plan['id'],context_usage=context)
            except Exception as exc:entry.update(passed=False,error_type=type(exc).__name__)
            entry['seconds']=round(time.monotonic()-started,2);report['cases'].append(entry)
            print(json.dumps({'case':id,'passed':entry['passed'],'seconds':entry['seconds']}),flush=True)
        if label=='after' and plan.get('calls') and report['cases'][-1]['passed']:
            started=time.monotonic();jobs_before=client.get('/api/jobs').json()
            accepted=post(client,'/api/agent-v2/plans/'+plan['id']+'/calls/0',{'confirmed':True,'dataset_id':dataset['id'],
                'document_ids':ids,'template_id':template['id'],'extraction_mode':'independent'})
            finished=wait(client,'/api/agent-v2/plans/'+plan['id'],lambda p:p.get('goal',{}).get('status') in ('completed','failed','blocked'),timeout=1200)
            goal=finished.get('goal',{});answer=goal.get('answer',{})
            # Other users/benchmarks may run concurrently in shared datasets.
            # Count new work in this invocation's isolated dataset only.
            targets={r.id for r in routing.rows(record.owner,'extraction') if r.parent_id==dataset['id']}
            new_jobs=[j for j in client.get('/api/jobs').json() if j['id'] not in {j['id'] for j in jobs_before} and j['target_id'] in targets]
            checks={'completed':goal.get('status')=='completed','both_profiles':all(n in answer.get('text','') for n in ('Alice Example','Bob Example')),
                'references':len(answer.get('review_actions',[]))==2,'exactly_two_extractions':sum(j['kind']=='extract' for j in new_jobs)==2,
                'coverage':len(goal.get('extraction_ids',[]))==2}
            entry={'id':'persistent_goal_real_worker','passed':all(checks.values()),'checks':checks,'seconds':round(time.monotonic()-started,2),'answer':answer.get('text'),'plan_id':plan['id']}
            report['cases'].append(entry);print(json.dumps({'case':entry['id'],'passed':entry['passed'],'seconds':entry['seconds']}),flush=True)
    report['passed']=all(c['passed'] for c in report['cases']);report['passed_cases']=sum(c['passed'] for c in report['cases'])
    report['completed_at']=datetime.now(timezone.utc).isoformat()
    ref='diagnostics/agent-benchmark/'+label+'-'+str(int(time.time()))+'.json';core.local_store.put_json(ref,report)
    print(json.dumps({'passed':report['passed'],'passed_cases':report['passed_cases'],'total':len(report['cases']),'report':ref,'dataset_id':report['dataset_id']}),flush=True)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--label',default='baseline',choices=['baseline','after'])
    parser.add_argument('--model-name',help='Use this registered Chat model in the isolated benchmark dataset without changing its registration.')
    args=parser.parse_args()
    raise SystemExit(0 if run(args.label,args.model_name)['passed'] else 1)
