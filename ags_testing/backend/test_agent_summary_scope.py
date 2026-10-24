"""Summary routing must reach scoped retrieval, never a processing workflow."""
import json
import pytest
from ags_app import core,knowledge,agent_model,dataset_models as routing
from test_dataset_models import system,dataset,upload
from test_agent_workspace import plan
from test_chat_hybrid_required import install_models


@pytest.mark.parametrize('question,query',[
    ('hi can you extract summary from the knowledge base','mixed'),
    ('Summarize the selected dataset.','mixed'),
    ('summary','mixed'),
    ('summarize','mixed'),
    ('Summarize the original documents.','original'),
    ('Give me a summary of the saved extraction results.','results'),
])
@pytest.mark.parametrize('selected_document',[False,True])
def test_summary_uses_current_scope_and_full_grounded_pipeline(system,monkeypatch,question,query,selected_document):
    s=system;d=dataset(s,'Balance Sheet');chosen=upload(s,d)['documents'][0]
    other=upload(s,d)['documents'][0]
    foreign=dataset(s,'Other dataset');upload(s,foreign)
    routing.create('extraction',s.owner,'Saved balance',
        {'document_ids':[chosen['id']],'result':{'owner':'Alice','assets':7000}},parent=d['id'])
    knowledge.sync(s.owner,d['id']);knowledge.sync(s.owner,foreign['id'])
    events=install_models(monkeypatch);answer=agent_model.complete;routes=[]
    def complete(messages,tools,**kwargs):
        if not tools:return answer(messages,tools,**kwargs)
        routes.append(messages)
        # The routing model is simulated here; the regression checks that even
        # bare summaries reach it instead of assuming a missing previous answer.
        instruction=messages[0]['content']
        assert 'A broad summary/overview is a complete information request' in instruction
        assert '"Extract a summary" means a read-only chat summary' in instruction
        return {'calls':[{'name':'route_aegis','arguments':{
            'agent':'chat','query':query,'answer_kind':'summary',
            'scope_reference':'current_selection','result_scope':'selected_scope',
            'request_evidence':question}}]}
    monkeypatch.setattr(agent_model,'complete',complete)
    response=plan(s,d,text=question,document_ids=[chosen['id']] if selected_document else [])
    assert routes and response['agent']=='chat' and not response['calls']
    assert [event[0] for event in events]==['rerank','answer']
    reply=core.store.json(routing.owned(response['conversation_id'],s.owner,'conversation').ref)['messages'][-1]
    trace=reply['tool_trace'][0]['result']
    assert trace['scope']['dataset_id']==d['id']
    assert trace['retrieval']['mode']=='hybrid' and trace['retrieval']['reranker_enabled']
    assert trace['answer_check']=='passed' and reply['citations']
    assert all(dataset_id==d['id'] for event,dataset_ids in events if event=='rerank' for dataset_id in dataset_ids)
    if selected_document:
        assert other['id'] not in json.dumps(trace['records'])
        assert {c['document_id'] for c in reply['citations'] if c.get('document_id')}=={chosen['id']}
    assert 'Which document' not in response['explanation']
