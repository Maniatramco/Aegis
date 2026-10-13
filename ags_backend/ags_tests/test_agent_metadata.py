"""Actual graph/tools/storage with scripted decisions; live model checked in browser."""
import json
import pytest
from fastapi import HTTPException
from ags_app import core, main, agent_model, dataset_models as routing
from ags_app.agent_tools import Tools
from ags_app.agent_workspace import PlanInput
from test_dataset_models import system, dataset, upload
from test_agent_workspace import plan
from test_agent_chat import reply
from test_chat_stream import events
from test_agent_graph import tool


def frame(source='metadata',**kw):
    return dict(intent='answer',source=source,operation='none',fields=[],document_names=[],
        answer_kind='list',filters=[],result_scope='selected_scope')|kw


def tools_for(s,d,**kw):
    return Tools(s.owner,PlanInput(text='List files',dataset_id=d['id'],
        planner_model_id=next(m['id'] for m in d['models'] if 'chat' in m['capabilities']),**kw),'test',main)


def document(s,d,name,status='ready'):
    r=routing.create('document',s.owner,name,{},parent=d['id'])
    with core.Session.begin() as db:db.get(core.Record,r.id).status=status
    return r


def test_document_metadata_includes_unextracted_failed_and_queued_files_and_paginates(system):
    s=system;d=dataset(s);other=dataset(s,'Other');expected={document(s,d,f'file-{i}.txt',['ready','queued','failed'][i%3]).id for i in range(43)}
    hidden=document(s,other,'other.txt');tools=tools_for(s,d)
    pages=[tools.list_documents(offset=n) for n in (0,20,40)]
    assert [p['next_offset'] for p in pages]==[20,40,None]
    assert all(p['document_count']==43 for p in pages)
    found={r['id'] for page in pages for r in page['documents']}
    assert found==expected and hidden.id not in found
    assert {r['status'] for page in pages for r in page['documents']}=={'ready','queued','failed'}
    assert tools.find_extractions()['total']==0
    assert pages[0]['processing_summary']['extraction_status_counts']=={}
    assert pages[0]['processing_summary']['document_count']==43
    assert 'not extraction completion' in pages[0]['document_status_meaning']
    status=tools.get_dataset_status()
    assert len(status['document_names'])==20 and status['document_names_complete'] is False
    assert hidden.name not in status['document_names']
    scoped=tools_for(s,d,document_ids=[next(iter(expected))])
    assert scoped.list_documents()['document_count']==1
    with pytest.raises(HTTPException):tools_for(s,d,document_ids=[hidden.id]).list_documents()


def test_status_models_and_help_are_read_only_and_do_not_leak_connection_data(system):
    s=system;d=dataset(s);upload(s,d,run=False);tools=tools_for(s,d)
    jobs=s.api.get('/api/jobs').json()
    state=tools.get_dataset_status()
    assert state['document_status_counts']=={'queued':1} and state['active_job_count']==1
    assert state['document_names']==['invoice.txt'] and state['document_names_complete'] is True
    assert 'IDs are not filenames' in state['filename_list_notice']
    assert state['recent_jobs'][0]['status']=='queued'
    models=tools.get_model_configuration()
    assert models['default_roles']['chat']==d['default_chat_model_id']
    assert all(set(m)<=set(['id','name','version','provider_model','capabilities','enabled','mapping_enabled','context_limit','max_output_tokens']) for m in models['models'])
    assert all(m['context_limit']>0 for m in models['models'])
    help=tools.get_application_info('documents',include_api=True)
    assert any(e['operation']=='POST /api/documents/upload' for e in help['entries'])
    assert tools.get_application_info()['source']=='Aegis built-in application documentation'
    assert 'Extraction Review' in tools.get_application_info('review')['user_guide']['review']
    assert 'Save changes' in tools.get_application_info('review')['user_guide']['review']
    assert tools.get_application_info('review')['entries']==[]
    assert s.api.get('/api/jobs').json()==jobs


