"""Dataset/prompt result tables, built from the latest verified saved revisions."""
import csv
import io
import json
from .result_exports import safe, xlsx

METADATA = [('dataset', 'Dataset'), ('prompt_template', 'Prompt template'),
            ('document', 'Document'), ('extraction', 'Extraction'),
            ('extraction_id', 'Extraction ID'), ('version', 'Saved version'),
            ('template_version', 'Prompt version'), ('record_number', 'Record'),
            ('review_status', 'Review status'), ('extracted_at', 'Extracted time')]


def fields(value, path=''):
    # Arrays remain one lossless cell: expanding them would duplicate records.
    if isinstance(value, dict) and value:
        for key, item in value.items():
            escaped = str(key).replace('~', '~0').replace('/', '~1')
            yield from fields(item, path + '/' + escaped)
    else:
        yield 'field:' + (path or '/'), value


def table(items):
    rows, paths = [], {}
    for record, data, dataset, template, documents in items:
        result = data['result']
        records = result.get('records') if isinstance(result, dict) else result if isinstance(result, list) else None
        entries = records if isinstance(records, list) else [result]
        for index, item in enumerate(entries):
            wrapped = isinstance(records, list) and isinstance(item, dict) and 'fields' in item
            value = item['fields'] if wrapped else item
            document = item.get('source_filename') if wrapped else None
            row = dict(dataset=dataset, prompt_template=template,
                       document=document or ', '.join(documents) or record.name,
                       extraction=record.name, extraction_id=record.id,
                       version=record.version, template_version=data.get('template_version', 1),
                       record_number=index + 1, review_status=data.get('review_status') or 'unreviewed',
                       extracted_at=record.created_at)
            for key, value in fields(value):
                row[key] = value
                label = ' › '.join(part.replace('~1', '/').replace('~0', '~').replace('_', ' ') for part in key[6:].strip('/').split('/')) or 'Result'
                paths.setdefault(key, label)
            rows.append(row)
    return {'columns': [{'key': key, 'label': label, 'kind': 'metadata'} for key, label in METADATA]
            + [{'key': key, 'label': label, 'kind': 'field'} for key, label in paths.items()],
            'rows': rows, 'total': len(rows), 'extraction_count': len(items), 'saved_values_only': True}


def cell(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False) if value is not None else ''


def render(data, format):
    if format == 'json':
        return json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2).encode(), 'application/json'
    columns = data['columns']
    # Equal field/metadata labels must never overwrite a column in CSV readers.
    labels = [column['label'] for column in columns]
    headers = [f"{column['label']} ({column['key']})" if labels.count(column['label']) > 1 else column['label'] for column in columns]
    values = [headers] + [[cell(row.get(column['key'])) for column in columns] for row in data['rows']]
    if format == 'xlsx':
        if len(columns) > 16384:
            raise ValueError('Results exceed the Excel column limit. Use CSV or JSON.')
        return xlsx(values), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    if format == 'csv':
        out = io.StringIO(newline='')
        csv.writer(out).writerows([[safe(value) for value in row] for row in values])
        return ('\ufeff' + out.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8'
    raise ValueError('Export format must be xlsx, csv or json')
