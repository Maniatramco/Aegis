"""Access-scoped metadata governance; originals, results and model contracts stay unchanged."""
import hashlib
import json
import time
from collections import Counter
from typing import Literal

from fastapi import Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from . import core, dataset_access as access, user_features

CLASSIFICATIONS = ('unclassified', 'public', 'internal', 'confidential', 'restricted')
FIELDS = ('owner_name', 'steward', 'classification', 'purpose', 'retention_days', 'glossary')


class Term(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    definition: str = Field(min_length=1, max_length=2000)


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    expected_version: int = Field(ge=0, strict=True)
    owner_name: str = Field(default='', max_length=200)
    steward: str = Field(default='', max_length=200)
    classification: Literal['unclassified', 'public', 'internal', 'confidential', 'restricted'] = 'unclassified'
    purpose: str = Field(default='', max_length=2000)
    retention_days: int | None = Field(default=None, ge=1, le=36500, strict=True)
    glossary: list[Term] = Field(default_factory=list, max_length=50)
    change_reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def unique_terms(self):
        names = [term.name.casefold() for term in self.glossary]
        if len(set(names)) != len(names):
            raise ValueError('Glossary term names must be unique within a dataset.')
        return self


def require_manager(actor):
    user_features.require_governance(actor)
    # Persisted roles are mandatory here, including calls from test/CLI contexts.
    from . import governance_audit
    context = governance_audit.request_context.get()
    if context is not None and context['actor'] is None: context['actor'] = actor
    if not core.is_administrator(actor):
        raise HTTPException(403, 'Only an administrator can change governance or publish metadata to OCI.')


def scope(actor, ids, allow_retired=False):
    user_features.require_governance(actor)
    selected = set(ids)
    if len(selected) > 100:
        raise HTTPException(422, 'Choose up to 100 datasets.')
    with core.Session() as session:
        allowed = (set(session.scalars(select(core.Record.id).where(core.Record.kind == 'knowledge_base')))
                   if allow_retired and core.is_administrator(actor, session) else access.dataset_ids(actor, session))
        if not selected <= allowed:
            raise HTTPException(404, 'Dataset metadata is no longer accessible.')
    from . import governance_audit
    context = governance_audit.request_context.get()
    if context is not None and context['actor'] is None: context['actor'] = actor
    for id in selected: governance_audit.touch(id)
    return selected


def policy_id(dataset_id):
    return 'gov-' + hashlib.sha256(dataset_id.encode()).hexdigest()[:40]


def policy(dataset, session=None):
    if session is None:
        with core.Session() as active:
            return policy(dataset, active)
    record = session.get(core.Record, policy_id(dataset.id))
    owner = session.get(core.User, dataset.owner)
    default = dict(owner_name=owner.username if owner else '', steward='', classification='unclassified',
                   purpose='', retention_days=None, glossary=[], version=0, updated_at=None, updated_by=None,
                   change_reason='')
    if not record:
        return default
    try:
        data = core.store.json(record.ref)
        if not isinstance(data, dict):
            raise ValueError()
        # Validate persisted values too; unavailable policies must never look unclassified.
        checked = PolicyInput(**{key: data[key] for key in FIELDS}, expected_version=record.version,
                              change_reason=data['change_reason'])
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'Saved governance metadata is unavailable. No default policy was substituted.') from None
    return {**{key: checked.model_dump()[key] for key in FIELDS}, 'version': record.version,
            **{key: data.get(key) for key in ('updated_at', 'updated_by', 'change_reason')}}


def detail(actor, dataset_id):
    scope(actor, [dataset_id])
    with core.Session() as session:
        dataset = session.get(core.Record, dataset_id)
        saved = policy(dataset, session)
        record = session.get(core.Record, policy_id(dataset_id))
        history = []
        if record:
            for version in range(record.version, max(0, record.version - 20), -1):
                try:
                    data = core.store.json(f'governance/{record.id}/v{version}.json')
                    history.append({key: data.get(key) for key in ('version', 'updated_at', 'updated_by', 'change_reason', 'changed_fields')})
                except (OSError, ValueError):
                    history.append({'version': version, 'unavailable': True})
        result = {'dataset_id': dataset_id, 'name': dataset.name, 'policy': saved,
                  'history': history, 'history_total': record.version if record else 0,
                  'can_manage': core.is_administrator(actor, session)}
    scope(actor, [dataset_id])
    return result


