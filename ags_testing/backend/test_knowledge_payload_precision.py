"""JSON transport precision must not invalidate intact published knowledge."""
import copy,json
import pytest
from ags_app import knowledge
from ags_app.chat_knowledge import assemble

def transport_number(value):
    # Equivalent to serde_json's non-float_roundtrip decimal parsing path:
    # integer significand is converted to f64 before decimal exponent scaling.
    if isinstance(value,float):
        text=repr(value)
        if 'e' not in text:
            whole,fraction=text.split('.')
            return float(int(whole+fraction))/(10**len(fraction))
        return value
    if isinstance(value,dict):return {k:transport_number(v) for k,v in value.items()}
    if isinstance(value,list):return [transport_number(v) for v in value]
    return value

@pytest.mark.parametrize('timestamp',[51.248178375505404,1791915031.2345679])
def test_metadata_transport_is_lossless_and_business_fields_stay_numeric(timestamp):
    value={'fields':{'rate':timestamp,'count':7}}
    point=next(knowledge.point('extraction','result:record:0','dataset','owner','Saved',
        knowledge.encoded(value),source_updated_at=timestamp,ocr={'seconds':timestamp,'verified':False}))
    received=transport_number(json.loads(json.dumps(point)))
    assert received['payload']==point['payload']
    assert received['payload']['source_updated_at']==repr(timestamp)
    digest=received['payload'].pop('content_digest')
    assert knowledge.digest(received['payload'])==digest
    received['payload']['content_digest']=digest
    assert assemble([received])[0]['value']==value
    assert isinstance(assemble([received])[0]['value']['fields']['rate'],float)
    altered=copy.deepcopy(received['payload']);altered['source_updated_at']='0'
    assert knowledge.digest({k:v for k,v in altered.items() if k!='content_digest'})!=digest

def test_transport_reproduction_changes_an_unprotected_float():
    timestamp=51.248178375505404
    assert transport_number(timestamp)!=timestamp
