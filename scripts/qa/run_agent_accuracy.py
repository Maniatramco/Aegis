"""Frozen-model, real-service extension of the existing benchmark.

Run inside the API container with --core-report diagnostics/agent-benchmark/FILE.
Uses its isolated fictional dataset and existing encrypted QA login. It never
changes registrations, elevates users, or confirms proposed workflow jobs.
"""
import argparse
import json
import re
import time
from datetime import datetime, timezone
import httpx
from sqlalchemy import select
from app import core, relational, dataset_models as routing, parquet_results


def run(core_report):
    baseline=core.local_store.json(core_report)
    auth=json.loads(core.secret_cipher().decrypt(core.local_store.get('diagnostics/langgraph-ui-auth.enc')))
    report={'suite_version':1,'started_at':datetime.now(timezone.utc).isoformat(),
            'core_report':core_report,'model':baseline['model'],'cases':[],
            'grading':'Predeclared deterministic fixture checks; no model judge, retries or product changes.'}
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=600) as client:
        def post(path,body):
            response=client.post(path,json=body);response.raise_for_status();return response.json()
        login=post('/api/auth/login',{'username':auth['username'],'password':auth['password']})
        client.headers['X-CSRF-Token']=login['csrf_token']
        actor=login['user']['id']
        with core.Session() as session: dataset=session.get(core.Record,baseline['dataset_id'])
        data=core.store.json(dataset.ref)
        data['description']='Fictional developer recruitment profiles: Python and Java programming skills, cities and years of engineering experience.'
        routing.write_version(dataset,data)
        decoy=routing.create('knowledge_base',dataset.owner,'Accuracy supplier billing '+str(int(time.time())),
            dict(data,description='Fictional supplier billing archive: invoices, payable amounts and purchase references.'))
        with core.Session.begin() as session:
            if not session.get(relational.UserDataset,(actor,decoy.id)):
                session.add(relational.UserDataset(user_id=actor,dataset_id=decoy.id,enabled=True))
        report.update(dataset_id=dataset.id,decoy_dataset_id=decoy.id)
        docs=client.get('/api/documents',params={'dataset_id':dataset.id}).json()
        alice=next(d['id'] for d in docs if d['name']=='alice-example.txt')
        templates=[t for t in client.get('/api/templates').json() if (t.get('dataset_id') or t.get('kb_id'))==dataset.id]
        template=next(t['id'] for t in templates if t['name']=='Benchmark profile')
        model=baseline['model_id']
        def has(answer,*terms):return all(t.casefold() in answer.casefold() for t in terms)
        def lacks(answer,*terms):return all(t.casefold() not in answer.casefold() for t in terms)
        def unknown(answer):return bool(re.search(r'\b(no|none|not|missing|unavailable|insufficient|cannot|couldn.t|0)\b',answer,re.I))
        def count(answer,n):return bool(re.search(r'\b'+str(n)+r'\b|\b'+{1:'one',2:'two'}[n]+r'\b',answer,re.I))
        cases=[
            ('semantic_developer_dataset','Semantically find a dataset about developer recruitment, programming skills and work experience.',
             {'knowledge'},{'search_knowledge'},lambda a:has(a,dataset.name),[],False),
            ('semantic_invoice_dataset','Semantically find a dataset about supplier bills, invoice amounts and purchase references.',
             {'knowledge'},{'search_knowledge'},lambda a:has(a,decoy.name),[],False),
            ('semantic_prompt','Semantically find a prompt schema for a person name, city, programming skills and years of experience.',
             {'knowledge','prompt'},{'search_knowledge','read_prompt'},lambda a:has(a,'Benchmark profile','skills','years'),[],True),
            ('semantic_saved_result','Semantically find the saved result about a Python developer in Cedar City; show their name, skills and city.',
             {'knowledge','results'},{'search_knowledge','read_extraction_results'},lambda a:has(a,'Alice Example','Python','Cedar City') and lacks(a,'Bob Example'),[],True),
            ('list_all_skills','list all skills',{'results'},{'read_extraction_results'},lambda a:has(a,'Python') and lacks(a,'Java'),[],True),
            ('names_and_count','Can you list the document names available for this dataset and give the exact count?',
             {'metadata'},{'list_documents'},lambda a:has(a,'alice-example.txt','bob-example.txt') and count(a,2),[],False),
            ('selected_document_count','How many documents are in the selected document scope?',
             {'metadata'},{'list_documents','get_dataset_status'},lambda a:count(a,1) and not count(a,2),[alice],False),
            ('missing_saved_bob','What city is saved in the extraction for Bob Example?',
             {'results'},{'find_extractions','read_extraction_results'},lambda a:unknown(a) and lacks(a,'Pine City'),[],False),
            ('current_model_limit','What is the configured maximum context token limit for the chat model mapped to this dataset?',
             {'metadata'},{'get_model_configuration'},lambda a:has(a.replace(',',''),'262144'),[],False),
            ('missing_invoice_field','What invoice number is saved in the extraction for Alice Example?',
             {'results'},{'find_extractions','read_extraction_results'},lambda a:unknown(a),[],False),
        ]
        def evaluate(case):
            id,question,sources,tools,score,selected,citation=case
            entry={'id':id,'question':question,'expected_sources':sorted(sources),'acceptable_tools':sorted(tools)}
            started=time.monotonic();before={j['id'] for j in client.get('/api/jobs').json()}
            try:
                plan=post('/api/agent-v2/plans',{'text':question,'planner_model_id':model,'dataset_id':dataset.id,
                    'document_ids':selected,'template_id':template})
                plan=client.get('/api/agent-v2/plans/'+plan['id']).json();message=plan.get('chat') or {}
                trace=message.get('tool_trace',[]);used={o['tool'] for o in trace}
                source=message.get('request_route',{}).get('decision',{}).get('source')
                answer=message.get('text','');context=message.get('context_usage',[])
                checks={'answer_accuracy':bool(score(answer)) and message.get('status')=='completed',
                    'tool_accuracy':source in sources and bool(used & tools),
                    'no_mutation':not plan['calls'] and before=={j['id'] for j in client.get('/api/jobs').json()},
                    'within_budget':bool(context) and all(c['dispatch_allowed'] and c['estimated_total_tokens']<=c['context_limit'] for c in context),
                    'citations':not citation or bool(message.get('citations')),
                    'no_step_limit':'tool-step limit' not in answer}
                entry.update(checks=checks,passed=all(checks.values()),answer=answer,source=source,
                    tools=sorted(used),plan_id=plan['id'],context_usage=context,
                    trajectory=[{'tool':o['tool'],'arguments':o.get('arguments',{}),'error':o.get('result',{}).get('error')} for o in trace])
            except Exception as error:
                entry.update(passed=False,error_type=type(error).__name__,checks={'answer_accuracy':False,'tool_accuracy':False})
            entry['seconds']=round(time.monotonic()-started,2);report['cases'].append(entry)
            core.local_store.put_json('diagnostics/agent-accuracy/current.json',report)
            print(json.dumps({'case':id,'passed':entry['passed'],'checks':entry['checks'],'seconds':entry['seconds']}),flush=True)
        for case in cases:evaluate(case)
        # Explicit operator edit of this run's fictional fixture only. Originals
        # and historical revisions stay intact; this exercises source separation.
        with core.Session() as session:extraction=session.get(core.Record,baseline['extraction_id'])
        saved=parquet_results.load(core.store.json(extraction.ref))
        assert saved['result']=={'name':'Alice Example','city':'Cedar City','skills':'Python','years':5}
        saved['result']['city']='Maple City';saved['review_status']='reviewed';saved['reviewed_by']=actor;saved['reviewed_at']=time.time()
        saved.update(parquet_results.persist(extraction.id,extraction.version+1,saved))
        routing.write_version(extraction,saved)
        for case in [
            ('edited_saved_city','What city is currently saved in the extraction for Alice Example?',
             {'results'},{'read_extraction_results'},lambda a:has(a,'Maple City') and lacks(a,'Cedar City'),[],True),
            ('unchanged_original_city','What city is written in the original alice-example.txt document?',
             {'documents'},{'search_documents'},lambda a:has(a,'Cedar City') and lacks(a,'Maple City'),[alice],True),
        ]:evaluate(case)
    count_cases=len(report['cases'])
    report['summary']={key:{'passed':sum(bool(c['checks'].get(key)) for c in report['cases']),
        'total':count_cases,'percentage':round(100*sum(bool(c['checks'].get(key)) for c in report['cases'])/count_cases,2)}
        for key in ('answer_accuracy','tool_accuracy')}
    report['summary']['end_to_end']={'passed':sum(c['passed'] for c in report['cases']),'total':count_cases,
        'percentage':round(100*sum(c['passed'] for c in report['cases'])/count_cases,2)}
    report['completed_at']=datetime.now(timezone.utc).isoformat()
    core.local_store.put_json('diagnostics/agent-accuracy/current.json',report)
    print(json.dumps(report['summary']),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--core-report',required=True)
    run(parser.parse_args().core_report)
