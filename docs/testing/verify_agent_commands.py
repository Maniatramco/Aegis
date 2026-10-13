"""Read back browser-submitted direct routes; never confirm processing."""
import json
from sqlalchemy import select
from app import core
found={}
with core.Session() as session:
    rows=list(session.scalars(select(core.Record).where(core.Record.kind=='agent_plan',core.Record.owner=='administrator').order_by(core.Record.created_at.desc()).limit(12)))
for record in rows:
    data=core.store.json(record.ref)
    if data.get('request','').strip() not in ('@Upload','@Extract'):continue
    operation=data['request'].strip()[1:].lower()
    if operation in found:continue
    # Conversation references are authoritative metadata, not assumed paths.
    with core.Session() as session:thread=session.get(core.Record,data['conversation_id'])
    conversation=core.store.json(thread.ref)
    message=next(m for m in reversed(conversation['messages']) if m.get('request_route',{}).get('requested_operation')==operation)
    assert data['agent']=='onboard_extract' and data['model_calls']==0
    assert message['request_route']['attempts']==[] and message['request_route']['routing_mode']=='explicit'
    assert [call['tool'] for call in data['calls']]==[operation]
    assert all(call['status']=='pending' and not call.get('job_ids') for call in data['calls'])
    found[operation]={'plan_id':record.id,'routing':'explicit','model_calls':0,'calls':[operation],'phase':data['phase'],'workflow':message['answer_workflow']}
assert set(found)=={'upload','extract'},'Finish both browser shortcut submissions first.'
print(json.dumps({'passed':True,'routes':found},indent=2))
