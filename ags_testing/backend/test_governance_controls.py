"""Operational governance: approval, masking bypasses, holds, scans and deletion."""
import json
import time
import pytest
from sqlalchemy import select
from ags_app import core, main, relational, governance_controls as controls
from ags_app import governance_audit as audit, governance_quality as quality, governance_automation as automation
from ags_app import governance_retention as retention, governance_oci
from test_dataset_models import system, dataset, upload, template
from test_metadata_relationships import run_record
from test_governance import admin


def administrators(s):
    admin(s)
    with s.session.begin() as db:
        db.add(core.User(id='approver', username='Second administrator', password_hash='synthetic', role='administrator'))


def propose(s, d, **values):
    return s.api.post('/api/governance/datasets/' + d['id'] + '/controls/proposals', json={
        'expected_version': 0, 'reason': 'Synthetic operational policy', 'controls': values})


def approve(s, d, **values):
    result = propose(s, d, **values)
    assert result.status_code == 200, result.text
    pending = result.json()['pending']
    s.owner = 'approver'
    decision = s.api.post('/api/governance/datasets/' + d['id'] + '/controls/decision', json={
        'proposal_id': pending['id'], 'approve': True, 'reason': 'Independently reviewed'})
    assert decision.status_code == 200, decision.text
    s.owner = 'alice'
    return decision.json()


def reader(s, d):
    with s.session.begin() as db:
        db.add(core.User(id='reader', username='Masked reader', password_hash='synthetic'))
        db.add(relational.UserDataset(user_id='reader', dataset_id=d['id'], enabled=True))
    s.owner = 'reader'


def test_two_administrator_approval_conflicts_and_rejection(system):
    s=system; administrators(s); d=dataset(s, mapped=False)
    p=propose(s,d,masking_enabled=True).json()
    path='/api/governance/datasets/'+d['id']+'/controls/decision'
    assert controls.active(d['id'])['controls']['masking_enabled'] is False
    body={'proposal_id':p['pending']['id'],'approve':True,'reason':'Review'}
    assert s.api.post(path,json=body).status_code==403
    assert propose(s,d).status_code==409
    s.owner='approver'
    result=s.api.post(path,json=body)
    assert result.status_code==200 and result.json()['active']['version']==1
    assert s.api.post(path,json=body).status_code==409
    assert propose(s,d).status_code==409
    assert s.api.post('/api/governance/datasets/'+d['id']+'/controls/proposals',json={
        'expected_version':1,'reason':'Disable','controls':{}}).status_code==200
    pending=controls.detail(s.owner,d['id'])['pending']
    assert s.api.post(path,json={'proposal_id':pending['id'],'approve':False,'reason':'Withdrawn'}).status_code==200
    assert controls.active(d['id'])['controls']['masking_enabled']


@pytest.mark.parametrize('spec',[
    {'retention_action':'purge'}, {'purge_grace_days':0}, {'quality_interval_minutes':1},
    {'sensitive_fields':['../../secrets']}, {'rules':[{'field':'amount','check':'minimum'}]},
    {'rules':[{'field':'state','check':'allowed_values'}]}, {'unknown':'secret'},
])
def test_invalid_operational_policy_is_rejected(system,spec):
    s=system; administrators(s); d=dataset(s,mapped=False)
    assert propose(s,d,**spec).status_code==422


