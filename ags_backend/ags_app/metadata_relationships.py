"""Read-only, access-scoped workflow lineage. No inference, indexing or DDL."""
import hashlib
import time
from collections import Counter
from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from . import core, relational, dataset_access as access

TYPES = ('Dataset', 'Document', 'Extraction', 'Prompt', 'Review', 'Model')


def build(actor, dataset_ids):
    selected = set(dataset_ids)
    if len(selected) > 100:
        raise HTTPException(422, 'Choose up to 100 datasets for a relationship view.')
    nodes, edges, warnings = {}, {}, set()
    with core.Session() as session:
        allowed = access.dataset_ids(actor, session)
        if not selected <= allowed:
            raise HTTPException(404, 'Dataset metadata is no longer accessible.')
        model_ids = set(session.scalars(select(relational.DatasetModel.model_id).where(
            relational.DatasetModel.dataset_id.in_(allowed), relational.DatasetModel.enabled == True)))
        records = {r.id: r for r in session.scalars(select(core.Record).where(
            core.Record.kind.in_(['knowledge_base', 'document', 'extraction', 'template', 'model']),
            core.Record.status.notin_(['deleted', 'deleting'])))
            if access.allowed(r, actor, session, allowed, model_ids) and
            (r.kind == 'model' or r.id in selected or r.parent_id in selected or r.kind == 'template' and not r.parent_id)}
        reviews = list(session.scalars(select(relational.Review).where(
            relational.Review.extract_id.in_([r.id for r in records.values() if r.kind == 'extraction']))))

    def payload(record, version=None):
        reference = record.ref if version is None or version == record.version else f'{record.kind}/{record.id}/v{version}.json'
        try:
            data = core.store.json(reference)
            if not isinstance(data, dict): raise ValueError()
            return data
        except (OSError, ValueError):
            warnings.add('Some saved metadata could not be read. Unavailable links are omitted; no source values were guessed.')
            return {}

    def node(key, kind, label, scope, status='ready', version=None, attributes=None, action=None):
        if key not in nodes:
            nodes[key] = {'id': key, 'type': kind, 'label': label, 'dataset_ids': set(),
                          'status': status, 'version': version, 'attributes': attributes or {}, 'action': action}
        nodes[key]['dataset_ids'].update(set(scope) & selected)
        return key

    def edge(source, target, label, scope):
        if source not in nodes or target not in nodes: return
        key = hashlib.sha256(f'{source}|{target}|{label}'.encode()).hexdigest()[:24]
        if key not in edges:
            edges[key] = {'id': key, 'source': source, 'target': target, 'label': label, 'dataset_ids': set()}
        edges[key]['dataset_ids'].update(set(scope) & selected)

    def prompt(id, version, scope):
        record = records.get(id)
        if not record or record.kind != 'template': return None
        number = version if isinstance(version, int) and 1 <= version <= record.version else record.version
        data = payload(record, number)
        label = data.get('source_filename') or data.get('name') or record.name
        return node(f'prompt:{id}:v{number}', 'Prompt', label, scope, 'saved' if data else 'unavailable', number,
                    {'Prompt ID': id, 'Version': number, 'Snapshot': 'Current' if number == record.version else 'Historical'})

    def model(id, scope, selection=None):
        record = records.get(id)
        if not record or record.kind != 'model': return None
        saved = selection or {}
        number = saved.get('model_version') or record.version
        data = payload(record, number)
        label = saved.get('model_name') or data.get('name') or record.name
        return node(f'model:{id}:v{number}', 'Model', label, scope,
                    'disabled' if data.get('enabled') is False else 'saved', number,
                    {'Model ID': id, 'Version': number, 'Provider model': saved.get('provider_model') or data.get('provider_model') or 'Unavailable',
                     'Snapshot': 'Current registration' if number == record.version else 'Pinned historical selection'})

    configs = {}
    for id in sorted(selected):
        record = records.get(id)
        if not record: raise HTTPException(404, 'Dataset metadata is no longer accessible.')
        data = payload(record); configs[id] = data
        node('dataset:'+id, 'Dataset', record.name, [id], 'inactive' if data.get('active') is False else record.status,
             record.version, {'Dataset ID': id, 'Description': data.get('description', ''), 'Access': 'Authorized dataset'})
    for record in records.values():
        if record.kind == 'document':
            node('document:'+record.id, 'Document', record.name, [record.parent_id], record.status, record.version,
                 {'Document ID': record.id, 'Size bytes': record.size}, {'kind': 'document', 'id': record.id})
            edge('dataset:'+record.parent_id, 'document:'+record.id, 'contains', [record.parent_id])
        elif record.kind == 'template' and record.parent_id in selected:
            key = prompt(record.id, record.version, [record.parent_id])
            edge('dataset:'+record.parent_id, key, 'has prompt', [record.parent_id])
    for id, data in configs.items():
        for mapping in data.get('mappings', []):
            key = model(mapping.get('model_id'), [id])
            if not key: continue
            roles = [role for role, field in [('embedding', 'embedding_model_id'), ('chat', 'default_chat_model_id'), ('extraction', 'default_extraction_model_id')]
                     if data.get(field) == mapping.get('model_id')]
            label = 'mapped '+('/'.join(roles) if roles else 'model')
            if mapping.get('enabled') is False: label += ' (disabled)'
            edge('dataset:'+id, key, label, [id])
    for record in records.values():
        if record.kind != 'extraction': continue
        data = payload(record); scope = [record.parent_id]
        key = node('extraction:'+record.id, 'Extraction', record.name, scope, record.status, record.version,
                   {'Extraction ID': record.id, 'Version': record.version, 'Review status': data.get('review_status', 'unreviewed'),
                    'Prompt version': data.get('template_version') or 'Unavailable'}, {'kind': 'extraction', 'id': record.id})
        edge('dataset:'+record.parent_id, key, 'has extraction', scope)
        # The saved list, rather than the single-document SQL projection, preserves combined-run lineage.
        ids = set(data.get('document_ids') or [])
        merge = data.get('merge') or {}
        if merge.get('document_id'): ids.add(merge['document_id'])
        for id in ids: edge('document:'+id, key, 'source of', scope)
        if data.get('template_id'):
            pkey = prompt(data['template_id'], data.get('template_version'), scope)
            edge(pkey, key, 'used by', scope)
        selection = data.get('model_selection') or {}
        if selection.get('model_id'):
            mkey = model(selection['model_id'], scope, selection)
            edge(mkey, key, 'used by (pinned)', scope)
    for review in reviews:
        record = records.get(review.extract_id)
        if not record: continue
        scope = [record.parent_id]
        key = node('review:'+review.review_id, 'Review', record.name+' · review', scope, review.status, review.review_version,
                   {'Review ID': review.review_id, 'Extraction version reviewed': review.extraction_version,
                    'Saved review revision': review.review_version, 'Reviewed at': review.created_at},
                   {'kind': 'extraction', 'id': review.extract_id})
        edge('extraction:'+review.extract_id, key, 'reviewed in', scope)
    # Recheck grants after source reads before publishing the graph response.
    with core.Session() as session:
        if not selected <= access.dataset_ids(actor, session):
            raise HTTPException(404, 'Dataset metadata is no longer accessible.')
    for item in [*nodes.values(), *edges.values()]: item['dataset_ids'] = sorted(item['dataset_ids'])
    return sorted(nodes.values(), key=lambda n: (TYPES.index(n['type']), n['label'].casefold(), n['id'])), list(edges.values()), sorted(warnings)


