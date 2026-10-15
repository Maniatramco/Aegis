"""Gemini sees concrete function parameters; canonical route guards remain strict."""
import copy
import pytest
from ags_app import core, agent_model
from ags_app.ags_models.providers.ags_gcp import gemini
from ags_app.ags_models.validation import temporary_credentials
from ags_app.ags_models.validation import ConnectionError
from ags_app.ags_models.connection import ModelConnection
from test_ocr_cloud import snapshot


def test_gemini_routing_wire_declares_all_branches_and_forces_tool_call(monkeypatch):
    request='What total and approval code are in invoice.txt?'
    pinned=snapshot();seen=[]
    def post(self,path,payload,headers=None):
        seen.append(copy.deepcopy(payload))
        assert core._execution.get()['secret_refs']==pinned['secret_refs']
        name=next(t['function']['name'] for t in payload['tools'] if 'original' in t['function']['parameters']['properties'].get('query',{}).get('enum',[]))
        return {'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{
            'id':'route-1','type':'function','function':{'name':name,'arguments':__import__('json').dumps({
                'agent':'chat','query':'original','document_names':['invoice.txt'],'request_evidence':request})}}]}}]}
    monkeypatch.setattr(ModelConnection,'post',post)
    with core.execution_context(pinned),temporary_credentials({'api_key':'unit-test-only'}):
        frame=agent_model.classify_vector([{'role':'user','content':request}])
    assert frame['source']=='documents' and frame['document_names']==['invoice.txt']
    payload=seen[0];params=payload['tools'][4]['function']['parameters']
    assert payload['tool_choice']=='required' and 'oneOf' not in params
    assert len(payload['tools'])==5 and params['properties']['agent']['enum']==['chat']
    assert {'original','results','application'}<=set(params['properties']['query']['enum'])
    assert params['required']==['agent','query','request_evidence']
    assert 'include_original' not in params['properties']


def test_wire_flattening_never_mutates_local_validation_schema():
    source=[{'type':'function','function':{'name':'route','parameters':{'oneOf':[
        {'type':'object','properties':{'agent':{'const':'chat'}},'required':['agent']},
        {'type':'object','properties':{'agent':{'const':'clarify'}},'required':['agent']}]}}}]
    original=copy.deepcopy(source)
    wire=gemini.agent_tools(source)
    assert len(wire)==2 and wire[0]['function']['parameters']['properties']['agent']['enum']==['chat']
    assert wire[1]['function']['parameters']['properties']['agent']['enum']==['clarify']
    assert source==original


def test_branch_return_cannot_include_fields_from_another_route():
    tools=[{'type':'function','function':{'name':'route','parameters':{'oneOf':[
        {'type':'object','properties':{'agent':{'const':'chat'}},'required':['agent'],'additionalProperties':False},
        {'type':'object','properties':{'agent':{'const':'action'},'operation':{'const':'extract'}},'required':['agent','operation'],'additionalProperties':False}]}}}]
    with pytest.raises(ConnectionError,match='invalid function arguments'):
        gemini.agent_calls([{'name':'route__branch_0','arguments':{'agent':'chat','operation':'extract'}}],tools)
    with pytest.raises(ConnectionError,match='undeclared function'):
        gemini.agent_calls([{'name':'invented','arguments':{}}],tools)


def test_plain_tool_contract_keeps_its_name_and_arguments():
    tools=[{'type':'function','function':{'name':'status','parameters':{'type':'object','properties':{'ready':{'type':'boolean'}},'required':['ready']}}}]
    calls=[{'id':'one','name':'status','arguments':{'ready':True}}]
    assert gemini.agent_tools(tools)==tools and gemini.agent_calls(calls,tools)==calls