def test_masked_result_exports_and_raw_bypass_routes(system):
    s=system; administrators(s); d=dataset(s); doc=upload(s,d)['documents'][0]; p=template(s)
    record=run_record(s,d,[doc],p,result={'email':'secret.person@example.com','bank_account':'777777777777',
        'customer_secret':'Sensitive custom value','amount':42,'notes':'Call +91 9876543210'},
        schema={'type':'object'},evidence=[{'quote':'secret.person@example.com'}])
    approve(s,d,masking_enabled=True,sensitive_fields=['customer_secret'])
    reader(s,d)
    for path in ('/api/extractions/'+record.id, '/api/extractions/'+record.id+'/versions',
                 '/api/extractions/'+record.id+'/export?format=json', '/api/extractions/'+record.id+'/export?format=csv'):
        response=s.api.get(path)
        assert response.status_code==200, response.text
        assert b'secret.person@example.com' not in response.content and b'777777777777' not in response.content
        assert b'Sensitive custom value' not in response.content and b'9876543210' not in response.content
        assert b'REDACTED' in response.content
    assert s.api.get('/api/extractions/'+record.id+'/export?format=parquet').status_code==403
    for suffix in ('', '/download', '/preview', '/source', '/page-image'):
        response=s.api.get('/api/documents/'+doc['id']+suffix)
        assert response.status_code in (403,404), response.text
    assert s.api.patch('/api/extractions/'+record.id,json={'version':1,'result':{'amount':99}}).status_code in (403,404)
    assert s.api.post('/api/knowledge/search',json={'text':'secrets','dataset_id':d['id']}).status_code in (403,404)
    assert s.api.get('/api/governance/datasets/'+d['id']+'/controls').status_code==200
    s.owner='alice'
    assert 'secret.person@example.com' in s.api.get('/api/extractions/'+record.id).text
    assert core.store.json(record.ref)['result']['amount']==42


def test_hold_blocks_document_dataset_and_workspace_deletion(system):
    s=system; administrators(s); d=dataset(s); doc=upload(s,d)['documents'][0]
    path='/api/governance/datasets/'+d['id']+'/hold'
    assert s.api.put(path,json={'active':True,'expected_version':0,'reason':'Preserve evidence'}).status_code==200
    assert s.api.delete('/api/documents/'+doc['id']).status_code==409
    assert s.api.request('DELETE','/api/datasets/'+d['id'],json={'confirmation':d['name'],'expected_version':d['version']}).status_code==409
    from ags_app import workspace_reset
    with pytest.raises(Exception,match='legal hold'): workspace_reset.reset(s.owner)
    assert s.api.put(path,json={'active':False,'expected_version':1,'reason':'Released'}).status_code==403
    s.owner='approver'
    assert s.api.put(path,json={'active':False,'expected_version':1,'reason':'Case closed'}).status_code==200
    assert s.api.delete('/api/documents/'+doc['id']).status_code==200


def test_quality_checks_discovery_alerts_and_staleness(system):
    s=system; administrators(s); d=dataset(s); a=upload(s,d)['documents'][0]; b=upload(s,d)['documents'][0]
    p=template(s)
    r=run_record(s,d,[a],p,result={'records':[{'fields':{'email':'private@example.com','amount':-1}}, {'fields':{'email':'private@example.com'}}]},schema={'type':'object'})
    approve(s,d,rules=[{'field':'amount','check':'required'}, {'field':'amount','check':'minimum','threshold':0}, {'field':'email','check':'unique'}])
    response=s.api.post('/api/governance/datasets/'+d['id']+'/quality/scan')
    assert response.status_code==200,response.text
    result=response.json()
    assert result['status']=='completed' and result['records_checked']==3 and result['result_rows_checked']==2
    assert {'duplicate_document','review_required','rule_required','rule_minimum','rule_unique'} <= {c['code'] for c in result['findings']}
    assert result['alerts']['errors'] and result['sensitivity']
    assert 'private@example.com' not in response.text and 'DO_NOT_RETURN' not in response.text
    assert not quality.latest(s.owner,d['id'])['report']['stale']
    with s.session.begin() as db: db.get(core.Record,r.id).version+=1
    assert quality.latest(s.owner,d['id'])['report']['stale']


def test_audit_includes_reads_exports_denials_and_detects_tampering(system):
    s=system; administrators(s); d=dataset(s)
    s.api.get('/api/governance/datasets/'+d['id'])
    s.api.get('/api/governance/export',params={'dataset_id':d['id']})
    reader(s,d)
    assert s.api.post('/api/governance/datasets/'+d['id']+'/quality/scan').status_code==403
    s.owner='alice'
    response=s.api.get('/api/governance/audit',params={'dataset_id':d['id']})
    assert response.status_code==200,response.text
    items=response.json()['items']
    assert any('export' in e['action'] for e in items)
    assert any(e['status']=='denied_or_failed' for e in audit._events())
    path=core.local_store.path(audit.JOURNAL)
    data=path.read_bytes().replace(b'GET',b'PUT',1);path.write_bytes(data)
    assert s.api.get('/api/governance/audit').status_code==503


