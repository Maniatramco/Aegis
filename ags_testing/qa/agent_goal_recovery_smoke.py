"""Explicit synthetic-data fault injection, isolated to this CLI process.

Stop the worker while creating the fixture. Resume through the browser and
restart the worker. This never changes a model registration or network config.
"""
import argparse
import json
import time
from unittest.mock import patch
from ags_app import core, main, agent_graph, agent_goals, dataset_models as routing

def run(plan_id):
    with core.Session() as session:source=session.get(core.Record,plan_id)
    if not source or source.kind!='agent_plan':raise ValueError('Choose a completed synthetic benchmark plan')
    saved=core.store.json(source.ref)
    dataset=routing.owned(saved['dataset_id'],source.owner,'knowledge_base')
    if not dataset.name.startswith('Agent reliability ') or saved.get('goal',{}).get('status')!='completed':
        raise ValueError('Fault injection is limited to completed Agent reliability fixtures')
    ids=agent_goals.extraction_ids(saved)
    if len(ids)!=2:raise ValueError('The fixture requires two completed benchmark results')
    conversation=routing.create('conversation',source.owner,'Synthetic recovery check',{'mode':'agent','dataset_id':dataset.id,'messages':[]},parent=dataset.id)
    data={k:saved[k] for k in ('runtime','request','dataset_id','document_ids','template_id','planner','calls')}
    data.update(conversation_id=conversation.id,created_at=time.time(),workflow_allow_external=False,chat={'text':'Saved benchmark results are retained for this recovery check.','status':'completed','citations':[]})
    agent_goals.seed(data);agent_goals.refresh(data)
    record=routing.create('agent_plan',source.owner,'Synthetic goal recovery check',data,parent=dataset.id)
    def unavailable(*a,**kw):raise agent_goals.providers.ProviderError('Synthetic provider outage')
    with patch.object(agent_graph,'run',unavailable):
        for attempt in range(3):
            current=core.store.json(record.ref)
            remaining=current['goal'].get('next_attempt_at',0)-time.time()
            if remaining>0:time.sleep(remaining+.05)
            agent_goals.advance(record,main)
            print(json.dumps({'attempt':attempt+1,'status':core.store.json(record.ref)['goal']['status']}),flush=True)
    report={'plan_id':record.id,'dataset_id':dataset.id,'extraction_ids':ids,'fault_injection':'CLI-local synthetic ProviderError',
            'passed':core.store.json(record.ref)['goal']['status']=='failed'}
    core.local_store.put_json('diagnostics/agent-goal-recovery.json',report)
    print(json.dumps(report),flush=True)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True)
    raise SystemExit(0 if run(parser.parse_args().plan)['passed'] else 1)
