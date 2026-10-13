"""Durable goal invariants with real storage/graph and scripted model output.
Real model intelligence is covered separately by app.agent_benchmark.
"""
import time
import pytest
from fastapi import HTTPException
from app import core, main, agent_goals, agent_graph, agent_model, providers, dataset_models as routing
from test_dataset_models import system, dataset, upload, template, post

def completed_plan(s):
    d=dataset(s);doc=upload(s,d)['documents'][0];t=template(s)
    # A saved synthetic result: no provider required for recovery invariants.
    ex=routing.create('extraction',s.owner,'Confirmed Alice',{'document_ids':[doc['id']],
        'result':{'owner':'Alice'},'review_status':'unreviewed'},parent=d['id'])
    conversation=routing.create('conversation',s.owner,'Goal thread',{'mode':'agent','dataset_id':d['id'],'messages':[]},parent=d['id'])
    model=routing.execution_snapshot(routing.owned(d['id'],s.owner,'knowledge_base'),'chat')
    data={'runtime':'langgraph','request':'Extract and summarize the owner.','dataset_id':d['id'],'document_ids':[doc['id']],
        'template_id':t['id'],'conversation_id':conversation.id,'created_at':time.time(),'planner':{'id':model['model_id'],'version':model['model_version']},
        'calls':[{'tool':'extract','status':'completed','started_at':time.time(),'result':{'extraction_id':ex.id}}]}
    agent_goals.seed(data);agent_goals.refresh(data)
    record=routing.create('agent_plan',s.owner,'Goal',data,parent=d['id'])
    return record,ex,conversation

def goal(record):return core.store.json(record.ref)['goal']

def test_finalization_reads_exact_results_cannot_propose_actions_and_deduplicates(system,monkeypatch):
    record,ex,conversation=completed_plan(system)
    monkeypatch.setattr(agent_model,'classify',lambda *a:pytest.fail('Goal finalization must not classify into a mutation'))
    seen=[]
    def complete(messages,tools):
        seen.append((messages,tools));return {'text':'Alice is the saved owner. ['+str(1)+']','calls':[]}
    monkeypatch.setattr(agent_model,'complete',complete)
    agent_goals.advance(record,main)
    assert goal(record)['status']=='completed' and goal(record)['extraction_ids']==[ex.id]
    assert goal(record)['answer']['review_actions'][0]['extraction_id']==ex.id
    assert seen[0][1]==[] and 'Alice' in str(seen[0][0])
    before=core.store.json(conversation.ref)['messages']
    agent_goals.advance(record,main);assert len(seen)==1
    # Death after the conversation commit, before the goal completion commit.
    data=core.store.json(record.ref);data['goal'].update(status='running',lease_until=0,attempts=1)
    core.store.put_json(record.ref,data);agent_goals.advance(record,main)
    assert goal(record)['status']=='completed' and len(seen)==1
    assert core.store.json(conversation.ref)['messages']==before

def test_transient_answer_failure_backs_off_and_manual_resume_never_reextracts(system,monkeypatch):
    record,ex,_=completed_plan(system);before=system.api.get('/api/jobs').json()
    def broken(*a,**kw):raise providers.ProviderError('provider temporarily unavailable')
    monkeypatch.setattr(agent_graph,'run',broken)
    for attempt in range(3):
        data=core.store.json(record.ref);data['goal']['next_attempt_at']=0;core.store.put_json(record.ref,data)
        agent_goals.advance(record,main)
        assert goal(record)['attempts']==attempt+1
        assert goal(record)['status']==('failed' if attempt==2 else 'retry_wait')
        assert goal(record)['next_attempt_at']>time.time()
    assert system.api.get('/api/jobs').json()==before
    resumed=post(system,'/api/agent-v2/plans/'+record.id+'/goal',{'action':'retry'})
    assert resumed['goal']['attempts']==0 and resumed['goal']['status']=='queued'
    assert routing.owned(ex.id,system.owner,'extraction').version==1

def test_goal_cannot_start_before_confirmation_or_processing_completion(system,monkeypatch):
    record,_,_=completed_plan(system);data=core.store.json(record.ref)
    data['calls'][0].update(status='pending');data['calls'][0].pop('started_at');data['goal']['status']='awaiting_confirmation'
    core.store.put_json(record.ref,data)
    monkeypatch.setattr(agent_graph,'run',lambda *a,**kw:pytest.fail('Unconfirmed work must never continue'))
    agent_goals.advance(record,main)
    assert goal(record)['status']=='awaiting_confirmation'
    assert system.api.post('/api/agent-v2/plans/'+record.id+'/goal',json={'action':'retry'}).status_code==409

def test_goal_pause_cancel_and_private_access(system,monkeypatch):
    record,_,_=completed_plan(system)
    assert post(system,'/api/agent-v2/plans/'+record.id+'/goal',{'action':'pause'})['goal']['status']=='paused'
    monkeypatch.setattr(agent_graph,'run',lambda *a,**kw:pytest.fail('Paused goals must not run'))
    agent_goals.advance(record,main)
    system.owner='mallory'
    assert system.api.post('/api/agent-v2/plans/'+record.id+'/goal',json={'action':'retry'}).status_code==404
    assert system.api.get('/api/agent-v2/goals').json()==[]
    system.owner='alice'
    assert post(system,'/api/agent-v2/plans/'+record.id+'/goal',{'action':'cancel'})['goal']['status']=='cancelled'
    agent_goals.advance(record,main)

def test_missing_coverage_stops_goal_without_model_or_new_jobs(system,monkeypatch):
    record,_,_=completed_plan(system);d=core.store.json(record.ref)
    extra=upload(system,routing.dataset_public(routing.owned(d['dataset_id'],system.owner,'knowledge_base')))['documents'][0]
    d['document_ids'].append(extra['id']);core.store.put_json(record.ref,d)
    monkeypatch.setattr(agent_graph,'run',lambda *a,**kw:pytest.fail('Incomplete coverage must stop before generating success'))
    agent_goals.advance(record,main)
    assert goal(record)['status']=='failed' and 'no completed result' in goal(record)['error']

def test_reading_plan_never_runs_goal_model(system,monkeypatch):
    record,_,_=completed_plan(system)
    monkeypatch.setattr(agent_graph,'run',lambda *a,**kw:pytest.fail('GET must not run inference'))
    assert system.api.get('/api/agent-v2/plans/'+record.id).json()['goal']['status']=='queued'
