"""Governance persistence, authorization, precise counts and metadata-only OCI publication."""
import json
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from ags_app import core, main, relational, governance, governance_oci, user_features
from test_dataset_models import system, dataset, upload, template
from test_metadata_relationships import run_record


def admin(s):
    with s.session.begin() as db:
        db.add(core.User(id='alice', username='governance-admin', password_hash='unused-synthetic-hash', role='administrator'))
    user_features.save('alice', 'alice', {'data_governance': True}, 0)


def values(**extra):
    return {'expected_version': 0, 'owner_name': 'Finance owner', 'steward': 'Finance operations',
            'classification': 'confidential', 'purpose': 'Invoice reconciliation', 'retention_days': 365,
            'glossary': [{'name': 'Invoice', 'definition': 'A supplier request for payment.'}],
            'change_reason': 'Assign accountability for the invoice pilot', **extra}


def catalog(s, ids, **params):
    return s.api.get('/api/governance/catalog', params=[('dataset_id', id) for id in ids]+list(params.items()))


def test_versioned_policy_preserves_dataset_and_models(system):
    s=system;d=dataset(s);admin(s)
    before=core.store.json(main.get_record(d['id'],s.owner).ref)
    result=s.api.put('/api/governance/datasets/'+d['id'],json=values())
    assert result.status_code==200,result.text
    assert result.json()['policy']['version']==1
    assert result.json()['history'][0]['updated_by']=='governance-admin'
    assert core.store.json(main.get_record(d['id'],s.owner).ref)==before
    assert s.api.put('/api/governance/datasets/'+d['id'],json=values(steward='Other')).status_code==409
    second=s.api.put('/api/governance/datasets/'+d['id'],json=values(expected_version=1,steward='Accounts team')).json()
    assert second['policy']['version']==2 and second['history_total']==2
    assert second['history'][0]['changed_fields']==['steward']
    assert second['history'][1]['version']==1
    graph=s.api.get('/api/metadata-relationships',params={'dataset_id':d['id'],'level':'instances'}).json()
    assert next(node for node in graph['nodes'] if node['type']=='Dataset')['attributes']['Classification']=='confidential'


def test_real_role_required_and_revocation_applies_to_all_reads(system):
    s=system;d=dataset(s,mapped=False);admin(s)
    assert s.api.put('/api/governance/datasets/'+d['id'],json=values()).status_code==200
    with s.session.begin() as db:
        db.add(core.User(id='bob',username='reader',password_hash='unused-synthetic-hash'))
        db.add(relational.UserDataset(user_id='bob',dataset_id=d['id'],enabled=True))
    user_features.save('alice', 'bob', {'data_governance': True}, 0)
    s.owner='bob'
    assert catalog(s,[d['id']]).json()['items'][0]['policy']['classification']=='confidential'
    assert s.api.get('/api/governance/datasets/'+d['id']).status_code==200
    assert s.api.put('/api/governance/datasets/'+d['id'],json=values()).status_code==403
    for path in ('/api/governance/oci','/api/governance/export'):
        assert s.api.get(path).status_code==403
    assert s.api.post('/api/governance/oci/publish',json={'dataset_ids':[d['id']]}).status_code==403
    with s.session.begin() as db:db.get(relational.UserDataset,('bob',d['id'])).enabled=False
    assert catalog(s,[d['id']]).status_code==404
    assert s.api.get('/api/governance/datasets/'+d['id']).status_code==404
    assert catalog(s,[]).json()['items']==[]


