"""Read persisted browser Chat Agent evidence, without modifying any workflow."""
import json
from sqlalchemy import select
from app import core,dataset_access,chat_knowledge

conversation_id='770958d7-4a35-46c1-89da-a6fb8b76ba65'
actor=dataset_access.request_actor.set('administrator')
try:
    with core.Session() as session:
        record=session.get(core.Record,conversation_id)
    assert record and record.owner=='administrator'
    data=core.store.json(record.ref)
    answers=[]
    for message in data['messages']:
        if message['role']!='assistant':continue
        answers.append({key:message.get(key) for key in ('text','status','request_route','tool_trace','answer_workflow','review_actions')})
        assert [t['tool'] for t in message.get('tool_trace',[])]==['query_unified_knowledge']
    view=chat_knowledge.PublishedKnowledge('administrator',data['dataset_id'])
    filenames=[r['value']['filename'] for r in chat_knowledge.assemble(view.catalog(['document']))]
    assert filenames==['maya-rao-sample-resume.pdf']
    print(json.dumps({'conversation_id':conversation_id,'dataset_id':data['dataset_id'],
        'provider':view.snapshot['settings']['search_provider'],'filenames':filenames,'answers':answers},indent=2))
finally:dataset_access.request_actor.reset(actor)
