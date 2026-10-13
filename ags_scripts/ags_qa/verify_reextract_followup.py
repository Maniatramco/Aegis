"""Read persisted browser proof of the named updated-result answer."""
import json
from ags_app import core,dataset_access
actor=dataset_access.request_actor.set('administrator')
try:
    record=dataset_access.get_record('55450c7b-0d5d-46ac-8d12-dc4debdf109c','administrator','conversation')
    message=core.store.json(record.ref)['messages'][-1]
    expected='220d33d7-b58c-43eb-a22c-35de309acde8'
    assert message['role']=='assistant' and message['status']=='completed'
    assert 'B.Tech in Computer Science' in message['text']
    assert [t['tool'] for t in message['tool_trace']]==['query_unified_knowledge']
    assert {a['extraction_id'] for a in message['review_actions']}=={expected}
    evidence=message['tool_trace'][0]['result']
    assert evidence['knowledge_provider']=='oracle'
    assert all(r['id'].split(':')[0]==expected for r in evidence['records'])
    print(json.dumps({'passed':True,'conversation_id':record.id,'answer':message['text'],
        'route':message['request_route'],'workflow':message['answer_workflow'],
        'review_actions':message['review_actions'],'tool_trace':message['tool_trace']},indent=2))
finally:dataset_access.request_actor.reset(actor)