def test_status_respects_merged_document_scope_and_metadata_permissions(system):
    s=system;d=dataset(s);a=document(s,d,'one.txt');b=document(s,d,'two.txt');merged=document(s,d,'merged.pdf')
    routing.create('extraction',s.owner,'Merged result',{'document_ids':[a.id,b.id],
        'merge':{'document_id':merged.id,'sources':[{'document_id':a.id},{'document_id':b.id}]},'result':{}},parent=d['id'])
    assert tools_for(s,d,document_ids=[merged.id]).get_dataset_status()['extraction_status_counts']=={'ready':1}
    assert tools_for(s,d,document_ids=[a.id]).get_dataset_status()['extraction_status_counts']=={}
    hidden=routing.create('knowledge_base','another-owner','Private dataset',{},parent='')
    assert hidden.id not in {r['id'] for r in tools_for(s,d).list_datasets()['datasets']}
    s.owner='another-owner'
    with pytest.raises(HTTPException):tools_for(s,d).list_documents()


def test_chat_agent_selects_metadata_tool_and_route_is_saved(system,monkeypatch):
    s=system;d=dataset(s);document(s,d,'available.txt');seen=[]
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:frame())
    def complete(messages,contracts,**kwargs):
        seen.append(messages)
        names={c['function']['name'] for c in contracts}
        assert not {'prepare_workflow','prepare_recovery'} & names
        assert 'available_result_fields' not in messages[0]['content']
        if len(seen)==1:
            assert not {'find_extractions','read_extraction_results'} & names
            return tool('list_documents')
        assert 'list_documents' not in names  # The complete catalog cannot loop.
        observed=json.loads(next(m['content'] for m in messages if m.get('tool_name')=='list_documents'))
        return {'text':'Available files: '+', '.join(d['name'] for d in observed['documents']),'calls':[]}
    monkeypatch.setattr(agent_model,'complete',complete)
    before=s.api.get('/api/jobs').json()
    p=plan(s,d,text='can you list me douccments name available for this dataset')
    answer=events(reply(s,p))[-1]['message']
    assert 'available.txt' in answer['text'] and not answer['citations']
    assert [o['tool'] for o in answer['tool_trace']]==['list_documents']
    assert answer['request_route']['decision']['source']=='metadata'
    assert s.api.get('/api/jobs').json()==before


def test_failed_initial_metadata_read_returns_to_tool_repair(system,monkeypatch):
    s=system;d=dataset(s);document(s,d,'file.txt');reads=[];seen=[]
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:frame(initial_reads=['list_documents']))
    original=Tools.list_documents
    def read(self,**kwargs):
        reads.append(kwargs)
        if len(reads)==1:raise HTTPException(503,'Temporary metadata read failure')
        return original(self,**kwargs)
    monkeypatch.setattr(Tools,'list_documents',read)
    def complete(messages,contracts,**kwargs):
        seen.append(messages)
        if len(seen)==1:
            assert 'list_documents' in {c['function']['name'] for c in contracts}
            assert any('Temporary metadata read failure' in m['content'] for m in messages if m['role']=='tool')
            return tool('list_documents')
        assert 'list_documents' not in {c['function']['name'] for c in contracts}
        return {'text':'file.txt','calls':[]}
    monkeypatch.setattr(agent_model,'complete',complete)
    answer=events(reply(s,plan(s,d,text='List filenames')))[-1]['message']
    assert len(seen)==2 and len(reads)==2
    assert answer['tool_trace'][0]['result']['error']
    assert not answer['tool_trace'][1]['result'].get('error')


def test_semantic_initial_metadata_reads_skip_duplicate_selection_and_keep_scope(system,monkeypatch):
    s=system;d=dataset(s);other=dataset(s,'Other')
    visible=document(s,d,'visible.txt');document(s,other,'private.txt');seen=[]
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:frame(
        initial_reads=['list_documents','get_dataset_status']))
    def complete(messages,contracts,**kwargs):
        seen.append(messages)
        assert contracts==[]
        reads={m['tool_name']:json.loads(m['content']) for m in messages if m['role']=='tool'}
        assert [r['id'] for r in reads['list_documents']['documents']]==[visible.id]
        assert reads['get_dataset_status']['document_count']==1
        assert 'private.txt' not in json.dumps(reads)
        return {'text':'visible.txt is available.','calls':[]}
    monkeypatch.setattr(agent_model,'complete',complete)
    before=s.api.get('/api/jobs').json()
    answer=events(reply(s,plan(s,d,text='List filenames and their processing status')))[-1]['message']
    assert len(seen)==1
    assert [o['tool'] for o in answer['tool_trace']]==['list_documents','get_dataset_status']
    assert s.api.get('/api/jobs').json()==before


