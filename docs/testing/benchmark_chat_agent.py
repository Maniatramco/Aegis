"""Real-model, live Oracle-vector Chat Agent checks on the fictional resume.
No workflow confirmations or file changes. Audit request-time business reads.
"""
import json,time
from sqlalchemy import select
from app import core,main,knowledge,dataset_access,dataset_models,agent_graph,agent_model,providers,parquet_results
from app.agent_workspace import PlanInput

owner='administrator'
actor=dataset_access.request_actor.set(owner)
with core.Session() as session:
    d=session.scalar(select(core.Record).where(core.Record.kind=='knowledge_base',core.Record.name=='Resume Agent Verification'))
snapshot=dataset_models.execution_snapshot(d,'chat')
body={'dataset_id':d.id,'planner_model_id':snapshot['model_id'],'allow_external':True}
counts={};original_json=core.store.json;original_embed=providers.embed;original_complete=agent_model.complete
original_sync=knowledge.sync;original_hydrate=knowledge.hydrate;original_load=parquet_results.load
def read(ref):
    if ref.startswith(('documents/','extraction/','template/')):counts['business_file_reads']+=1
    return original_json(ref)
def embed(*a,**kw):counts['embedding_calls']+=1;return original_embed(*a,**kw)
def complete(*a,**kw):counts['answer_calls']+=1;return original_complete(*a,**kw)
def forbidden(*a,**kw):raise AssertionError('Chat attempted request-time sync, hydration or Parquet reads.')
core.store.json=read;providers.embed=embed;agent_model.complete=complete
knowledge.sync=forbidden;knowledge.hydrate=forbidden;parquet_results.load=forbidden
cases=[
    ('count','How many documents are in this dataset?',lambda text:'1 document' in text),
    ('filenames','Can you list me the douccments name available for this dataset?',lambda text:'maya-rao-sample-resume.pdf' in text),
    ('saved_identity','What is the extracted full name and total experience years?',lambda text:'Maya Rao' in text and '8' in text),
    ('saved_skills','List the extracted skills.',lambda text:all(word in text for word in ('Python','SQL','Docker'))),
    ('models','Which models are mapped to this dataset?',lambda text:all(word in text for word in ('Nomic','Qwen3 Chat','Qwen3 Extraction'))),
    ('original','What email and professional title are written in the original resume?',lambda text:'maya.rao@example.com' in text.lower() and 'Senior Data Engineer' in text),
    ('semantic','Semantically find the saved extracted profile about Python data engineering.',lambda text:'Maya Rao' in text and 'Python' in text),
]
report={'dataset_id':d.id,'model':snapshot['settings']['model'],'provider':core.settings()['search_provider'],'cases':[]}
try:
    for name,question,grade in cases:
        counts={'business_file_reads':0,'embedding_calls':0,'answer_calls':0}
        start=time.perf_counter();result=agent_graph.run(owner,PlanInput(text=question,**body),snapshot,main)
        message=result['message'];answer=message['text']
        trace=[o['tool'] for o in message['tool_trace']]
        passed=grade(answer) and trace==['query_unified_knowledge'] and counts['business_file_reads']==0
        report['cases'].append({'case':name,'question':question,'passed':passed,'seconds':round(time.perf_counter()-start,3),
            'model_calls':result['model_calls'],'request_counts':dict(counts),'answer':answer,
            'tools':trace,'route':message['request_route'],'workflow':message['answer_workflow'],
            'review_actions':message['review_actions'],'conversation_id':result['conversation_id']})
    report['passed']=sum(c['passed'] for c in report['cases']);report['total']=len(cases)
    print(json.dumps(report,indent=2))
finally:
    core.store.json=original_json;providers.embed=original_embed;agent_model.complete=original_complete
    knowledge.sync=original_sync;knowledge.hydrate=original_hydrate;parquet_results.load=original_load
    dataset_access.request_actor.reset(actor)
