"""Opt-in Gemini comparison using the frozen local Select AI questions.

Default: validate references without any service calls. --prepare exports Oracle's
actual showprompt messages and verifies both fixtures without model inference.
--run additionally requires a private key and recently verified Free-tier receipt.
The original offline services, Select AI profile and Aegis Agent are not changed.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
from pathlib import Path
import subprocess
import time

import benchmark_local_select_ai as baseline

ROOT = baseline.ROOT
PRIVATE_ROOT = ROOT / 'ags_runtime' / 'select-ai-local'
CONFIG = PRIVATE_ROOT / 'gemini-private.json'
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
MODEL = 'gemini-2.5-flash'
INSTRUCTION = 'Return only the final Oracle SQL query in a JSON object with one key sql. No explanation or reasoning. /no_think'
SQL_SCHEMA = {'type': 'object', 'properties': {'sql': {'type': 'string'}},
              'required': ['sql'], 'additionalProperties': False}


def fingerprint():
    return hashlib.sha256(json.dumps(baseline.CASES, sort_keys=True).encode()).hexdigest()


def free_configuration(path=CONFIG, now=None):
    """Fail closed; an API key alone does not establish a project's billing tier.

    The receipt must be completed only after checking that SAME key's project in
    Google AI Studio. This local check does not query Google's billing control plane.
    """
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        required = {'api_key', 'project_id', 'model', 'billing_tier',
                    'billing_verified_at_utc', 'billing_verification_source'}
        if set(value) != required or value['model'] != MODEL or value['billing_tier'] != 'free':
            raise ValueError()
        if not all(isinstance(value[key], str) and value[key].strip() for key in required):
            raise ValueError()
        if not 20 <= len(value['api_key']) <= 200 or not 3 <= len(value['project_id']) <= 128:
            raise ValueError()
        verified = datetime.fromisoformat(value['billing_verified_at_utc'].replace('Z', '+00:00'))
        current = now or datetime.now(timezone.utc)
        if verified.tzinfo is None or not timedelta(0) <= current - verified <= timedelta(hours=24):
            raise ValueError()
        if value['billing_verification_source'] != 'Google AI Studio Projects: Free tier':
            raise ValueError()
        return value
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError('Gemini is blocked: provide a private key for a project verified as Free tier within 24 hours. No inference was requested.') from None


def payload(messages):
    if not isinstance(messages, list) or not messages or len(messages) > 20:
        raise ValueError('Unexpected Oracle showprompt messages.')
    if any(not isinstance(m, dict) or set(m) != {'role', 'content'}
           or m['role'] not in ('system', 'user', 'assistant') or not isinstance(m['content'], str)
           for m in messages):
        raise ValueError('Unexpected Oracle showprompt message shape.')
    return {'model': MODEL, 'messages': messages + [{'role': 'user', 'content': INSTRUCTION}],
            'temperature': 0, 'max_tokens': 768, 'reasoning_effort': 'none',
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': 'metadata_sql', 'strict': True, 'schema': SQL_SCHEMA}}}


def parse_answer(value):
    choices = value.get('choices') or []
    if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
        raise ValueError('Gemini returned an incomplete or refused response.')
    content = json.loads(choices[0]['message']['content'])
    if not isinstance(content, dict) or set(content) != {'sql'} or not isinstance(content['sql'], str):
        raise ValueError('Gemini did not return the requested SQL object.')
    return content['sql'], value.get('usage', {})


def validate_plan(report):
    if (report['question_fingerprint'] != fingerprint() or report['model'] != MODEL
            or report['endpoint'] != ENDPOINT or len(report['plan']) != len(baseline.CASES)):
        raise ValueError('Prepared questions or model changed; prepare a new directory.')
    for index, (planned, original) in enumerate(zip(report['plan'], baseline.CASES), 1):
        if (planned['id'] != f'Q{index:02}' or planned['category'] != original[0]
                or planned['question'] != original[1] or planned['gold_sql'] != original[2]
                or planned['request'] != payload(planned['request']['messages'][:-1])):
            raise ValueError('Prepared question or fixed Gemini request settings changed.')


def output_directory(path=None):
    output = Path(path).resolve() if path else PRIVATE_ROOT / ('gemini-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
    if not output.is_relative_to(PRIVATE_ROOT) or output == PRIVATE_ROOT:
        raise ValueError('Use a separate ignored directory under ags_runtime/select-ai-local/.')
    output.mkdir(parents=True, exist_ok=True)
    return output


def write_report(output, report):
    done = report['cases']
    correct = sum(bool(c.get('correct_a') and c.get('correct_b')) for c in done)
    complete = report['status'] == 'complete' and len(done) == len(baseline.CASES)
    report['summary'] = {'planned': len(baseline.CASES), 'completed': len(done),
                         'correct_both': correct,
                         'accuracy_percent': round(100 * correct / len(done), 1) if done else None,
                         'complete_comparison': complete,
                         'difference_from_local_baseline_percentage_points':
                             round(100 * correct / len(done) - 67.5, 1) if complete else None,
                         'aegis_agent_improvement_measured': False}
    baseline.save(output / 'results.json', report)
    esc = lambda value: html.escape(str(value))
    score = f'{correct}/{len(done)} completed' if done else 'Not run'
    delta = report['summary']['difference_from_local_baseline_percentage_points']
    rows = []
    by_id = {c['id']: c for c in done}
    for planned in report['plan']:
        case = by_id.get(planned['id'], {})
        result = 'PASS BOTH' if case.get('correct_a') and case.get('correct_b') else 'FAILED' if case else 'PENDING'
        evidence = {k: case.get(k) for k in ['generated_sql', 'actual_a', 'actual_b', 'error', 'usage']}
        rows.append(f'<tr><td>{esc(planned["id"])}</td><td>{esc(planned["question"])}</td><td>{result}</td>'
                    f'<td><details><summary>Evidence</summary><pre>{esc(json.dumps(evidence, indent=2))}</pre></details></td></tr>')
    document = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aegis Gemini metadata benchmark</title><style>body{{font:15px/1.6 system-ui,sans-serif;max-width:1100px;margin:30px auto;padding:0 18px;color:#16304f;background:#f3f7fc}}section{{background:white;border:1px solid #cbd8eb;border-radius:12px;padding:20px;margin:18px 0}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{border:1px solid #cbd8eb;padding:10px;text-align:left;vertical-align:top}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;max-width:600px}}.scroll{{overflow:auto}}</style>
<h1>Gemini metadata benchmark</h1><p>Status: <b>{esc(report['status'])}</b>. Gemini: <b>{score}</b>. Local Qwen baseline: <b>27/40 (67.5%)</b>.</p>
<section><b>Improvement over Aegis Agent remains unmeasured.</b><p>Difference from local Qwen: {esc(str(delta)+' percentage points' if delta is not None else 'not measured; Gemini comparison is incomplete')}.</p>
<p>The same 40 questions and two synthetic fixtures are used. Oracle showprompt supplies the actual schema/question messages; the same JSON-only instruction, 768 output-token limit, SQL allow-list and read-only Oracle executor are used. Gemini uses the Google Developer API directly. Oracle's native showsql response processing and the authenticated application route are not exercised by this comparator. Latencies therefore do not represent comparable full application timings.</p>
<p>No changes to Aegis Agent, the offline model network, native Select AI profile or live data are made. A prepared plan makes zero external calls. A run requires a recently checked Free-tier project; the local receipt is not an independent billing API check. Quota/authentication failures stop the run without a paid fallback. Partial scores are not final accuracy results.</p></section>
<section><pre>{esc(json.dumps(report['summary'], indent=2))}</pre></section>
<div class="scroll"><table><thead><tr><th>ID</th><th>Question</th><th>Result</th><th>Evidence</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></html>'''
    (output / 'report.html').write_text(document, encoding='utf-8')


def prepare(output):
    baseline.prepare_environment(output)
    from ags_app import local_select_ai as lab
    baseline.network_proof()
    config = lab.configuration()
    audit = PRIVATE_ROOT / 'audit' / 'requests.jsonl'
    before = audit.stat().st_size
    fixtures = baseline.variants()
    plan = []
    for index, case in enumerate(baseline.CASES, 1):
        category, question, gold = case[:3]
        ids = case[3] if len(case) > 3 else [row[0] for row in baseline.DATASETS]
        item = {'id': f'Q{index:02}', 'category': category, 'question': question,
                'scope': ids, 'gold_sql': gold}
        for variant, rows in zip(('a', 'b'), fixtures):
            data = baseline.scoped(rows, ids)
            expected = baseline.reference(data, gold)
            with lab.connect(config) as connection:
                lab.verify_profile(connection)
                lab.stage(connection, data)
                actual = lab.execute(connection, lab.validate_sql(gold))['rows']
                assert baseline.result_match(actual, expected, category == 'ordering')[0], item['id']
            item['expected_' + variant] = expected
        with lab.connect(config) as connection:
            lab.verify_profile(connection)
            cursor = connection.cursor()
            cursor.execute("select DBMS_CLOUD_AI.GENERATE(prompt=>:prompt,profile_name=>:profile,action=>'showprompt') from dual",
                           prompt=question, profile=lab.PROFILE)
            messages = json.loads(lab.text_value(cursor.fetchone()[0]))
            item['request'] = payload(messages)
        plan.append(item)
    assert before == audit.stat().st_size, 'Preparation unexpectedly invoked the local model.'
    report = {'status': 'prepared_no_gemini_calls', 'created_at': datetime.now(timezone.utc).isoformat(),
              'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'question_fingerprint': fingerprint(), 'model': MODEL, 'endpoint': ENDPOINT,
              'reference_checks_passed': len(plan) * 2, 'local_model_audit_unchanged': True,
              'external_provider_calls': 0, 'agent_comparison_performed': False,
              'plan': plan, 'cases': []}
    write_report(output, report)
    return report


def run(output, report, credential):
    import httpx
    baseline.prepare_environment(output)
    from ags_app import local_select_ai as lab
    validate_plan(report)
    if report.get('project_id') not in (None, credential['project_id']):
        raise ValueError('A resumable benchmark must keep the same project.')
    report.update(project_id=credential['project_id'], status='running',
                  billing_tier='free', billing_verification_source=credential['billing_verification_source'],
                  billing_verified_at_utc=credential['billing_verified_at_utc'])
    config = lab.configuration()
    fixtures = baseline.variants()
    completed = {case['id'] for case in report['cases']}
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=90) as client:
        for planned in report['plan']:
            if planned['id'] in completed:
                continue
            # Recheck receipt expiry for every call. No automatic quota retries.
            current = free_configuration()
            if any(current[key] != credential[key] for key in ('api_key', 'project_id')):
                raise ValueError('Gemini credentials or project changed during the run.')
            start = time.monotonic()
            print('Requesting ' + planned['id'], flush=True)
            report['external_provider_calls'] += 1
            write_report(output, report)
            try:
                response = client.post(ENDPOINT, headers={'Authorization': 'Bearer ' + credential['api_key']}, json=planned['request'])
            except httpx.HTTPError:
                report['status'] = 'stopped_transport_error'
                write_report(output, report)
                return
            if response.status_code in (401, 402, 403, 429) or response.status_code >= 500:
                report['status'] = 'stopped_http_' + str(response.status_code)
                write_report(output, report)
                return
            item = {key: planned[key] for key in ('id', 'category', 'question')}
            item.update(correct_a=False, correct_b=False, http_status=response.status_code)
            try:
                if response.status_code != 200:
                    raise ValueError('Gemini request failed; no provider fallback was attempted.')
                sql, usage = parse_answer(response.json())
                item.update(generated_sql=sql, usage=usage)
                safe = lab.validate_sql(sql)
                for variant, rows in zip(('a', 'b'), fixtures):
                    with lab.connect(config) as connection:
                        lab.verify_profile(connection)
                        lab.stage(connection, baseline.scoped(rows, planned['scope']))
                        actual = lab.execute(connection, safe)['rows']
                    item['actual_' + variant] = actual
                    item['correct_' + variant] = baseline.result_match(actual, planned['expected_' + variant], planned['category'] == 'ordering')[0]
            except Exception as error:
                item['error'] = str(error) if isinstance(error, ValueError) else getattr(error, 'detail', type(error).__name__)
            item['seconds'] = round(time.monotonic() - start, 2)
            report['cases'].append(item)
            write_report(output, report)
            print(item['id'] + ': ' + ('PASS BOTH' if item['correct_a'] and item['correct_b'] else 'FAILED'), flush=True)
            if len(report['cases']) < len(baseline.CASES):
                time.sleep(max(0, 13 - (time.monotonic() - start)))
    report['status'] = 'complete'
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    write_report(output, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--prepare', action='store_true')
    actions.add_argument('--run', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not (args.prepare or args.run):
        for case in baseline.CASES:
            ids = case[3] if len(case) > 3 else [row[0] for row in baseline.DATASETS]
            for rows in baseline.variants():
                baseline.reference(baseline.scoped(rows, ids), case[2])
        print('80 reference answers validated. No Oracle or model calls made.')
        return
    # Refuse a cloud run before preparation/import if no verified Free-tier setup exists.
    credential = free_configuration() if args.run else None
    output = output_directory(args.output)
    report = json.loads((output / 'results.json').read_text()) if args.run and (output / 'results.json').exists() else prepare(output)
    if args.run:
        run(output, report, credential)
    print('REPORT: ' + str(output / 'report.html'), flush=True)


if __name__ == '__main__':
    main()
