"""Read-only lineage, complete counts, saved versions and grant enforcement."""
from sqlalchemy import select
from ags_app import core, main, relational, providers, dataset_models as routing
from test_dataset_models import system, dataset, upload, template, post


def request(s, ids, **params):
    return s.api.get('/api/metadata-relationships', params=[('dataset_id', id) for id in ids]+list(params.items()))


def run_record(s, d, docs, prompt, **extra):
    model = next(m for m in d['models'] if m['id'] == d['default_extraction_model_id'])
    return main.new_record('extraction', s.owner, 'Combined saved run', parent=d['id'], status='ready', data={
        'dataset_id':d['id'], 'document_ids':[doc['id'] for doc in docs], 'template_id':prompt['id'],
        'template_version':prompt['version'], 'review_status':'unreviewed',
        'model_selection':{'model_id':model['id'],'model_version':model['version'],'model_name':model['name'],'provider_model':model['provider_model']},
        'result':{'private_value':'DO_NOT_RETURN_RESULTS'},'credential':'DO_NOT_RETURN_SECRET',**extra})


def test_graph_reads_combined_lineage_without_inference_or_results(system, monkeypatch):
    s=system;d=dataset(s);a=upload(s,d,run=False)['documents'][0];b=upload(s,d,run=False)['documents'][0];p=template(s)
    run_record(s,d,[a,b],p,review_status='reviewed',reviewed_extraction_version=1)
    def forbidden(*args,**kwargs):raise AssertionError('Metadata inspection must not call a provider')
    monkeypatch.setattr(providers,'extract',forbidden)
    overview=request(s,[d['id']]);assert overview.status_code==200,overview.text
    graph=overview.json();assert graph['totals']['categories']['Document']==2
    assert graph['totals']['categories']['Review']==1
    full=request(s,[d['id']],level='instances',limit=100).json()
    assert len([e for e in full['edges'] if e['label']=='source of'])==2
    assert len([e for e in full['edges'] if e['label']=='used by (pinned)'])==1
    assert 'DO_NOT_RETURN' not in overview.text+str(full)
    assert 'connection_profile_id' not in str(full) and 'result_reference' not in str(full)
    with s.session() as db:assert all(j.status=='queued' for j in db.scalars(select(core.Job)))


def test_scope_never_defaults_to_all_and_rejects_foreign_datasets(system):
    s=system;d=dataset(s,'Visible',mapped=False)
    assert request(s,[]).json()['totals']['nodes']==0
    assert request(s,[d['id']]).json()['totals']['nodes']==1
    s.owner='bob'
    assert request(s,[d['id']]).status_code==404
    assert request(s,[]).json()['nodes']==[]


def test_shared_access_and_revocation_apply_to_nodes_edges_and_counts(system):
    s=system;d=dataset(s);doc=upload(s,d,run=False)['documents'][0]
    with s.session.begin() as db:
        db.add(core.User(id='bob',username='metadata-reader',password_hash=core.password_hash('Synthetic-only-123')))
        db.add(relational.UserDataset(user_id='bob',dataset_id=d['id'],enabled=True))
    s.owner='bob';result=request(s,[d['id']]);assert result.status_code==200,result.text
    assert result.json()['totals']['categories']['Document']==1
    with s.session.begin() as db:db.get(relational.UserDataset,('bob',d['id'])).enabled=False
    assert request(s,[d['id']]).status_code==404


def test_prompt_revisions_remain_distinct_and_counts_are_not_page_counts(system):
    s=system;d=dataset(s);doc=upload(s,d,run=False)['documents'][0]
    p=post(s,'/api/templates',{'name':'Saved schema','dataset_id':d['id'],'schema':{'type':'object','properties':{},'required':[],'additionalProperties':False}})
    run_record(s,d,[doc],p)
    current=main.get_record(p['id'],s.owner,'template');routing.write_version(current,core.store.json(current.ref))
    response=request(s,[d['id']],level='instances',category='Prompt',limit=1).json()
    assert response['total_items']==2 and response['has_more']
    assert response['totals']['categories']['Prompt']==2
    next_page=request(s,[d['id']],level='instances',category='Prompt',limit=1,offset=1).json()
    assert response['items'][0]['id']!=next_page['items'][0]['id']
    assert next_page['items'][0]['version']!=response['items'][0]['version']


def test_search_pagination_and_unknown_focus_do_not_invent_records(system):
    s=system;d=dataset(s,mapped=False)
    for index in range(25):main.new_record('document',s.owner,f'Evidence {index:02}.txt',parent=d['id'],status='queued')
    page=request(s,[d['id']],level='instances',category='Document',limit=12).json()
    assert page['total_items']==25 and len(page['items'])==12 and page['has_more']
    assert page['totals']['nodes']==26
    found=request(s,[d['id']],level='instances',search='Evidence 24').json()
    assert found['total_items']==1 and found['items'][0]['label']=='Evidence 24.txt'
    assert request(s,[d['id']],level='instances',focus='document:private').status_code==404
    assert request(s,[d['id']],level='instances',category='Private').status_code==422


def test_deleted_document_is_not_resurrected_from_saved_extraction_references(system):
    s=system;d=dataset(s);doc=upload(s,d,run=False)['documents'][0];p=template(s);run_record(s,d,[doc],p)
    with s.session.begin() as db:db.get(core.Record,doc['id']).status='deleted'
    graph=request(s,[d['id']],level='instances',limit=100).json()
    assert not any(n['id']=='document:'+doc['id'] for n in graph['nodes'])
    assert not any(e['label']=='source of' for e in graph['edges'])