def test_scheduler_obeys_interval_and_signatory_revocation(system,monkeypatch):
    s=system; administrators(s); d=dataset(s,mapped=False)
    approve(s,d,auto_quality=True,auto_sync=True)
    calls=[]
    monkeypatch.setattr(quality,'run',lambda *args:calls.append('quality') or {'status':'completed'})
    monkeypatch.setattr(governance_oci,'publish_selected',lambda *args:calls.append('sync') or {'status':'metadata_published'})
    automation.tick(); automation.tick()
    assert calls==['quality','sync']
    with s.session.begin() as db:db.get(core.User,'approver').role='user'
    automation.tick()
    assert calls==['quality','sync'] and core.store.json(automation.state_ref(d['id']))['status']=='suspended'


def age(s,d,days=400):
    with s.session.begin() as db:
        for r in db.scalars(select(core.Record).where((core.Record.parent_id==d['id'])|(core.Record.id==d['id']))):
            r.created_at=time.time()-days*86400
    # Audit hooks update updated_at for changes. Use a raw SQL update to model
    # real historical timestamps without changing the production audit hooks.
    with core.current_engine().begin() as c:
        c.execute(core.Record.__table__.update().where((core.Record.parent_id==d['id'])|(core.Record.id==d['id'])).values(updated_at=time.time()-days*86400))


def test_retention_archives_then_purges_only_the_expired_dataset(system):
    s=system; administrators(s); d=dataset(s); keep=dataset(s,'Keep',mapped=False); doc=upload(s,d)['documents'][0]
    approve(s,d,retention_action='purge',retention_days=365,purge_grace_days=7)
    age(s,d)
    assert retention.apply(s.owner,d['id'])['status']=='retired'
    assert retention.apply(s.owner,d['id'])['status']=='retired_waiting'
    ref='knowledge_base/'+d['id']+'/trash.json';receipt=core.store.json(ref);receipt['deleted_at']=time.time()-8*86400;core.store.put_json(ref,receipt)
    result=retention.apply(s.owner,d['id'])
    assert result['status']=='active_storage_purged'
    with s.session() as db:
        assert db.get(core.Record,d['id']) is None and db.get(core.Record,keep['id']) is not None
    with pytest.raises(FileNotFoundError):core.store.get('documents/'+doc['id']+'/original')


def test_corrupt_controls_and_hold_fail_closed(system):
    s=system; administrators(s); d=dataset(s,mapped=False)
    core.store.put_json(controls.root(d['id'])+'/controls.json', {'version':1,'controls':{},'proposed_by':'same','approved_by':'same'})
    assert s.api.get('/api/governance/datasets/'+d['id']+'/controls').status_code==503
    core.store.put_json(controls.root(d['id'])+'/hold.json', {'active':'false','version':1})
    assert s.api.request('DELETE','/api/datasets/'+d['id'],json={'confirmation':d['name'],'expected_version':d['version']}).status_code==503


def test_missing_anchored_policy_never_disables_masking(system):
    s=system; administrators(s); d=dataset(s,mapped=False); approve(s,d,masking_enabled=True)
    current=controls.active(d['id'])
    core.store.delete(controls.root(d['id'])+'/controls-v1.json')
    assert s.api.get('/api/governance/datasets/'+d['id']+'/controls').status_code==503
    with pytest.raises(Exception,match='invalid'):controls.active(d['id'])


def test_retired_dataset_can_receive_a_hold_and_cannot_be_purged(system):
    s=system; administrators(s); d=dataset(s,mapped=False)
    approve(s,d,retention_action='purge',retention_days=1,purge_grace_days=7)
    age(s,d,30)
    assert retention.apply(s.owner,d['id'])['status']=='retired'
    path='/api/governance/datasets/'+d['id']+'/hold'
    response=s.api.put(path,json={'active':True,'expected_version':0,'reason':'Preserve retired evidence'})
    assert response.status_code==200,response.text
    with pytest.raises(Exception,match='legal hold'):retention.apply(s.owner,d['id'])


