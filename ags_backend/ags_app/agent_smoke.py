"""Explicit operator smoke: real graph proposal and real local extraction.

Uses an isolated QA dataset. Does not confirm uploads or submit worker jobs.
Override AEGIS_OLLAMA_URL to test a CPU-only model container independently.
"""
import json
import os
import time
from . import core, main, agent_graph, dataset_models as routing, providers
from .agent_workspace import PlanInput
from .container_smoke import call


def run():
    qa=json.loads(core.secret_cipher().decrypt(core.local_store.get('diagnostics/langgraph-ui-auth.enc')))
    with core.Session() as db:dataset=db.get(core.Record,os.environ.get('AEGIS_AGENT_SMOKE_DATASET',qa['dataset_id']))
    templates=[t for t in routing.rows(dataset.owner,'template') if t.parent_id==dataset.id]
    if not templates:raise RuntimeError('Save the fictional QA prompt first.')
    snapshot=routing.execution_snapshot(dataset,'chat',qa['model_id'])
    snapshot['settings'].update(model_provider='ollama',model=os.environ.get('AEGIS_MODEL','qwen3:4b'),context_limit=8192,max_output_tokens=1024,timeout=300)
    snapshot['settings'].pop('model_connection',None)
    started=time.monotonic()
    body=PlanInput(text='Extract the attached resume with my selected prompt.',planner_model_id=qa['model_id'],
        dataset_id=dataset.id,template_id=templates[0].id,attached_filenames=['fictional-cpu-smoke.pdf'])
    outcome=agent_graph.run(dataset.owner,body,snapshot,main)
    if [c['tool'] for c in (outcome.get('proposal') or {}).get('calls',[])]!=['upload','extract']:
        raise RuntimeError('The real agent did not propose the requested upload/extraction chain.')
    proposal_seconds=round(time.monotonic()-started,2)
    schema={'type':'object','properties':{'name':{'type':'string'}},'required':['name'],'additionalProperties':False}
    with core.execution_context(snapshot):value=providers.extract('Fictional resume. Candidate name: Alice Example.',schema)
    if value!={'name':'Alice Example'}:raise RuntimeError('The real extraction did not return the known fictional value.')
    loaded=call(os.environ.get('AEGIS_OLLAMA_URL','http://ollama:11434'),'/api/ps',timeout=10).get('models',[])
    vram=sum(int(m.get('size_vram',0)) for m in loaded)
    result={'passed':True,'model':snapshot['settings']['model'],'hardware':'GPU offload' if vram else 'CPU',
        'size_vram_bytes':vram,'proposal_seconds':proposal_seconds,'total_seconds':round(time.monotonic()-started,2),
        'confirmed':False,'worker_jobs_submitted':0,'conversation_id':outcome['conversation_id']}
    print(json.dumps(result));return result

if __name__=='__main__':run()
