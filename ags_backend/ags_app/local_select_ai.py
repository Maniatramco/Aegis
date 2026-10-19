"""Opt-in local metadata SQL tool. Independent of the Unified Chat pipeline.

Oracle Select AI generates SQL using only the offline Qwen endpoint. Per-request
temporary tables contain complete authorized metadata, never source/result values.
"""
import json
import os
from pathlib import Path
import threading
import time

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import core, governance, governance_controls, runtime_config, user_features

SCHEMA = 'AEGIS_LOCAL_AI'
PROFILE = 'AEGIS_LOCAL_METADATA'
MODEL = 'qwen3:4b'
TABLES = {
    'LOCAL_DATASETS': ('DATASET_ID', 'DATASET_NAME', 'CLASSIFICATION', 'ACCOUNTABLE_OWNER', 'STEWARD', 'STATUS'),
    'LOCAL_DOCUMENTS': ('DOCUMENT_ID', 'DATASET_ID', 'DOCUMENT_NAME', 'STATUS', 'SIZE_BYTES'),
    'LOCAL_EXTRACTIONS': ('EXTRACTION_ID', 'DATASET_ID', 'EXTRACTION_NAME', 'STATUS', 'REVIEW_STATUS'),
}
ROW_LIMIT = 200
METADATA_LIMIT = 50000
REQUEST_SLOT = threading.BoundedSemaphore(1)


class QueryInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    dataset_ids: list[str] = Field(min_length=1, max_length=100)
    question: str = Field(min_length=3, max_length=1200)


def enabled():
    return runtime_config.get('AEGIS_LOCAL_SQL_ENABLED')


def configuration():
    if not enabled():
        raise HTTPException(404, 'Local Select AI is not enabled.')
    if os.getenv('AEGIS_LOCAL_ONLY') != 'true' or core.engine.url.get_backend_name() != 'sqlite':
        raise HTTPException(503, 'Local Select AI requires an isolated local-only SQLite workspace.')
    try:
        filename = Path(runtime_config.get('AEGIS_LOCAL_SQL_CONNECTION_FILE'))
        if not filename.is_absolute():
            raise ValueError()
        value = json.loads(filename.read_text(encoding='utf-8'))
        fixed = {'host': '127.0.0.1', 'port': 1523, 'service': 'FREEPDB1', 'user': SCHEMA, 'profile': PROFILE}
        if set(value) != set(fixed) | {'password'} or any(value.get(k) != v for k, v in fixed.items()):
            raise ValueError()
        if not isinstance(value['password'], str) or not 16 <= len(value['password']) <= 128:
            raise ValueError()
        return value
    except (OSError, ValueError, TypeError):
        raise HTTPException(503, 'The private local Select AI connection is unavailable.') from None


def model_health():
    try:
        with httpx.Client(trust_env=False, timeout=5, follow_redirects=False) as client:
            response = client.get('http://127.0.0.1:11439/health')
            response.raise_for_status()
            value = response.json()
        if (value.get('status') != 'ready' or value.get('model') != MODEL
                or value.get('model_location') != 'local' or value.get('cloud_enabled') is not False):
            raise ValueError()
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, 'The offline local model is unavailable. No cloud fallback is permitted.') from None


def connect(config):
    import oracledb  # Optional dependency; disabled installations do not need it.
    connection = oracledb.connect(user=SCHEMA, password=config['password'],
        host='127.0.0.1', port=1523, service_name='FREEPDB1', tcp_connect_timeout=5)
    connection.call_timeout = 180000
    return connection


def text_value(value):
    return value.read() if hasattr(value, 'read') else value


def verify_profile(connection):
    cursor = connection.cursor()
    cursor.execute('select attribute_name, attribute_value from user_cloud_ai_profile_attributes where profile_name=:profile', profile=PROFILE)
    attrs = {key.lower(): text_value(value) for key, value in cursor}
    expected = {'provider': 'openai', 'provider_endpoint': 'https://llm.aegis.local',
                'model': MODEL, 'credential_name': 'AEGIS_LOCAL_MODEL',
                'enforce_object_list': 'true', 'conversation': 'false'}
    try:
        objects = json.loads(attrs.get('object_list', 'null'))
        actual = {(item['owner'], item['name']) for item in objects}
        if (any(attrs.get(key) != value for key, value in expected.items())
                or actual != {(SCHEMA, name) for name in TABLES}
                or len(objects) != len(TABLES)):
            raise ValueError()
        if set(attrs) - set(expected) - {'object_list', 'comments', 'temperature', 'max_tokens'}:
            raise ValueError()
        cursor.execute("select count(*) from user_tables where table_name in ('LOCAL_DATASETS','LOCAL_DOCUMENTS','LOCAL_EXTRACTIONS') and temporary='Y' and duration='SYS$SESSION'")
        if cursor.fetchone()[0] != 3:
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503, 'The local Select AI profile or temporary-table safeguards changed. Re-run local setup.') from None


def authorize(actor, ids):
    selected = governance.scope(actor, ids)
    if governance_controls.restricted_datasets(actor, selected):
        raise HTTPException(403, 'Dataset privacy controls block this SQL tool for your account.')
    return selected