def test_partial_quality_scan_is_not_reported_as_success(system,monkeypatch):
    s=system; administrators(s); d=dataset(s); doc=upload(s,d)['documents'][0]
    core.store.delete('documents/'+doc['id']+'/original')
    result=quality.run(s.owner,d['id'])
    assert result['status']=='failed_or_partial' and result['read_failures']


def test_retention_purge_can_finalize_after_catalog_commit_and_receipt_failure(system,monkeypatch):
    s=system; administrators(s); d=dataset(s,mapped=False)
    approve(s,d,retention_action='purge',retention_days=1,purge_grace_days=7); age(s,d,30)
    retention.apply(s.owner,d['id'])
    ref='knowledge_base/'+d['id']+'/trash.json';value=core.store.json(ref);value['deleted_at']=time.time()-8*86400;core.store.put_json(ref,value)
    original=core.store.put_json
    def fail(ref,data):
        if ref.endswith('/purge-receipt.json') and data.get('status')=='active_storage_purged': raise OSError('Synthetic receipt write failure')
        return original(ref,data)
    monkeypatch.setattr(core.store,'put_json',fail)
    with pytest.raises(OSError):retention.apply(s.owner,d['id'])
    with s.session() as db:assert db.get(core.Record,d['id']) is None
    monkeypatch.setattr(core.store,'put_json',original)
    assert retention.apply(s.owner,d['id'])['status']=='active_storage_purged'
    assert retention.apply(s.owner,d['id'])['status']=='active_storage_purged'


def test_native_lineage_submission_is_distinct_from_graph_visibility(system,monkeypatch):
    from types import SimpleNamespace as NS
    from ags_app import governance
    s=system; administrators(s); d=dataset(s); doc=upload(s,d,run=False)['documents'][0]
    run_record(s,d,[doc],template(s))
    monkeypatch.setattr(governance_oci,'upsert_glossary',lambda *args:'synthetic-key')
    submitted=[]
    client=NS(get_data_asset=lambda *args:NS(data=NS(type_key='custom',lifecycle_state='ACTIVE')),
              get_type=lambda *args:NS(data=NS(name='Custom Lineage Provider')),
              import_lineage=lambda *args,**kwargs:submitted.append((args,kwargs)))
    snapshot=governance.inventory(s.owner,[d['id']])
    result=governance_oci.publish(snapshot,client,'synthetic-catalog','synthetic-provider')
    assert result['lineage_submitted']==1 and result['lineage_status']=='accepted_not_visibility_verified'
    later=dict(snapshot,generated_at=snapshot['generated_at']+3600)
    assert list(governance_oci.lineage_events(snapshot))==list(governance_oci.lineage_events(later))
    assert 'DO_NOT_RETURN' not in submitted[0][0][2].lineage_payload


def test_approval_audit_records_the_actual_reviewer(system):
    s=system; administrators(s); d=dataset(s,mapped=False)
    approve(s,d,masking_enabled=True)
    event=next(item for item in reversed(audit._events()) if item['action'].endswith('/controls/decision'))
    assert event['actor_id']=='approver'


def test_rejected_proposal_can_be_cleared_after_proposer_demotion(system):
    s=system; administrators(s); d=dataset(s,mapped=False); p=propose(s,d).json()['pending']
    with s.session.begin() as db:db.get(core.User,'alice').role='user'
    s.owner='approver'
    response=s.api.post('/api/governance/datasets/'+d['id']+'/controls/decision',json={
        'proposal_id':p['id'],'approve':False,'reason':'Proposer no longer administers this data'})
    assert response.status_code==200,response.text
    assert response.json()['pending']['status']=='rejected' and controls.active(d['id'])['version']==0


