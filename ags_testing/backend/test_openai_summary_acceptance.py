"""Opt-in real-provider acceptance using synthetic, disposable local state.

Invoke pytest directly with AEGIS_TEST_OPENAI_SUMMARY=true and an authorized
TASK_OPENAI_PROBE_KEY in memory. The isolated offline runner disables this test.
Embeddings and reranking are test doubles; OpenAI routing/generation are real.
"""
import os
import pytest
from ags_app import core,knowledge,reranker,worker,main,agent_model
from test_dataset_models import system,dataset
from test_model_registration import body,register,select
from test_agent_workspace import plan

pytestmark=pytest.mark.skipif(os.getenv('AEGIS_TEST_OPENAI_SUMMARY')!='true',
    reason='Opt-in real OpenAI acceptance with synthetic local state')


@pytest.mark.parametrize('model_name',['gpt-4o','gpt-4o-mini'])
@pytest.mark.parametrize('question',[
    'hi can you extract summary from the knowledge base',
    'summary',
    'Summarize the original documents.',
])
def test_real_summary(system,monkeypatch,model_name,question):
    s=system;d=dataset(s,'Balance Sheet')
    response=s.api.post('/api/documents/upload',files={'files':('Fictional-Balance-Sheet.txt',
        b'SYNTHETIC EXAMPLE. Cedar Demo balance sheet as of 31 March 2026. Currency USD thousands. Total assets: 7000. Total liabilities: 4000. Total equity: 3000. Assets equal liabilities plus equity. Prior year assets: 6300. This is fictional test data.','text/plain')},
        data={'dataset_id':d['id'],'allow_external':'true'})
    assert response.status_code==200 and worker.run_once()
    value=body(protocol='openai-compatible',provider_model=model_name,context_limit=128000,max_output_tokens=2048)
    value['credentials']={'api_key':os.environ['TASK_OPENAI_PROBE_KEY']}
    model=register(s,value);select(s,d,model,'chat');knowledge.sync(s.owner,d['id'])
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setenv('AEGIS_CHAT_AGENT_VECTOR_ONLY','true')
    monkeypatch.setenv('AEGIS_RERANKER','local')
    ranked=[]
    monkeypatch.setattr(reranker,'rank',lambda q,items,limit:(ranked.append(items) or items[:limit]))
    original=agent_model.classify_vector;routes=[]
    def classify(messages):
        frame=original(messages);routes.append(frame);return frame
    monkeypatch.setattr(agent_model,'classify_vector',classify)
    result=plan(s,d,text=question,planner_model_id=model['id'],allow_external=True)
    assert result['agent']=='chat',result.get('explanation')
    reply=core.store.json(main.get_record(result['conversation_id'],s.owner,'conversation').ref)['messages'][-1]
    trace=reply['tool_trace'][0]['result']
    assert reply['answer_workflow']['status']=='completed'
    assert ranked and trace['retrieval']['mode']=='hybrid'
    assert trace['answer_check']=='passed' and reply['citations']
    assert trace['scope']['dataset_id']==d['id']
    assert any(r['type']=='document_chunk' for r in trace['records'])
    assert '7,000' in reply['text'] or '7000' in reply['text']
    assert routes[0]['intent']=='answer' and routes[0]['scope_reference']=='current_selection'