def snapshot(actor, ids):
    catalog = governance.inventory(actor, ids)
    if catalog['warnings']:
        raise HTTPException(503, 'Complete authorized metadata is unavailable. No partial counts were used.')
    rows = {name: [] for name in TABLES}
    for item in catalog['datasets']:
        policy = item['policy']
        rows['LOCAL_DATASETS'].append((item['id'], item['name'], policy['classification'],
            policy['owner_name'], policy['steward'], item['status']))
    for item in catalog['records']:
        if item['type'] not in ('Document', 'Extraction'):
            continue
        if len(item['dataset_ids']) != 1:
            raise HTTPException(503, 'Metadata scope is ambiguous.')
        dataset = item['dataset_ids'][0]
        attrs = item['attributes']
        if item['type'] == 'Document':
            rows['LOCAL_DOCUMENTS'].append((attrs['Document ID'], dataset, item['label'], item['status'], attrs['Size bytes']))
        else:
            rows['LOCAL_EXTRACTIONS'].append((attrs['Extraction ID'], dataset, item['label'], item['status'], attrs['Review status']))
    if sum(map(len, rows.values())) > METADATA_LIMIT:
        raise HTTPException(422, 'Choose fewer datasets. This local pilot supports up to 50,000 metadata rows without truncation.')
    return rows, catalog['generated_at']


def stage(connection, rows):
    cursor = connection.cursor()
    for name, columns in TABLES.items():
        # Fresh connection for each request: rows cannot survive into another user.
        if rows[name]:
            binds = ','.join(':' + str(i + 1) for i in range(len(columns)))
            cursor.executemany(f'INSERT INTO {name} ({",".join(columns)}) VALUES ({binds})', rows[name])
    connection.commit()


def validate_sql(value):
    from .local_select_ai_sql import validate_sql as check
    try:
        return check(value)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


def generate(connection, question):
    cursor = connection.cursor()
    cursor.execute("select DBMS_CLOUD_AI.GENERATE(prompt=>:prompt,profile_name=>:profile,action=>'showsql') from dual",
                   prompt=question, profile=PROFILE)
    return text_value(cursor.fetchone()[0])


def execute(connection, query):
    connection.rollback()
    connection.call_timeout = 15000
    cursor = connection.cursor()
    cursor.execute('SET TRANSACTION READ ONLY')
    cursor.execute(f'SELECT * FROM ({query}) WHERE ROWNUM <= :max_rows', max_rows=ROW_LIMIT + 1)
    columns = [item[0] for item in cursor.description]
    if len(columns) > 30:
        raise HTTPException(422, 'The query returned too many columns.')
    rows = cursor.fetchmany(ROW_LIMIT + 1)
    return {'columns': columns, 'rows': [list(row) for row in rows[:ROW_LIMIT]],
            'row_limit': ROW_LIMIT, 'has_more': len(rows) > ROW_LIMIT}


def query(actor, body):
    selected = authorize(actor, body.dataset_ids)
    config = configuration()
    if not REQUEST_SLOT.acquire(blocking=False):
        raise HTTPException(429, 'Another local SQL request is running. Try again when it finishes.')
    steps = []

    def timed(id, label, action):
        started = time.monotonic()
        value = action()
        steps.append({'id': id, 'label': label, 'status': 'completed',
                      'detail': f'{round((time.monotonic() - started) * 1000)} ms'})
        return value

    try:
        model_health()
        rows, as_of = timed('scope', 'Scope metadata', lambda: snapshot(actor, selected))
        with connect(config) as connection:
            verify_profile(connection)
            stage(connection, rows)
            authorize(actor, selected)
            sql = timed('generate', 'Oracle Select AI', lambda: generate(connection, body.question))
            safe = timed('validate', 'Validate SQL', lambda: validate_sql(sql))
            authorize(actor, selected)
            result = timed('execute', 'Read-only query', lambda: execute(connection, safe))
            timed('access', 'Recheck access', lambda: authorize(actor, selected))
        return result | {'sql': safe, 'dataset_ids': sorted(selected), 'metadata_as_of': as_of,
                         'metadata_rows': {name: len(value) for name, value in rows.items()},
                         'model': MODEL, 'engine': 'Oracle DBMS_CLOUD_AI.GENERATE / showsql',
                         'cloud_inference': False, 'external_provider_calls': 0, 'steps': steps}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'Local Oracle Select AI could not complete this request. No cloud fallback was attempted.') from None
    finally:
        REQUEST_SLOT.release()


def status(actor):
    user_features.require_governance(actor)
    if not enabled():
        return {'enabled': False}
    try:
        config = configuration()
        model_health()
        with connect(config) as connection:
            verify_profile(connection)
            version = connection.version
        return {'enabled': True, 'ready': True, 'model': MODEL, 'database': 'Oracle AI Database Free ' + version,
                'cloud_inference': False, 'external_provider_calls': 0, 'row_limit': ROW_LIMIT,
                'tables': {name: list(columns) for name, columns in TABLES.items()}}
    except HTTPException as error:
        return {'enabled': True, 'ready': False, 'detail': error.detail}
    except Exception:
        return {'enabled': True, 'ready': False, 'detail': 'The local database is unavailable. Cloud fallback is disabled.'}


def install(app, auth):
    @app.get('/api/governance/local-sql/status')
    def local_status(actor=Depends(auth)):
        return status(actor)

    @app.post('/api/governance/local-sql/query')
    def local_query(body: QueryInput, actor=Depends(auth)):
        return query(actor, body)
