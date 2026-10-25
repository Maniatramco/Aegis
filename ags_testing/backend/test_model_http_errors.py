import httpx
import pytest
from ags_app.ags_models.connection import http_failure

@pytest.mark.parametrize('code,notice', [
    ('credit_balance_exhausted','prepaid credits'),
    ('organization_spend_limit_exceeded','organization reached its spend limit'),
    ('project_spend_limit_exceeded','project reached its spend limit'),
    ('organization_usage_limit_exceeded','approved usage limit'),
    ('insufficient_quota','insufficient quota'),
])
def test_quota_errors_are_actionable_without_echoing_provider_message(code, notice):
    response=httpx.Response(429,json={'error':{'code':code,'type':'insufficient_quota','message':'SECRET API KEY AND PRIVATE PROMPT'}})
    result=http_failure(response)
    assert notice in result and 'SECRET' not in result and 'rate limited' not in result

@pytest.mark.parametrize('code,kind',[('rate_limit_exceeded','tokens'),('slow_down','rate_limit_error'),('', 'rate_limit_error')])
def test_temporary_rate_limit_respects_safe_retry_hint(code,kind):
    response=httpx.Response(429,headers={'retry-after':'45'},json={'error':{'code':code,'type':kind}})
    result=http_failure(response)
    assert 'rate limited' in result and 'at least 45 seconds' in result

@pytest.mark.parametrize('data',[{'error':{'code':['bad'],'type':{}}},{'error':'private error'},['not an object'],{}])
def test_unknown_429_preserves_uncertainty_and_never_echoes_data(data):
    assert 'did not identify a recognized cause' in http_failure(httpx.Response(429,json=data))

def test_invalid_json_and_non429_keep_safe_messages():
    assert 'HTTP 429' in http_failure(httpx.Response(429,content=b'not json private data'))
    assert http_failure(httpx.Response(401,json={'error':{'message':'SECRET'}}))=='Model request failed (HTTP 401). Check credentials, model access, quota, and protocol.'