def test_catalog_counts_and_export_cover_complete_scope_without_content(system):
    s=system;admin(s);a=dataset(s,'Finance');b=dataset(s,'Other',mapped=False)
    doc=upload(s,a,run=False)['documents'][0];p=template(s);run_record(s,a,[doc],p)
    assert s.api.put('/api/governance/datasets/'+a['id'],json=values()).status_code==200
    page=catalog(s,[a['id'],b['id']],limit=1).json()
    assert page['total_items']==2 and page['has_more']
    assert page['totals']['datasets']==2 and page['totals']['classified']==1
    assert catalog(s,[a['id'],b['id']],search='Invoice').json()['total_items']==1
    export=s.api.get('/api/governance/export',params={'dataset_id':a['id']})
    assert export.status_code==200 and 'DO_NOT_RETURN' not in export.text
    assert 'result_reference' not in export.text and 'credential' not in export.text
    assert export.json()['dataset_ids']==[a['id']]
    assert b['id'] not in export.text
    assert export.json()['relationships']
    lineage=s.api.get('/api/governance/lineage-export',params={'dataset_id':a['id']})
    assert lineage.status_code==200 and lineage.text.endswith('\n')
    assert len([json.loads(line) for line in lineage.text.splitlines()])==1
    assert 'DO_NOT_RETURN' not in lineage.text and b['id'] not in lineage.text


@pytest.mark.parametrize('change',[{'classification':'secret'},{'retention_days':0},{'retention_days':True},{'change_reason':''},{'glossary':[{'name':'Invoice','definition':'A'},{'name':'invoice','definition':'B'}]},{'extra_secret':'forbidden'}])
def test_invalid_policy_is_rejected(system,change):
    s=system;admin(s);d=dataset(s,mapped=False)
    assert s.api.put('/api/governance/datasets/'+d['id'],json=values(**change)).status_code==422
    assert s.api.get('/api/governance/datasets/'+d['id']).json()['policy']['version']==0


def test_missing_policy_snapshot_fails_closed(system):
    s=system;admin(s);d=dataset(s,mapped=False)
    s.api.put('/api/governance/datasets/'+d['id'],json=values())
    core.store.delete(f'governance/{governance.policy_id(d["id"])}/v1.json')
    assert catalog(s,[d['id']]).status_code==503
    assert s.api.get('/api/governance/datasets/'+d['id']).status_code==503


def test_oci_connection_verified_before_saved_and_failures_sanitized(system,monkeypatch):
    s=system;admin(s)
    monkeypatch.setattr(governance_oci,'client',lambda config:SimpleNamespace(get_catalog=lambda id:SimpleNamespace(data=SimpleNamespace(lifecycle_state='ACTIVE'))))
    body={'catalog_id':'ocid1.datacatalog.oc1.ap-mumbai-1.synthetic','region':'ap-mumbai-1'}
    assert s.api.put('/api/governance/oci',json=body).status_code==200
    assert s.api.get('/api/governance/oci').json()['configured']
    def broken(config):raise RuntimeError('DO_NOT_RETURN_PRIVATE_CREDENTIAL')
    monkeypatch.setattr(governance_oci,'client',broken)
    response=s.api.put('/api/governance/oci',json=body)
    assert response.status_code==502 and 'DO_NOT_RETURN' not in response.text


def test_local_only_mode_blocks_oci_before_any_client_is_created(system,monkeypatch):
    s=system;admin(s);monkeypatch.setenv('AEGIS_LOCAL_ONLY','true')
    result=s.api.put('/api/governance/oci',json={'catalog_id':'ocid1.datacatalog.oc1.ap-mumbai-1.synthetic','region':'ap-mumbai-1'})
    assert result.status_code==409 and 'Local-only' in result.text
    assert s.api.get('/api/governance/oci').json()['configured'] is False


def test_lineage_export_uses_saved_sources_and_versions_without_values(system):
    s=system;admin(s);d=dataset(s);a=upload(s,d,run=False)['documents'][0];b=upload(s,d,run=False)['documents'][0]
    run_record(s,d,[a,b],template(s),review_status='reviewed',reviewed_extraction_version=1)
    snapshot=governance.inventory(s.owner,[d['id']]);events=list(governance_oci.lineage_events(snapshot))
    extraction=next(event for event in events if event['job']['name'].startswith('extraction:'))
    assert {value['name'] for value in extraction['inputs']}=={'document:'+a['id'],'document:'+b['id']}
    assert any(event['job']['name'].startswith('review:') for event in events)
    assert 'DO_NOT_RETURN' not in json.dumps(events)
    assert [event['run']['runId'] for event in events]==[event['run']['runId'] for event in governance_oci.lineage_events(snapshot)]


