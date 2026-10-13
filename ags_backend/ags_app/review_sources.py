"""Read-only, revision-pinned original evidence for a saved extraction citation."""
from fastapi import HTTPException
from . import core, parquet_results


def evidence(id, owner, version, record_index, main):
    record = main.get_record(id, owner, 'extraction')
    version = version or record.version
    if version > record.version:
        raise HTTPException(404, 'Saved extraction version is unavailable.')
    try:
        data = core.store.json(record.ref if version == record.version else f'extraction/{id}/v{version}.json')
        data = parquet_results.load(data)
    except (OSError, ValueError, KeyError):
        raise HTTPException(503, 'This saved source revision could not be read. Please retry.')
    result = data.get('result')
    if result is None:raise HTTPException(409, 'This extraction revision has no completed result.')
    items = result.get('records') if isinstance(result, dict) else None
    items = items if isinstance(items, list) else [{'fields': result}]
    if record_index >= len(items):raise HTTPException(404, 'Extracted record is unavailable.')
    item = items[record_index]
    fields = item.get('fields', item) if isinstance(item, dict) else item
    source_key = item.get('source_key') if isinstance(item, dict) else None
    merge = data.get('merge') or {}
    merged = merge.get('sources') or []
    matched = next((s for s in merged if s.get('key') == source_key), None)
    allowed = set(data.get('document_ids', [])) | {s.get('document_id') for s in merged}
    if merge.get('document_id'):allowed.add(merge['document_id'])
    origins, seen = [], set()

    def origin(source, field_evidence=False):
        key = source.get('source_key')
        if source_key and key and key != source_key:return
        if matched and source.get('document_id') and source['document_id'] not in {matched.get('document_id'),merge.get('document_id')}:return
        original = next((s for s in merged if s.get('key') == key), None) or matched
        document_id = source.get('document_id') or (original or {}).get('document_id')
        if document_id not in allowed:return
        if original and merge.get('document_id'):
            main.get_record(merge['document_id'], owner, 'document')
            base = f'/documents/{merge["document_id"]}/merged-sources/{original["key"]}'
            name = original.get('name') or original.get('filename') or 'Original document'
            page = source.get('source_page')
        else:
            document = main.get_record(document_id, owner, 'document')
            base, name = '/documents/' + document.id, document.name
            page = source.get('page')
        page = page if isinstance(page, int) and not isinstance(page, bool) and page > 0 else None
        quote = source.get('quote') or source.get('text') or ''
        identity = (base, page, quote, field_evidence)
        if identity in seen:return
        seen.add(identity)
        origins.append({'document_id': document_id, 'document_name': name, 'page': page,
                        'source_base': base, 'excerpt': quote, 'field': source.get('field'),
                        'field_evidence': field_evidence, 'ocr': source.get('ocr')})

    for source in data.get('evidence', []):
        path = source.get('field') or source.get('path') or source.get('json_pointer') or ''
        if len(items) > 1 and path.startswith('/records/') and not path.startswith(f'/records/{record_index}/'):continue
        origin(source, True)
    for source in data.get('sources', []):origin(source)
    if not origins:
        for document_id in data.get('document_ids', []):
            if matched and matched.get('document_id'):
                origin({'document_id': matched['document_id'], 'source_key': source_key})
                break
            origin({'document_id': document_id})
    return {'extraction_id': id, 'extraction_name': record.name, 'version': version,
            'record_index': record_index, 'fields': fields,
            'review_status': data.get('review_status', 'unreviewed'), 'sources': origins,
            'evidence_notice': 'Recorded passages are shown below. A missing field quote or page does not establish a field-level location.'}