def test_initial_metadata_reads_still_require_all_catalog_pages(system,monkeypatch):
    s=system;d=dataset(s)
    for i in range(23):document(s,d,f'file-{i}.txt')
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:frame(initial_reads=['list_documents']))
    seen=[]
    def complete(messages,contracts,**kwargs):
        seen.append(messages)
        if len(seen)==1:
            assert 'list_documents' in {c['function']['name'] for c in contracts}
            return tool('list_documents',offset=20)
        assert contracts==[]
        pages=[json.loads(m['content']) for m in messages if m.get('tool_name')=='list_documents']
        assert sum(len(p['documents']) for p in pages)==23
        return {'text':'There are 23 documents.','calls':[]}
    monkeypatch.setattr(agent_model,'complete',complete)
    answer=events(reply(s,plan(s,d,text='List every filename')))[-1]['message']
    assert len(seen)==2 and len(answer['tool_trace'])==2


def test_semantic_count_uses_fresh_authorized_total_without_answer_generation(system,monkeypatch):
    s=system;d=dataset(s);other=dataset(s,'Private')
    for i in range(23):document(s,d,f'file-{i}.txt')
    document(s,other,'hidden.txt')
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:frame(answer_kind='count',
        initial_reads=['list_documents'],metadata_answer='document_count'))
    monkeypatch.setattr(agent_model,'complete',lambda *a,**kw:pytest.fail('Verified count does not need answer generation'))
    first=events(reply(s,plan(s,d,text='How many documents are available?')))[-1]['message']
    assert first['text']=='There are 23 documents in this dataset.'
    assert first['tool_trace'][0]['result']['next_offset']==20
    document(s,d,'new.txt')
    second=events(reply(s,plan(s,d,text='What is the number of available documents?')))[-1]['message']
    assert second['text']=='There are 24 documents in this dataset.'


def test_application_help_composes_after_one_topic_read_without_repeating_tools(system,monkeypatch):
    s=system;d=dataset(s);seen=[]
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:frame('application',answer_kind='other'))
    def complete(messages,contracts,**kwargs):
        seen.append(messages)
        if len(seen)==1:
            assert {c['function']['name'] for c in contracts}=={'get_application_info'}
            return tool('get_application_info',topic='review')
        assert contracts==[]
        reads=[m for m in messages if m.get('tool_name')=='get_application_info']
        assert len(reads)==1
        assert 'Save changes' in json.loads(reads[0]['content'])['user_guide']['review']
        return {'text':'Open the saved result in Review, edit the fields, then use Save changes.','calls':[]}
    monkeypatch.setattr(agent_model,'complete',complete)
    before=s.api.get('/api/jobs').json()
    answer=events(reply(s,plan(s,d,text='How do I open Review and save edited fields?')))[-1]['message']
    assert len(seen)==2
    assert [o['tool'] for o in answer['tool_trace']]==['get_application_info']
    assert s.api.get('/api/jobs').json()==before


@pytest.mark.parametrize('route',[
    frame(initial_reads=['prepare_workflow']),
    frame(initial_reads=['list_documents'],supplementary_sources=['results']),
    frame(initial_reads=['list_documents'],document_names=['specific.txt']),
])
def test_initial_reads_cannot_bypass_normal_argument_and_source_selection(system,monkeypatch,route):
    s=system;d=dataset(s);document(s,d,'available.txt');seen=[]
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:route)
    def complete(messages,contracts,**kwargs):
        seen.append(messages)
        assert not any(m['role']=='tool' for m in messages)
        assert contracts
        # Stop after confirming the normal tool agent is required, avoiding a
        # synthetic answer that pretends an unperformed read succeeded.
        raise main.providers.ProviderError('Test stops at normal tool selection.')
    monkeypatch.setattr(agent_model,'complete',complete)
    before=s.api.get('/api/jobs').json()
    response=s.api.post('/api/agent-v2/plans',json={'text':'Read specific.txt' if route.get('document_names') else 'Read the current scope','dataset_id':d['id'],
        'planner_model_id':next(m['id'] for m in d['models'] if 'chat' in m['capabilities'])})
    assert len(seen)==1
    assert s.api.get('/api/jobs').json()==before