def test_partial_oci_publication_is_not_success(system,monkeypatch):
    s=system;admin(s);d=dataset(s,mapped=False)
    core.store.put_json(governance_oci.CONFIG,{'catalog_id':'ocid1.datacatalog.oc1.ap-mumbai-1.synthetic','region':'ap-mumbai-1'})
    monkeypatch.setattr(governance_oci,'client',lambda config:None)
    def broken(*args):raise RuntimeError('DO_NOT_RETURN_SECRET')
    monkeypatch.setattr(governance_oci,'publish',broken)
    result=s.api.post('/api/governance/oci/publish',json={'dataset_ids':[d['id']]})
    assert result.status_code==502 and 'DO_NOT_RETURN' not in result.text
    assert s.api.get('/api/governance/oci').json()['last_publication']['status']=='failed_or_partial'


def test_governance_is_archived_and_restored_with_workspace(system):
    from ags_app import workspace_reset
    s=system;admin(s);d=dataset(s,mapped=False)
    assert s.api.put('/api/governance/datasets/'+d['id'],json=values()).status_code==200
    receipt=workspace_reset.reset(s.owner)
    with s.session() as db:assert db.get(core.Record,governance.policy_id(d['id'])) is None
    workspace_reset._restore(receipt['id'])
    restored=s.api.get('/api/governance/datasets/'+d['id'])
    assert restored.status_code==200 and restored.json()['policy']['classification']=='confidential'


def test_governance_survives_recoverable_dataset_delete(system):
    s=system;admin(s);d=dataset(s,mapped=False)
    assert s.api.put('/api/governance/datasets/'+d['id'],json=values()).status_code==200
    deleted=s.api.request('DELETE','/api/datasets/'+d['id'],json={'confirmation':d['name'],'expected_version':d['version']})
    assert deleted.status_code==200,deleted.text
    assert s.api.get('/api/governance/datasets/'+d['id']).status_code==404
    assert s.api.post('/api/dataset-trash/'+d['id']+'/restore').status_code==200
    assert s.api.get('/api/governance/datasets/'+d['id']).json()['policy']['version']==1


def test_oci_repeat_publication_uses_current_etags_and_retires_removed_terms():
    from unittest.mock import Mock
    sdk=pytest.importorskip('oci')
    c=Mock()
    category=SimpleNamespace(key='category',display_name='Aegis business terms',parent_term_key=None)
    term=SimpleNamespace(key='invoice',display_name='Invoice',parent_term_key='category',description='Old definition')
    c.list_glossaries.return_value=SimpleNamespace(data=[SimpleNamespace(key='glossary')],headers={})
    c.get_glossary.return_value=SimpleNamespace(data=SimpleNamespace(key='glossary'),headers={'etag':'glossary-current'})
    c.update_glossary.return_value=SimpleNamespace(data=SimpleNamespace(key='glossary'))
    c.list_terms.return_value=SimpleNamespace(data=[category,term],headers={})
    c.get_term.return_value=SimpleNamespace(data=term,headers={'etag':'term-current'})
    dataset={'id':'dataset','name':'Invoices','counts':{},'policy':values()}
    governance_oci.upsert_glossary(c,'catalog',dataset,sdk.data_catalog.models)
    assert c.update_glossary.call_args.kwargs['if_match']=='glossary-current'
    assert c.update_term.call_args.kwargs['if_match']=='term-current'
    assert c.update_term.call_args.args[3].parent_term_key=='category'
    assert c.update_term.call_args.args[3].description=='A supplier request for payment.'
    c.create_glossary.assert_not_called();c.create_term.assert_not_called()
    dataset['policy']['glossary']=[]
    governance_oci.upsert_glossary(c,'catalog',dataset,sdk.data_catalog.models)
    assert c.update_term.call_args.args[3].description.startswith('Retired from the current Aegis glossary.')