def save(actor, dataset_id, body):
    require_manager(actor)
    scope(actor, [dataset_id])
    with core.document_lock('workspace-reset'), core.document_lock('governance-' + hashlib.sha256(dataset_id.encode()).hexdigest()):
        with core.Session() as session:
            dataset = session.get(core.Record, dataset_id)
            previous = policy(dataset, session)
            if previous['version'] != body.expected_version:
                raise HTTPException(409, 'Governance changed. Refresh and review the current policy before saving your draft.')
            changed = [key for key in FIELDS if previous[key] != body.model_dump()[key]]
            if not changed:
                return detail(actor, dataset_id)
            version = previous['version'] + 1
            user = session.get(core.User, actor)
            data = {key: body.model_dump()[key] for key in FIELDS} | {
                'version': version, 'updated_at': time.time(), 'updated_by': user.username,
                'change_reason': body.change_reason, 'changed_fields': changed}
            id = policy_id(dataset_id)
            reference = f'governance/{id}/v{version}.json'
            core.store.put_json(reference, data)
            # Recheck role/access in the publishing transaction after the object write.
            with core.Session.begin() as transaction:
                user_features.require_governance(actor, transaction)
                if not core.is_administrator(actor, transaction) or dataset_id not in access.dataset_ids(actor, transaction):
                    raise HTTPException(403, 'Governance access changed before saving.')
                record = transaction.get(core.Record, id)
                if record and record.version != previous['version']:
                    raise HTTPException(409, 'Governance changed. Refresh before saving.')
                if record:
                    record.ref = reference
                    record.version = version
                else:
                    transaction.add(core.Record(id=id, kind='governance', owner=dataset.owner,
                                                parent_id=dataset_id, name=dataset.name, ref=reference, version=version))
    return detail(actor, dataset_id)


def inventory(actor, ids):
    selected = scope(actor, ids)
    from .metadata_relationships import build
    nodes, edges, warnings = build(actor, selected)
    with core.Session() as session:
        policies = {id: policy(session.get(core.Record, id), session) for id in sorted(selected)}
    datasets = []
    for id in sorted(selected):
        node = next(node for node in nodes if node['id'] == 'dataset:' + id)
        counts = Counter(node['type'] for node in nodes if id in node['dataset_ids'])
        datasets.append({'id': id, 'name': node['label'], 'status': node['status'], 'policy': policies[id], 'counts': dict(counts)})
    scope(actor, selected)
    return {'dataset_ids': sorted(selected), 'datasets': datasets, 'records': nodes, 'relationships': edges,
            'warnings': warnings, 'generated_at': time.time(), 'can_manage': core.is_administrator(actor),
            'policy_effect': 'Classification and retention describe policy. Existing dataset grants enforce access. Retention does not delete files.'}


def catalog(actor, ids, search='', classification='', offset=0, limit=25):
    result = inventory(actor, ids)
    query = search.casefold().strip()
    matched = [d for d in result['datasets'] if (not classification or d['policy']['classification'] == classification)
               and (not query or query in json.dumps([d['name'], d['policy']], ensure_ascii=False).casefold())]
    totals = {'datasets': len(result['datasets']), 'records': len(result['records']),
              'relationships': len(result['relationships']),
              'classified': sum(d['policy']['classification'] != 'unclassified' for d in result['datasets']),
              'with_steward': sum(bool(d['policy']['steward']) for d in result['datasets']),
              'glossary_terms': sum(len(d['policy']['glossary']) for d in result['datasets'])}
    return {key: result[key] for key in ('dataset_ids', 'generated_at', 'warnings', 'can_manage', 'policy_effect')} | {
        'items': matched[offset:offset + limit], 'total_items': len(matched), 'offset': offset,
        'has_more': offset + limit < len(matched), 'totals': totals}


def install(app, auth):
    def enabled_actor(actor=Depends(auth)):
        user_features.require_governance(actor)
        return actor

    auth = enabled_actor
    @app.get('/api/governance/catalog')
    def get_catalog(dataset_id: list[str] = Query(default=[]), search: str = Query('', max_length=200),
                    classification: str = Query('', pattern='^(|unclassified|public|internal|confidential|restricted)$'),
                    offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), actor=Depends(auth)):
        return catalog(actor, dataset_id, search, classification, offset, limit)

    @app.get('/api/governance/datasets/{id}')
    def get_policy(id: str, actor=Depends(auth)):
        return detail(actor, id)

    @app.put('/api/governance/datasets/{id}')
    def put_policy(id: str, body: PolicyInput, actor=Depends(auth)):
        return save(actor, id, body)

    @app.get('/api/governance/export')
    def export(dataset_id: list[str] = Query(default=[]), actor=Depends(auth)):
        require_manager(actor)
        return Response(json.dumps(inventory(actor, dataset_id), ensure_ascii=False), media_type='application/json',
                        headers={'Content-Disposition': 'attachment; filename="aegis-governance-metadata.json"'})

    @app.get('/api/governance/lineage-export')
    def lineage_export(dataset_id: list[str] = Query(default=[]), actor=Depends(auth)):
        require_manager(actor)
        from .governance_oci import lineage_events
        events = list(lineage_events(inventory(actor, dataset_id)))
        return Response(''.join(json.dumps(event, ensure_ascii=False) + '\n' for event in events), media_type='application/x-ndjson',
                        headers={'Content-Disposition': 'attachment; filename="aegis-openlineage.ndjson"'})

    from . import governance_oci
    governance_oci.install(app, auth)
    from . import governance_controls
    governance_controls.install(app, auth)
    from . import local_select_ai
    local_select_ai.install(app, auth)