def test_inconsistent_results_filter_is_reclassified_before_reading_wrong_data(system,monkeypatch):
    s=system;d=dataset(s);document(s,d,'file.txt');decisions=[]
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    def classify(messages):
        decisions.append(messages)
        return frame('results',answer_kind='filter',result_scope='latest_workflow') if len(decisions)==1 else frame()
    monkeypatch.setattr(agent_model,'classify',classify)
    outputs=iter([tool('list_documents'),{'text':'file.txt','calls':[]}])
    monkeypatch.setattr(agent_model,'complete',lambda *args,**kwargs:next(outputs))
    p=plan(s,d,text='List dataset documents')
    answer=events(reply(s,p))[-1]['message']
    assert len(decisions)==2 and decisions[1][-1]['content']=='List dataset documents'
    assert [o['tool'] for o in answer['tool_trace']]==['list_documents']
    assert len(answer['request_route']['attempts'])==2


def test_chat_cannot_finish_without_metadata_reads_or_with_incomplete_pages(system,monkeypatch):
    s=system;d=dataset(s)
    for i in range(21):document(s,d,f'{i}.txt')
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph');monkeypatch.setattr(agent_model,'classify',lambda messages:frame())
    outputs=iter([{'text':'Invented file','calls':[]},tool('list_documents'),{'text':'Only 20 files','calls':[]},
        tool('list_documents',offset=20),{'text':'All 21 files were inspected.','calls':[]}])
    monkeypatch.setattr(agent_model,'complete',lambda *args,**kwargs:next(outputs))
    p=plan(s,d,text='List all documents')
    assert p['explanation']=='All 21 files were inspected.'
    answer=events(reply(s,p))[-1]['message']
    assert [o['arguments'].get('offset',0) for o in answer['tool_trace']]==[0,20]


def test_application_help_uses_documentation_without_a_dataset(system,monkeypatch):
    s=system;d=dataset(s);monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:frame('application',answer_kind='other'))
    outputs=iter([tool('get_application_info',topic='overview'),{'text':'Aegis organizes datasets, documents and extraction results.','calls':[]}])
    monkeypatch.setattr(agent_model,'complete',lambda *args,**kwargs:next(outputs))
    p=plan(s,d,text='What can you do?',dataset_id='')
    answer=events(reply(s,p))[-1]['message']
    assert answer['tool_trace'][0]['tool']=='get_application_info'
    assert answer['tool_trace'][0]['result']['user_guide']['review']
    assert not s.api.get('/api/jobs').json()


def test_combined_metadata_and_saved_values_enable_only_declared_content_tools(system,monkeypatch):
    s=system;d=dataset(s);doc=document(s,d,'one.txt')
    extraction=routing.create('extraction',s.owner,'Saved',{'document_ids':[doc.id],
        'result':{'full_name':'Alice'},'review_status':'unreviewed'},parent=d['id'])
    routing.create('extraction',s.owner,'Other',{'document_ids':[doc.id],'result':{'full_name':'Other'}},parent=d['id'])
    assert tools_for(s,d).find_extractions(name='saved')['total']==1
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:frame(supplementary_sources=['results']))
    named_lookup=tool('find_extractions');named_lookup['calls'][0]['arguments']={'name':'Saved'}
    outputs=iter([tool('get_dataset_status'),{'text':'The name is unavailable from status.','calls':[]},named_lookup,
        tool('read_extraction_results',extraction_id=extraction.id,fields=['full_name']),
        {'text':'One file. Saved full_name: Alice (unreviewed).','calls':[]}])
    def complete(messages,contracts,**kwargs):
        names={c['function']['name'] for c in contracts}
        if not any(m.get('tool_name')=='read_extraction_results' for m in messages):
            assert {'find_extractions','read_extraction_results'}<=names
        else:assert not names  # Final composition retains data, without schemas.
        assert not {'search_documents','prepare_workflow','prepare_recovery'}&names
        return next(outputs)
    monkeypatch.setattr(agent_model,'complete',complete)
    p=plan(s,d,text='How many files and what full_name was extracted?')
    answer=events(reply(s,p))[-1]['message']
    assert [o['tool'] for o in answer['tool_trace']]==['get_dataset_status','find_extractions','read_extraction_results']
    assert answer['review_actions'][0]['extraction_id']==extraction.id
    assert answer['citations'][0]['kind']=='extraction'
    assert not s.api.get('/api/jobs').json()


