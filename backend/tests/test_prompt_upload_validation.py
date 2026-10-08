"""Prompt preview uses the same schema validation as saving, without writes."""
from app import core,main
from test_dataset_models import system,post
from test_temporary_chat import snapshot

SCHEMA={'type':'object','properties':{'total':{'type':'number'}},'required':['total'],'additionalProperties':False}

def test_validation_is_read_only_and_preserves_reviewed_schema(system):
    s=system;before=snapshot(s)
    result=s.api.post('/api/templates/validate',json={'name':'Invoice','schema':SCHEMA})
    assert result.status_code==200,result.text
    assert result.json()=={'valid':True,'name':'Invoice','schema':SCHEMA,'dataset_id':None}
    assert snapshot(s)==before
    assert s.api.get('/api/templates').json()==[]

def test_validation_rejects_invalid_schemas_and_checks_dataset_ownership(system):
    s=system;before=snapshot(s)
    for schema in [{'type':'object','properties':{'total':{'type':'number'}}}, {'type':'object','additionalProperties':False,'required':[],'properties':{'total':{'type':'made-up'}}},SCHEMA|{'$ref':'https://example.test/schema'}, {'type':'array'}]:
        assert s.api.post('/api/templates/validate',json={'name':'Invalid','schema':schema}).status_code==400
    assert snapshot(s)==before
    dataset=post(s,'/api/datasets',{'name':'Owned dataset'})
    s.owner='bob'
    assert s.api.post('/api/templates/validate',json={'name':'Invoice','schema':SCHEMA,'dataset_id':dataset['id']}).status_code==404
    main.app.dependency_overrides.clear()
    assert s.api.post('/api/templates/validate',json={'name':'Invoice','schema':SCHEMA}).status_code==401
