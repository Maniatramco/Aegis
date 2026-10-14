"""Chat caps are configurable and do not override narrower model limits."""
import json
import pytest
from fastapi import HTTPException
from ags_app import chat_agent,knowledge,agent_model,core,dataset_models as routing
from test_dataset_models import system,dataset
from test_agent_workspace import plan
from test_chat_hybrid_required import install_models


def test_default_and_profile_limits(monkeypatch):
    for key in ('AEGIS_CHAT_CONTEXT_TOKENS','AEGIS_CHAT_EVIDENCE_BYTES','AEGIS_CHAT_OUTPUT_TOKENS'):monkeypatch.delenv(key,raising=False)
    settings={'context_limit':262144,'max_output_tokens':1024}
    assert chat_agent.chat_limits(settings)=={'context_tokens':16384,'output_tokens':1024,'evidence_bytes':22000}
    assert settings=={'context_limit':262144,'max_output_tokens':1024}
    assert chat_agent.chat_limits({'context_limit':4096,'max_output_tokens':512})['context_tokens']==4096
    monkeypatch.setenv('AEGIS_CHAT_CONTEXT_TOKENS','32768');monkeypatch.setenv('AEGIS_CHAT_EVIDENCE_BYTES','40000')
    assert chat_agent.chat_limits(settings)=={'context_tokens':32768,'output_tokens':1024,'evidence_bytes':40000}


@pytest.mark.parametrize('value',['-1','abc','1000001'])
def test_invalid_evidence_cap_is_rejected(monkeypatch,value):
    monkeypatch.setenv('AEGIS_CHAT_EVIDENCE_BYTES',value)
    with pytest.raises(HTTPException,match='budget configuration'):chat_agent.chat_limits({})


@pytest.mark.parametrize('size,allowed',[(14000,True),(23000,False)])
def test_new_evidence_band_reaches_model_without_discarding_fields(system,monkeypatch,size,allowed):
    s=system;d=dataset(s)
    monkeypatch.setattr(knowledge,'GUIDE',{'knowledge':'Aegis guidance '+('x'*size)})
    knowledge.sync(s.owner,d['id']);install_models(monkeypatch)
    monkeypatch.setattr(agent_model,'classify',lambda _:dict(intent='answer',source='application'))
    seen=[]
    def answer(messages,tools,**kw):
        request=next(m['content'] for m in messages if m['role']=='user' and 'Published vector evidence:' in m['content'])
        evidence=json.loads(request.split('Published vector evidence:\n',1)[1]);seen.append(evidence)
        assert evidence['records'][0]['data'].endswith('x'*size)
        return {'text':'Aegis guidance is available [1].','calls':[]}
    monkeypatch.setattr(agent_model,'complete',answer)
    result=plan(s,d,text='Explain the Aegis guidance.')
    if allowed:
        assert len(seen)==1 and 'guidance is available' in result['explanation']
        reply=core.store.json(routing.owned(result['conversation_id'],s.owner,'conversation').ref)['messages'][-1]
        assert reply['tool_trace'][0]['result']['chat_budget']['context_tokens']==16384
    else:
        assert not seen and '22,000 bytes' in result['explanation']


def test_single_prompt_keeps_full_schema_without_duplicate_facts(system,monkeypatch):
    s=system;d=dataset(s)
    schema={'type':'object','properties':{'amount':{'type':'number','description':'Read the stated amount.'}}}
    instructions='Never invent absent values.'
    prompt=routing.create('template',s.owner,'Budget prompt',{'schema':schema,'instructions':instructions,'source_filename':'budget.json'},parent=d['id'])
    knowledge.sync(s.owner,d['id']);install_models(monkeypatch)
    monkeypatch.setattr(agent_model,'classify',lambda _:dict(intent='answer',source='prompt'))
    def answer(messages,tools,**kw):
        content=next(m['content'] for m in messages if m['role']=='user' and 'Published vector evidence:' in m['content'])
        evidence=json.loads(content.split('Published vector evidence:\n',1)[1])
        assert 'verified_catalog_facts' not in evidence
        assert evidence['records'][0]['data']['schema']==schema
        assert evidence['records'][0]['data']['instructions']==instructions
        return {'text':'Read the amount without inventing values [1].','calls':[]}
    monkeypatch.setattr(agent_model,'complete',answer)
    result=plan(s,d,text='Explain this prompt.',template_id=prompt.id)
    assert 'without inventing' in result['explanation']