def graph(actor, dataset_ids, level='overview', category='', focus='', offset=0, limit=40, search=''):
    nodes, edges, warnings = build(actor, dataset_ids)
    counts = Counter(n['type'] for n in nodes)
    totals = {'nodes': len(nodes), 'edges': len(edges), 'categories': dict(counts)}
    result = {'dataset_ids': sorted(set(dataset_ids)), 'level': level, 'totals': totals,
              'generated_at': time.time(), 'warnings': warnings, 'offset': offset, 'limit': limit}
    if level == 'overview':
        lookup = {n['id']: n for n in nodes}; grouped = {}
        for e in edges:
            source, target = lookup[e['source']]['type'], lookup[e['target']]['type']
            key = (source, target)
            grouped.setdefault(key, Counter())[e['label']] += 1
        return result | {'nodes': [{'id': kind, 'type': kind, 'label': kind, 'count': counts[kind], 'dataset_ids': sorted(set(dataset_ids)), 'status': 'category', 'attributes': {}}
                                  for kind in TYPES if counts[kind]],
                         'edges': [{'id': '|'.join(key), 'source': key[0], 'target': key[1],
                                    'label': next(iter(labels)) if len(labels) == 1 else 'mapped models' if key == ('Dataset', 'Model') else 'related via',
                                    'count': sum(labels.values()), 'relationships': dict(labels)}
                                   for key, labels in sorted(grouped.items())], 'items': [], 'total_items': len(nodes), 'has_more': False, 'truncated': False, 'related_total': len(nodes)}
    if category and category not in TYPES: raise HTTPException(422, 'Unknown metadata category.')
    lookup = {n['id']: n for n in nodes}
    if focus and focus not in lookup: raise HTTPException(404, 'Metadata record is no longer accessible.')
    query = search.strip().casefold()
    candidates = [n for n in nodes if (not category or n['type'] == category) and (not focus or n['id'] == focus)
                  and (not query or query in (n['label']+' '+n['type']+' '+str(n['attributes'])).casefold())]
    page = candidates[offset:offset+limit]; ids = {n['id'] for n in page}; related = set(ids)
    for e in edges:
        if e['source'] in ids or e['target'] in ids: related.update([e['source'], e['target']])
    # Keep browser rendering bounded. Exact category totals and list pagination remain complete.
    display = [*page, *[n for n in nodes if n['id'] in related and n['id'] not in ids]][:200]
    displayed = {n['id'] for n in display}
    return result | {'nodes': display, 'edges': [e for e in edges if e['source'] in displayed and e['target'] in displayed],
                     'items': page, 'total_items': len(candidates), 'has_more': offset+limit < len(candidates), 'truncated': len(related) > len(display), 'related_total': len(related)}


def install(app, auth):
    @app.get('/api/metadata-relationships')
    def relationships(dataset_id: list[str] = Query(default=[]), level: str = Query('overview', pattern='^(overview|instances)$'),
                      category: str = '', focus: str = '', offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100),
                      search: str = Query('', max_length=200), actor=Depends(auth)):
        return graph(actor, dataset_id, level, category, focus, offset, limit, search)
