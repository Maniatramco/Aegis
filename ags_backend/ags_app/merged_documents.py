"""Physical combined uploads with retained original boundaries and provenance."""
import io
import re
from . import core


def prepare(parts):
    from .worker import parse_document
    if not 2 <= len(parts) <= 20:
        raise ValueError('Merge requires between 2 and 20 files.')
    pdf = all(name.lower().endswith('.pdf') for name, _ in parts)
    writer = None
    if pdf:
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
    pages, sources = [], []
    pending=False
    for number, (name, raw) in enumerate(parts):
        name = name.replace('\\', '/').split('/')[-1][:200]
        # No model calls on the HTTP upload path. The worker reads all original
        # scans after durable upload, including mixed PDF/DOCX/TXT merges.
        parsed = parse_document(name, raw, ocr_enabled=False)
        pending=pending or name.lower().endswith('.docx') or any(p.get('ocr_pending') for p in parsed)
        key = str(number + 1)
        start = len(pages) + 1
        for item in parsed:
            pages.append({'page': len(pages) + 1, 'text': item['text'],
                          'source_key': key, 'source_filename': name, 'source_page': item['page']})
        sources.append({'key': key, 'name': name, 'size': len(raw), 'page_count': len(parsed),
                        'merged_page_start': start, 'merged_page_end': len(pages)})
        if pdf:
            writer.append(PdfReader(io.BytesIO(raw)))
    if len(pages) > 1000 or sum(len(p['text']) for p in pages) > 5000000:
        raise ValueError('Merged document exceeds the page or text processing limit. Choose fewer files.')
    stem = re.sub(r'[^\w.-]+', '-', parts[0][0].replace('\\', '/').split('/')[-1].rsplit('.', 1)[0])[:55] or 'documents'
    filename = f'merged-{stem}-{len(parts)}-files-{core.uid()[:8]}.{"pdf" if pdf else "txt"}'
    if pdf:
        out = io.BytesIO(); writer.write(out); raw = out.getvalue()
    else:
        raw = '\n\n'.join(f'--- Source {s["key"]}: {s["name"]} ---\n' + '\n'.join(p['text'] for p in pages if p['source_key'] == s['key']) for s in sources).encode('utf-8')
    return filename, raw, {'filename': filename, 'source_count': len(sources), 'sources': sources, 'pages': pages,'ocr_pending':pending}


def read_sources(document_id, metadata, progress=None):
    from .worker import parse_document
    pages=[]
    for source in metadata['sources']:
        raw=core.store.get(f'documents/{document_id}/merged-sources/{source["key"]}/original')
        parsed=parse_document(source['name'],raw,progress=progress,cache_id=document_id)
        for page in parsed:
            pages.append(page|{'page':len(pages)+1,'source_key':source['key'],
                'source_filename':source['name'],'source_page':page['page']})
    if len(pages)>1000 or sum(len(p['text']) for p in pages)>5000000:
        raise ValueError('Merged document exceeds processing limits. Choose fewer files.')
    metadata.update(pages=pages,ocr_pending=False)
    core.store.put_json(f'documents/{document_id}/merged.json',metadata)
    return pages


def save(document_id, manifest, parts):
    core.store.put_json(f'documents/{document_id}/merged.json', manifest)
    for source, (_, raw) in zip(manifest['sources'], parts):
        core.store.put(f'documents/{document_id}/merged-sources/{source["key"]}/original', raw)


def manifest(document_id):
    try:
        return core.store.json(f'documents/{document_id}/merged.json')
    except FileNotFoundError:
        return None


def public(value):
    return {key: value[key] for key in ('filename', 'source_count', 'sources')}


def records_schema(schema, sources):
    # Local references in the original schema keep pointing to its own root.
    return {'type': 'object', 'additionalProperties': False, '$defs': {'record': embedded_schema(schema)},
            'properties': {'records': {'type': 'array', 'minItems': len(sources), 'maxItems': len(sources),
                'items': False, 'prefixItems': [{'type': 'object', 'additionalProperties': False,
                    'properties': {'source_filename': {'const': source['name']}, 'source_key': {'const': source['key']},
                                   'fields': {'$ref': '#/$defs/record'}},
                    'required': ['source_filename', 'source_key', 'fields']} for source in sources]}}, 'required': ['records']}


def embedded_schema(schema):
    import copy
    value = copy.deepcopy(schema)
    def visit(node):
        if isinstance(node, dict):
            node.pop('$id', None)
            for key, item in node.items():
                if key in ('$ref', '$dynamicRef') and isinstance(item, str) and (item=='#' or item.startswith('#/')):
                    node[key] = '#/$defs/record' + item[1:]
                else: visit(item)
        elif isinstance(node, list):
            for item in node: visit(item)
    visit(value)
    return value
