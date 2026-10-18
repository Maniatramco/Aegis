"""Deterministic saved-data checks and sensitivity discovery; never inference."""
import hashlib
import json
import time
from collections import Counter
from fastapi import Depends, HTTPException
from jsonschema import Draft202012Validator
from sqlalchemy import select
from . import core, governance, governance_controls as controls, governance_audit as audit


def sources(dataset_id):
    with core.Session() as session:
        return list(session.scalars(select(core.Record).where(core.Record.parent_id == dataset_id,
                    core.Record.kind.in_(['document', 'extraction', 'template'])).order_by(core.Record.id)))


def stamp(rows):
    return hashlib.sha256(json.dumps([(row.id, row.version, row.status, row.updated_at) for row in rows], default=str).encode()).hexdigest()


def rows_of(result):
    if isinstance(result, dict) and isinstance(result.get('records'), list):
        return [row.get('fields', row) if isinstance(row, dict) else row for row in result['records']]
    return [result]


def field_value(row, path):
    value = row
    for key in path.split('.'):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def run(actor, dataset_id):
    governance.require_manager(actor)
    governance.scope(actor, [dataset_id])
    with core.document_lock('workspace-reset'), core.document_lock('governance-scan-' + governance.policy_id(dataset_id)):
        policy = controls.active(dataset_id)
        spec = policy['controls']
        source_rows = sources(dataset_id)
        source_stamp = stamp(source_rows)
        checks, sensitive, failures, hashes, all_rows = [], [], [], {}, []
        now = time.time()
        def issue(code, record_id, severity='warning', count=1, field=None):
            checks.append({'code': code, 'record_id': record_id, 'severity': severity, 'count': count, 'field': field})
        for record in source_rows:
            if record.status in ('failed', 'deleting'):
                issue('processing_failed', record.id, 'error')
            if record.updated_at and now - float(record.updated_at) > spec['freshness_days'] * 86400:
                issue('stale_record', record.id)
            try:
                if record.kind == 'document':
                    raw = core.store.get(record.ref)
                    digest = hashlib.sha256(raw).hexdigest()
                    if digest in hashes:
                        issue('duplicate_document', record.id)
                    else:
                        hashes[digest] = record.id
                    try:
                        payload = core.store.json('documents/' + record.id + '/parsed.json')
                    except FileNotFoundError:
                        payload = raw.decode('utf-8', errors='ignore') if record.name.lower().endswith(('.txt', '.json')) else ''
                        if not payload:
                            issue('text_not_available_for_discovery', record.id)
                    counts = controls.sensitive_counts(payload, spec['sensitive_fields'])
                    if counts: sensitive.append({'record_id': record.id, 'record_type': record.kind, 'categories': counts})
                elif record.kind == 'extraction' and record.status == 'ready':
                    from .parquet_results import load
                    payload = load(core.store.json(record.ref))
                    result = payload.get('result')
                    if result is None:
                        issue('missing_result', record.id, 'error')
                    schema = payload.get('schema')
                    if schema:
                        Draft202012Validator.check_schema(schema)
                        errors = sum(1 for _ in Draft202012Validator(schema).iter_errors(result))
                        if errors: issue('schema_mismatch', record.id, 'error', errors)
                    else:
                        issue('missing_schema', record.id)
                    if spec['require_review'] and payload.get('review_status') != 'reviewed':
                        issue('review_required', record.id)
                    all_rows.extend((record.id, row) for row in rows_of(result))
                    counts = controls.sensitive_counts(result, spec['sensitive_fields'])
                    if counts: sensitive.append({'record_id': record.id, 'record_type': record.kind, 'categories': counts})
            except Exception:
                # Do not persist exception strings: schema/parser errors may contain values.
                failures.append({'record_id': record.id, 'code': 'saved_data_unreadable'})
                issue('saved_data_unreadable', record.id, 'error')
        for rule in spec['rules']:
            values = [(record_id, field_value(row, rule['field'])) for record_id, row in all_rows]
            unique = Counter(json.dumps(value, sort_keys=True, default=str) for _, value in values if value is not None)
            violations = Counter()
            for record_id, value in values:
                bad = False
                if rule['check'] == 'required': bad = value in (None, '', [], {})
                elif rule['check'] == 'unique': bad = value is not None and unique[json.dumps(value, sort_keys=True, default=str)] > 1
                elif rule['check'] in ('minimum', 'maximum'):
                    bad = type(value) not in (int, float) or (value < rule['threshold'] if rule['check'] == 'minimum' else value > rule['threshold'])
                elif rule['check'] == 'allowed_values': bad = str(value) not in rule['allowed_values']
                if bad: violations[record_id] += 1
            for record_id, count in violations.items():
                issue('rule_' + rule['check'], record_id, 'error', count, rule['field'])
        unchanged = source_stamp == stamp(sources(dataset_id)) and policy['version'] == controls.active(dataset_id)['version']
        result = {'id': core.uid(), 'dataset_id': dataset_id, 'at': now, 'actor_id': actor,
                  'status': 'completed' if unchanged and not failures else 'failed_or_partial',
                  'source_stamp': source_stamp, 'source_changed': not unchanged, 'controls_version': policy['version'],
                  'records_checked': len(source_rows), 'result_rows_checked': len(all_rows),
                  'findings': checks, 'sensitivity': sensitive, 'read_failures': failures,
                  'alerts': {'errors': sum(item['severity'] == 'error' for item in checks),
                             'warnings': sum(item['severity'] == 'warning' for item in checks),
                             'sensitive_records': len(sensitive)},
                  'discovery_note': 'Pattern and field-name detection can miss sensitive data and can produce false positives. No values are copied into this report.'}
        governance.require_manager(actor)
        governance.scope(actor, [dataset_id])
        audit.append(actor, 'governance.quality.scanned', dataset_ids=[dataset_id], status=result['status'])
        base = controls.root(dataset_id) + '/quality/'
        core.store.put_json(base + result['id'] + '.json', result)
        core.store.put_json(base + 'latest.json', result)
        return result


def latest(actor, dataset_id):
    governance.scope(actor, [dataset_id])
    result = controls._read(controls.root(dataset_id) + '/quality/latest.json', None)
    if result:
        result = dict(result, stale=(result['source_stamp'] != stamp(sources(dataset_id)) or
                                    result['controls_version'] != controls.active(dataset_id)['version']))
    governance.scope(actor, [dataset_id])
    return {'dataset_id': dataset_id, 'report': result}


def install(app, auth):
    @app.get('/api/governance/datasets/{id}/quality')
    def get_quality(id: str, actor=Depends(auth)):
        return latest(actor, id)

    @app.post('/api/governance/datasets/{id}/quality/scan')
    def scan(id: str, actor=Depends(auth)):
        return run(actor, id)
