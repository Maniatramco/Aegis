"""Read back the real browser QA answers and server-reported step timings."""
import json
from app import core,main
record=main.get_record('d99b7b6a-e14b-4759-8e30-493d3de774d9','administrator','conversation')
data=core.store.json(record.ref)
results=[]
for index,message in enumerate(data['messages']):
    if message.get('role')!='assistant':continue
    question=data['messages'][index-1].get('text','')
    if question not in ('How many documents are in this dataset?','Summarize the saved extraction named Resume re-extract verification.'):continue
    assert message['status']=='completed'
    workflow=message['answer_workflow']
    assert workflow['steps'][0]['label']=='Checking agent configuration'
    assert all(step['status']=='completed' for step in workflow['steps'])
    answer=message['text']
    if question.startswith('How many'):assert '1 document' in answer
    else:assert 'Maya Rao' in answer and '8' in answer and 'B.Tech' in answer
    results.append({'question':question,'answer':answer,'workflow_seconds':round(sum(s['duration_ms'] for s in workflow['steps'])/1000,3),'steps':workflow['steps'],'route':message['request_route'].get('decision'),'citations':len(message['citations'])})
assert len(results)>=3,'Finish the browser summary question before this verification.'
print(json.dumps({'passed':True,'cases':results},indent=2))
