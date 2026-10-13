"""Immutable, verified Parquet revisions; SQL publishes references only after readback."""
import hashlib
import io
import json
from . import core


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))


def persist(extraction_id, revision, data):
    import pyarrow as pa
    import pyarrow.parquet as pq
    result = data['result']
    records = result.get('records') if isinstance(result, dict) else None
    items = records if isinstance(records, list) else [{'fields': result}]
    rows = []
    for index, item in enumerate(items):
        fields = item.get('fields', item) if isinstance(item, dict) else item
        row = {'extraction_id': extraction_id, 'dataset_id': data['dataset_id'],
               'revision': revision, 'record_index': index,
               'source_filename': item.get('source_filename') if isinstance(item, dict) else None,
               'source_key': item.get('source_key') if isinstance(item, dict) else None,
               'fields_json': encoded(fields)}
        # Columns keep native scalar/array/struct types, alongside lossless JSON.
        if isinstance(fields, dict):
            row.update({'field_' + key: value for key, value in fields.items()})
        rows.append(row)
    try:
        # JSON schema permits empty objects and heterogeneous arrays; Arrow
        # cannot represent every valid JSON value as one nested native type.
        # Preserve those columns as explicit JSON with an encoding manifest.
        json_columns = []
        columns = {}
        for key in dict.fromkeys(key for row in rows for key in row):
            values = [row.get(key) for row in rows]
            try:
                column = pa.array(values)
                def empty_struct(kind):
                    if pa.types.is_struct(kind): return not len(kind) or any(empty_struct(f.type) for f in kind)
                    if pa.types.is_list(kind): return empty_struct(kind.value_type)
                    return False
                if empty_struct(column.type): raise ValueError('Empty struct requires JSON encoding')
            except (pa.ArrowException, ValueError, TypeError):
                if not key.startswith('field_'): raise
                column = pa.array([encoded(value) for value in values]); json_columns.append(key)
            columns[key] = column
        table = pa.table(columns)
        metadata = {b'aegis.result': encoded(result).encode(),
                    b'aegis.provenance': encoded({key: data.get(key) for key in
                        ('dataset_id', 'document_ids', 'template_id', 'template_version',
                         'index_versions', 'evidence', 'reviewed_by', 'reviewed_at')}).encode()}
        metadata[b'aegis.json_columns'] = encoded(json_columns).encode()
        table = table.replace_schema_metadata(metadata)
        buffer = io.BytesIO(); pq.write_table(table, buffer, compression='zstd')
        payload = buffer.getvalue(); digest = hashlib.sha256(payload).hexdigest()
        # Content addressed revision prevents failed/orphan writes from replacing
        # a previously published file, including recovery after process death.
        reference = f'extraction/{extraction_id}/results/v{revision}-{digest[:16]}.parquet'
        core.store.put(reference, payload)
        saved = core.store.get(reference)
        if hashlib.sha256(saved).hexdigest() != digest:
            raise ValueError('Persisted Parquet checksum differs from the written output')
        restored = decode(saved)
        if encoded(restored) != encoded(result):
            raise ValueError('Persisted Parquet result differs from validated fields')
    except Exception as error:
        raise ValueError('Parquet persistence/readback failed. The extraction is not complete; retry the saved job or review draft.') from error
    return {'output_reference': reference, 'output_sha256': digest,
            'output_format': 'parquet', 'review_revision': revision}


def decode(payload):
    import pyarrow.parquet as pq
    table = pq.read_table(io.BytesIO(payload))
    metadata = table.schema.metadata or {}
    result = json.loads(metadata[b'aegis.result'])
    rows = table.to_pylist()
    for row in rows:
        for key in json.loads(metadata.get(b'aegis.json_columns', b'[]')):
            row[key] = json.loads(row[key])
    items = result.get('records') if isinstance(result, dict) else None
    expected = items if isinstance(items, list) else [{'fields': result}]
    if len(rows) != len(expected):
        raise ValueError('Parquet record count does not match its result metadata')
    for row, item in zip(rows, expected):
        fields = item.get('fields', item) if isinstance(item, dict) else item
        if encoded(json.loads(row['fields_json'])) != encoded(fields):
            raise ValueError('Parquet record fields do not match result metadata')
        if isinstance(fields, dict) and any(encoded(row.get('field_' + key)) != encoded(value) for key, value in fields.items()):
            raise ValueError('Parquet typed fields do not match lossless fields')
    return result


def load(data):
    reference = data.get('output_reference')
    if not reference:
        return data  # Existing historical JSON remains readable; new runs use Parquet.
    payload = core.store.get(reference)
    if hashlib.sha256(payload).hexdigest() != data['output_sha256']:
        raise ValueError('Saved Parquet integrity check failed; reload or contact the administrator')
    return dict(data, result=decode(payload))