def test_approval_recovers_a_failed_pending_status_write(system,monkeypatch):
    s=system; administrators(s); d=dataset(s,mapped=False); p=propose(s,d,masking_enabled=True).json()['pending']
    original=core.store.put_json
    def fail(ref,data):
        if ref.endswith('/pending.json') and data.get('status')=='approved':raise OSError('Synthetic status failure')
        return original(ref,data)
    monkeypatch.setattr(core.store,'put_json',fail);s.owner='approver'
    path='/api/governance/datasets/'+d['id']+'/controls/decision'
    body={'proposal_id':p['id'],'approve':True,'reason':'Independently checked'}
    with pytest.raises(OSError):s.api.post(path,json=body)
    assert controls.active(d['id'])['version']==1
    monkeypatch.setattr(core.store,'put_json',original)
    assert s.api.post(path,json=body).status_code==200
    assert controls.detail(s.owner,d['id'])['pending']['status']=='approved'


def test_discovery_patterns_do_not_damage_uuid_references(system):
    from types import SimpleNamespace
    s=system; administrators(s); d=dataset(s,mapped=False); approve(s,d,masking_enabled=True)
    reader(s,d)
    value={'id':'11223344-5566-7788-9900-112233445566','result':{'phone':'+91 9876543210','note':'Call +91 9876543210'}}
    result=controls.masked(s.owner,SimpleNamespace(parent_id=d['id']),value)
    assert result['id']==value['id'] and '9876543210' not in json.dumps(result)


def test_dashboard_general_chat_exception_survives_masking_but_grounding_is_blocked(system,monkeypatch):
    from ags_app.ags_agent import dataset_chat, dataset_chat_general
    s=system; administrators(s); d=dataset(s); approve(s,d,masking_enabled=True); reader(s,d)
    called=[]
    monkeypatch.setattr(dataset_chat_general,'general_reply',lambda *args:called.append('model') or 'Hello from the selected chat model.')
    monkeypatch.setattr(dataset_chat,'WorkspaceKnowledge',lambda *args:pytest.fail('Protected dataset must never reach knowledge retrieval'))
    body={'text':'Hi','dataset_ids':[d['id']],'model_id':d['default_chat_model_id']}
    response=s.api.post('/api/dataset-chat/messages',json=body)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['message']['source_summary']['knowledge_used'] is False and result['message']['citations']==[]
    assert called==['model']
    assert s.api.get('/api/dataset-chat/conversations/'+result['conversation_id']).status_code==200
    mixed=s.api.post('/api/dataset-chat/messages',json=dict(body,text='Hi, what is the invoice amount in our dataset?'))
    assert mixed.status_code==403 and called==['model']


def test_masking_blocks_old_grounded_history_without_blocking_general_history(system):
    from ags_app import dataset_models as routing
    s=system; administrators(s); d=dataset(s); reader(s,d)
    record=routing.create('dataset_chat',s.owner,'Grounded history',{'dataset_ids':[d['id']],'document_ids':None,
        'messages':[{'role':'assistant','text':'Private saved source content','request_route':{'routing_mode':'dataset_knowledge_chat'}}]})
    s.owner='alice'; approve(s,d,masking_enabled=True); s.owner='reader'
    assert s.api.get('/api/dataset-chat/conversations/'+record.id).status_code==403
    assert not s.api.get('/api/dataset-chat/conversations').json()


def test_policy_activation_during_grounded_inference_blocks_result_and_history(system,monkeypatch):
    from ags_app.ags_agent import dataset_chat
    s=system; administrators(s); d=dataset(s); reader(s,d)
    def answer(*args,**kwargs):
        pending=controls.propose('alice',d['id'],controls.Proposal(expected_version=0,reason='Protect dataset now',controls=controls.Controls(masking_enabled=True)))['pending']
        controls.decide('approver',d['id'],controls.Decision(proposal_id=pending['id'],approve=True,reason='Reviewed privacy change'))
        return {'text':'DO_NOT_RELEASE_PRIVATE_FACT','request_route':{'routing_mode':'dataset_knowledge_chat'}}
    monkeypatch.setattr(dataset_chat,'answer',answer)
    result=s.api.post('/api/dataset-chat/messages',json={'text':'What is the invoice amount?','dataset_ids':[d['id']],'model_id':d['default_chat_model_id']})
    assert result.status_code==403 and 'DO_NOT_RELEASE' not in result.text
    with s.session() as db:assert not list(db.scalars(select(core.Record).where(core.Record.kind=='dataset_chat')))
