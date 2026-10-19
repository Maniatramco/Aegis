"""No-network checks for the opt-in Gemini comparator and billing gates."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

QA = Path(__file__).resolve().parents[1] / 'qa'
sys.path.insert(0, str(QA))
SPEC = importlib.util.spec_from_file_location('gemini_select_ai_benchmark', QA / 'benchmark_gemini_select_ai.py')
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def credential(now):
    return {'api_key': 'synthetic-key-for-unit-tests-only', 'project_id': 'synthetic-project',
            'model': benchmark.MODEL, 'billing_tier': 'free',
            'billing_verified_at_utc': now.isoformat(),
            'billing_verification_source': 'Google AI Studio Projects: Free tier'}


def test_missing_key_or_paid_unverified_and_stale_receipts_block_before_calls(tmp_path):
    path = tmp_path / 'private.json'
    now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match='No inference was requested'):
        benchmark.free_configuration(path, now)
    for field, value in [('billing_tier', 'paid'), ('billing_tier', 'trial'),
                         ('billing_verification_source', 'assumed from API key'),
                         ('billing_verified_at_utc', (now - timedelta(hours=25)).isoformat()),
                         ('billing_verified_at_utc', (now + timedelta(minutes=1)).isoformat()),
                         ('model', 'a-paid-model'), ('api_key', '')]:
        data = credential(now)
        data[field] = value
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError, match='No inference was requested'):
            benchmark.free_configuration(path, now)
    path.write_text(json.dumps(credential(now)))
    assert benchmark.free_configuration(path, now)['billing_tier'] == 'free'


def test_unexpected_endpoint_or_credentials_are_not_accepted(tmp_path):
    now = datetime.now(timezone.utc)
    data = credential(now)
    data['endpoint'] = 'https://unapproved.invalid'
    path = tmp_path / 'private.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        benchmark.free_configuration(path, now)


def test_prompt_preserves_oracle_messages_and_uses_fixed_model_and_limits():
    messages = [{'role': 'system', 'content': 'Synthetic schema'}, {'role': 'user', 'content': 'Count documents'}]
    original = json.loads(json.dumps(messages))
    request = benchmark.payload(messages)
    assert messages == original
    assert request['messages'][:-1] == original
    assert request['messages'][-1]['content'] == benchmark.INSTRUCTION
    assert request['model'] == 'gemini-2.5-flash'
    assert request['temperature'] == 0 and request['max_tokens'] == 768
    assert request['reasoning_effort'] == 'none'
    assert 'tools' not in request and 'api_key' not in request
    for bad in [[], [{'role': 'tool', 'content': 'x'}], [{'role': 'user', 'content': ['image']}]]:
        with pytest.raises(ValueError):
            benchmark.payload(bad)


def test_incomplete_refused_and_invalid_model_answers_are_not_scored_as_sql():
    def response(finish, content):
        return {'choices': [{'finish_reason': finish, 'message': {'content': content}}], 'usage': {'total_tokens': 12}}
    for value in [response('length', '{"sql":"SELECT 1"}'), response('stop', '{}'),
                  response('stop', '{"sql":null}'), response('stop', '{"sql":"x","extra":true}')]:
        with pytest.raises(ValueError):
            benchmark.parse_answer(value)
    assert benchmark.parse_answer(response('stop', '{"sql":"SELECT COUNT(*) FROM LOCAL_DOCUMENTS"}')) == (
        'SELECT COUNT(*) FROM LOCAL_DOCUMENTS', {'total_tokens': 12})


def test_partial_runs_never_claim_full_comparison_or_aegis_agent_improvement(tmp_path):
    report = {'status': 'stopped_http_429', 'plan': [],
              'cases': [{'id': 'Q01', 'correct_a': True, 'correct_b': True}]}
    benchmark.write_report(tmp_path, report)
    assert report['summary']['accuracy_percent'] == 100
    assert not report['summary']['complete_comparison']
    assert report['summary']['difference_from_local_baseline_percentage_points'] is None
    assert not report['summary']['aegis_agent_improvement_measured']
    assert 'Partial scores are not final accuracy results' in (tmp_path / 'report.html').read_text()


def test_cached_plan_cannot_switch_questions_model_or_enable_tools():
    plan = []
    for index, case in enumerate(benchmark.baseline.CASES, 1):
        plan.append({'id': f'Q{index:02}', 'category': case[0], 'question': case[1], 'gold_sql': case[2],
                     'request': benchmark.payload([{'role': 'user', 'content': case[1]}])})
    report = {'model': benchmark.MODEL, 'endpoint': benchmark.ENDPOINT,
              'question_fingerprint': benchmark.fingerprint(), 'plan': plan}
    benchmark.validate_plan(report)
    for field, value in [('model', 'a-paid-model'), ('tools', [{'type': 'web_search'}])]:
        altered = json.loads(json.dumps(report))
        altered['plan'][0]['request'][field] = value
        with pytest.raises(ValueError):
            benchmark.validate_plan(altered)
    report['plan'][0]['question'] = 'A different easier question'
    with pytest.raises(ValueError):
        benchmark.validate_plan(report)


@pytest.mark.parametrize('status', [401, 402, 403, 429, 503])
def test_quota_auth_and_server_failures_stop_after_one_attempt_without_fallback(tmp_path, monkeypatch, status):
    import httpx
    called = []
    def transport(request):
        called.append(request)
        return httpx.Response(status, request=request)
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs))
    monkeypatch.setattr(benchmark.baseline, 'prepare_environment', lambda output: None)
    monkeypatch.setattr(benchmark, 'validate_plan', lambda report: None)
    monkeypatch.setattr(benchmark, 'free_configuration', lambda: credential(datetime.now(timezone.utc)))
    monkeypatch.setitem(sys.modules, 'ags_app', SimpleNamespace(local_select_ai=SimpleNamespace(configuration=lambda: {})))
    report = {'status': 'prepared_no_gemini_calls', 'external_provider_calls': 0,
              'plan': [{'id': 'Q01', 'question': 'Synthetic question', 'request': benchmark.payload([{'role': 'user', 'content': 'Synthetic question'}])},
                       {'id': 'Q02', 'question': 'Must not be sent'}], 'cases': []}
    benchmark.run(tmp_path, report, credential(datetime.now(timezone.utc)))
    assert len(called) == 1 and str(called[0].url) == benchmark.ENDPOINT
    assert report['status'] == 'stopped_http_' + str(status)
    assert not report['cases'] and report['external_provider_calls'] == 1
    assert not report['summary']['complete_comparison']
    assert report['summary']['difference_from_local_baseline_percentage_points'] is None