def test_status_read_does_not_offer_duplicate_reads_or_unneeded_result_tools(system,monkeypatch):
    s=system;d=dataset(s);document(s,d,'one.txt');seen=[]
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:frame(answer_kind='count'))
    def complete(messages,contracts,**kwargs):
        names={c['function']['name'] for c in contracts};seen.append(names)
        assert not {'find_extractions','read_extraction_results','search_documents'}&names
        if len(seen)==1:return tool('get_dataset_status')
        assert 'get_dataset_status' not in names
        status=json.loads(next(m['content'] for m in messages if m.get('tool_name')=='get_dataset_status'))
        return {'text':f"{status['document_count']} file, {status['active_job_count']} active jobs.",'calls':[]}
    monkeypatch.setattr(agent_model,'complete',complete)
    p=plan(s,d,text='How many files are indexed and is any job running?')
    answer=events(reply(s,p))[-1]['message']
    assert answer['text']=='1 file, 0 active jobs.' and len(answer['tool_trace'])==1
    seen.clear()
    def next_complete(messages,contracts,**kwargs):
        # Current-turn tool observations follow this single current request.
        users=[m['content'] for m in messages if m['role']=='user']
        assert users==['Which models are mapped?']
        seen.append(messages)
        if len(seen)==1:return tool('get_model_configuration')
        return {'text':'The mapped model names are available.','calls':[]}
    monkeypatch.setattr(agent_model,'complete',next_complete)
    follow=plan(s,d,text='Which models are mapped?',conversation_id=p['conversation_id'])
    message=events(reply(s,follow))[-1]['message']
    assert [o['tool'] for o in message['tool_trace']]==['get_model_configuration']


def test_required_tool_preflight_reserves_actual_selection_budget(system,monkeypatch):
    from ags_app import ollama_provider
    from ags_app.agent_tools import definitions
    seen=[]
    def request(path,payload,timeout):
        seen.append(payload)
        return {'done':True,'done_reason':'stop','message':{'content':json.dumps({
            'answer':'','tool_calls':[{'name':'list_documents','arguments':{}}]})}}
    monkeypatch.setattr(ollama_provider,'request',request)
    cfg=core.settings()|{'model':'qwen3:4b','context_limit':8192,'max_output_tokens':1024}
    contracts=[c for c in definitions() if c['function']['name']=='list_documents']
    with core.execution_context({'settings':cfg}):
        result=agent_model.schema_decision([{'role':'system','content':'x'*13800}],contracts,cfg,required_tool=True)
        assert core.settings()['max_output_tokens']==1024
    assert result['calls'][0]['name']=='list_documents'
    assert seen[0]['options']['num_predict']==256 and seen[0]['options']['num_ctx']==8192


def test_combined_answer_reads_all_saved_profile_pages(system,monkeypatch):
    s=system;d=dataset(s);doc=document(s,d,'one.txt')
    extraction=routing.create('extraction',s.owner,'Merged',{'document_ids':[doc.id],
        'result':{'records':[{'fields':{'full_name':f'Person {i}'},'source_filename':'one.txt'} for i in range(5)]}},parent=d['id'])
    monkeypatch.setenv('AEGIS_AGENT_ENGINE','langgraph')
    monkeypatch.setattr(agent_model,'classify',lambda messages:frame(supplementary_sources=['results']))
    outputs=iter([tool('get_dataset_status'),tool('find_extractions'),
        tool('read_extraction_results',extraction_id=extraction.id,fields=['full_name']),
        {'text':'Only the first two names were read.','calls':[]},
        tool('read_extraction_results',extraction_id=extraction.id,fields=['full_name'],offset=2),
        tool('read_extraction_results',extraction_id=extraction.id,fields=['full_name'],offset=4),
        {'text':'All five saved names were read.','calls':[]}])
    monkeypatch.setattr(agent_model,'complete',lambda *args,**kwargs:next(outputs))
    p=plan(s,d,text='How many documents and all saved names?')
    answer=events(reply(s,p))[-1]['message']
    assert 'All five' in answer['text']
    assert [o['arguments'].get('offset',0) for o in answer['tool_trace'] if o['tool']=='read_extraction_results']==[0,2,4]
