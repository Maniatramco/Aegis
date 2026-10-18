"""Approved operational policies, immediate preservation holds and privacy gates."""
import json
import re
import time
from contextlib import contextmanager
from typing import Literal
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import core, governance, governance_audit as audit


class QualityRule(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    field: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z_][A-Za-z0-9_.-]*$')
    check: Literal['required', 'unique', 'minimum', 'maximum', 'allowed_values']
    threshold: float | None = None
    allowed_values: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def options(self):
        import math
        if self.check in ('minimum', 'maximum') and (self.threshold is None or not math.isfinite(self.threshold)):
            raise ValueError('A finite threshold is required.')
        if self.check == 'allowed_values' and not self.allowed_values:
            raise ValueError('Specify allowed values.')
        if any(len(value) > 200 for value in self.allowed_values):
            raise ValueError('Allowed values must be at most 200 characters.')
        return self


class Controls(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    masking_enabled: bool = False
    sensitive_fields: list[str] = Field(default_factory=list, max_length=100)
    freshness_days: int = Field(default=30, ge=1, le=36500, strict=True)
    require_review: bool = True
    rules: list[QualityRule] = Field(default_factory=list, max_length=100)
    auto_quality: bool = True
    quality_interval_minutes: int = Field(default=60, ge=15, le=10080, strict=True)
    auto_sync: bool = False
    sync_interval_minutes: int = Field(default=1440, ge=15, le=10080, strict=True)
    retention_action: Literal['none', 'archive', 'purge'] = 'none'
    retention_days: int | None = Field(default=None, ge=1, le=36500, strict=True)
    purge_grace_days: int = Field(default=30, ge=7, le=3650, strict=True)

    @model_validator(mode='after')
    def decisions(self):
        if self.retention_action != 'none' and self.retention_days is None:
            raise ValueError('An explicit retention period is required before enabling retention.')
        if any(not value or len(value) > 120 or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*', value) for value in self.sensitive_fields):
            raise ValueError('Sensitive fields must be identifiers or dotted field paths.')
        return self


class Proposal(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    expected_version: int = Field(ge=0, strict=True)
    reason: str = Field(min_length=1, max_length=500)
    controls: Controls


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    proposal_id: str = Field(min_length=1, max_length=80)
    approve: bool
    reason: str = Field(min_length=1, max_length=500)


class Hold(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    expected_version: int = Field(ge=0, strict=True)
    active: bool
    reason: str = Field(min_length=1, max_length=500)


def root(dataset_id):
    return 'governance/' + governance.policy_id(dataset_id)


def _read(ref, default):
    try:
        return core.store.json(ref)
    except FileNotFoundError:
        return default
    except (ValueError, OSError, TypeError):
        raise HTTPException(503, 'Saved operational governance state is unavailable. Controls were not bypassed.') from None


def active(dataset_id):
    id = 'gctl-' + governance.policy_id(dataset_id)[4:]
    with core.Session() as session:
        record = session.get(core.Record, id)
    if not record:
        if _read(root(dataset_id) + '/controls.json', None) is not None:
            raise HTTPException(503, 'Operational governance is missing its authoritative catalog reference.')
        return {'version': 0, 'controls': Controls().model_dump(), 'approved_by': None, 'proposed_by': None}
    saved = _read(record.ref, None)
    try:
        if not saved or record.kind != 'governance_control' or saved['version'] != record.version or saved['proposed_by'] == saved['approved_by']:
            raise ValueError()
        saved['controls'] = Controls(**saved['controls']).model_dump()
        return saved
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503, 'Saved operational governance policy is invalid. Controls were not bypassed.') from None


def hold(dataset_id):
    id = 'ghold-' + governance.policy_id(dataset_id)[4:]
    with core.Session() as session:
        record = session.get(core.Record, id)
    if record:
        saved = _read(record.ref, None)
        if not saved or record.kind != 'governance_hold' or saved.get('version') != record.version:
            raise HTTPException(503, 'Saved legal hold cannot be verified. Deletion is blocked.')
    else:
        saved = _read(root(dataset_id) + '/hold.json', {'version': 0, 'active': False})
    if not isinstance(saved, dict) or type(saved.get('active')) is not bool or type(saved.get('version')) is not int:
        raise HTTPException(503, 'Legal hold status cannot be verified. Deletion is blocked.')
    return saved


def publish_state(actor, dataset_id, kind, reference, version, proposer=None):
    """SQL publishes a pointer only after its immutable object was persisted."""
    id = ('gctl-' if kind == 'governance_control' else 'ghold-') + governance.policy_id(dataset_id)[4:]
    with core.Session.begin() as session:
        from .user_features import require_governance
        require_governance(actor, session)
        if not core.is_administrator(actor, session):
            raise HTTPException(403, 'Administrator access changed before publishing governance.')
        if proposer and not core.is_administrator(proposer, session):
            raise HTTPException(403, 'The proposing administrator lost access before approval.')
        if proposer:
            require_governance(proposer, session)
        dataset = session.get(core.Record, dataset_id)
        if not dataset or dataset.kind != 'knowledge_base': raise HTTPException(404, 'Dataset not found.')
        record = session.get(core.Record, id)
        if record:
            if record.version != version - 1: raise HTTPException(409, 'Governance state changed before publishing.')
            record.ref = reference; record.version = version
        else:
            if version != 1: raise HTTPException(409, 'Governance state changed before publishing.')
            session.add(core.Record(id=id, kind=kind, owner=dataset.owner, parent_id=dataset_id,
                                    name=dataset.name, ref=reference, version=version))


def ensure_no_hold(dataset_id):
    if dataset_id and hold(dataset_id)['active']:
        raise HTTPException(409, 'This dataset is under legal hold. Deletion and workspace archival are blocked.')


@contextmanager
def deletion_guard(dataset_id):
    with core.document_lock('governance-hold-' + governance.policy_id(dataset_id)):
        ensure_no_hold(dataset_id)
        yield


def detail(actor, dataset_id):
    governance.scope(actor, [dataset_id], allow_retired=True)
    current = active(dataset_id)
    pending = _read(root(dataset_id) + '/pending.json', None)
    if pending and pending['status'] == 'pending' and current.get('proposal_id') == pending['id']:
        pending = dict(pending, status='approved', decided_by=current['approved_by'],
                       decided_at=current['approved_at'], decision_reason=current.get('approval_reason', ''))
    result = {'dataset_id': dataset_id, 'active': current, 'hold': hold(dataset_id), 'pending': pending,
              'can_manage': core.is_administrator(actor),
              'can_approve': bool(pending and pending['status'] == 'pending' and pending['proposed_by'] != actor and core.is_administrator(actor))}
    with core.Session() as session:
        def name(id):
            user = session.get(core.User, id) if id else None
            return user.username if user else 'Former administrator'
        result['active'] = dict(current, approved_by_name=name(current.get('approved_by')),
                                proposed_by_name=name(current.get('proposed_by')))
        if pending: result['pending'] = dict(pending, proposed_by_name=name(pending['proposed_by']))
        result['hold'] = dict(result['hold'], updated_by_name=name(result['hold'].get('updated_by')))
    result['can_release_hold'] = bool(result['can_manage'] and result['hold'].get('placed_by') != actor)
    governance.scope(actor, [dataset_id], allow_retired=True)
    if not result['can_manage']:
        result['pending'] = None
    return result


def propose(actor, dataset_id, body):
    governance.require_manager(actor)
    governance.scope(actor, [dataset_id])
    with core.document_lock('workspace-reset'), core.document_lock('governance-controls-' + governance.policy_id(dataset_id)):
        current = active(dataset_id)
        if current['version'] != body.expected_version:
            raise HTTPException(409, 'Operational policy changed. Refresh before proposing changes.')
        pending = _read(root(dataset_id) + '/pending.json', None)
        if pending and current.get('proposal_id') == pending['id']:
            pending = dict(pending, status='approved', decided_by=current['approved_by'], decided_at=current['approved_at'],
                           decision_reason=current.get('approval_reason', ''))
            core.store.put_json(root(dataset_id) + '/pending.json', pending)
            core.store.put_json(root(dataset_id) + '/proposals/' + pending['id'] + '.json', pending)
        if pending and pending['status'] == 'pending':
            raise HTTPException(409, 'Review or reject the current proposal before submitting another.')
        saved = body.model_dump() | {'id': core.uid(), 'status': 'pending', 'proposed_by': actor, 'proposed_at': time.time()}
        governance.require_manager(actor)
        governance.scope(actor, [dataset_id])
        audit.append(actor, 'governance.controls.proposed', dataset_ids=[dataset_id])
        core.store.put_json(root(dataset_id) + '/pending.json', saved)
        core.store.put_json(root(dataset_id) + '/proposals/' + saved['id'] + '.json', saved)
    return detail(actor, dataset_id)


def decide(actor, dataset_id, body):
    governance.require_manager(actor)
    governance.scope(actor, [dataset_id])
    with core.document_lock('workspace-reset'), core.document_lock('governance-controls-' + governance.policy_id(dataset_id)):
        pending = _read(root(dataset_id) + '/pending.json', None)
        if not pending or pending['id'] != body.proposal_id or pending['status'] != 'pending':
            raise HTTPException(409, 'The pending proposal changed or was already decided.')
        if body.approve and pending['proposed_by'] == actor:
            raise HTTPException(403, 'A different administrator must approve operational policies.')
        current = active(dataset_id)
        if current.get('proposal_id') == pending['id']:
            pending.update(status='approved', decided_by=current['approved_by'], decided_at=current['approved_at'],
                           decision_reason=current.get('approval_reason', ''))
            core.store.put_json(root(dataset_id) + '/pending.json', pending)
            core.store.put_json(root(dataset_id) + '/proposals/' + pending['id'] + '.json', pending)
            return detail(actor, dataset_id)
        if body.approve and current['version'] != pending['expected_version']:
            raise HTTPException(409, 'The active policy changed. Reject and resubmit the proposal.')
        if body.approve:
            governance.require_manager(pending['proposed_by'])
            governance.scope(pending['proposed_by'], [dataset_id])
            checked = Controls(**pending['controls']).model_dump()
            saved = {'version': current['version'] + 1, 'controls': checked,
                     'proposed_by': pending['proposed_by'], 'approved_by': actor,
                     'approved_at': time.time(), 'proposal_id': pending['id'], 'reason': pending['reason'], 'approval_reason': body.reason}
            audit.append(actor, 'governance.controls.approval_attempted', dataset_ids=[dataset_id])
            ref = root(dataset_id) + '/controls-v' + str(saved['version']) + '.json'
            core.store.put_json(ref, saved)
            publish_state(actor, dataset_id, 'governance_control', ref, saved['version'], pending['proposed_by'])
            audit.append(actor, 'governance.controls.approved', dataset_ids=[dataset_id])
        pending.update(status='approved' if body.approve else 'rejected', decided_by=actor,
                       decided_at=time.time(), decision_reason=body.reason)
        core.store.put_json(root(dataset_id) + '/proposals/' + pending['id'] + '.json', pending)
        core.store.put_json(root(dataset_id) + '/pending.json', pending)
    return detail(actor, dataset_id)


def set_hold(actor, dataset_id, body):
    governance.require_manager(actor)
    governance.scope(actor, [dataset_id], allow_retired=True)
    with core.document_lock('workspace-reset'), core.document_lock('governance-hold-' + governance.policy_id(dataset_id)):
        previous = hold(dataset_id)
        if previous['version'] != body.expected_version:
            raise HTTPException(409, 'Legal hold changed. Refresh before continuing.')
        if not body.active and previous.get('placed_by') == actor:
            raise HTTPException(403, 'A different administrator must release this legal hold.')
        saved = {'active': body.active, 'version': previous['version'] + 1, 'reason': body.reason,
                 'updated_at': time.time(), 'updated_by': actor,
                 'placed_by': actor if body.active else previous.get('placed_by')}
        audit.append(actor, 'governance.hold.place_attempted' if body.active else 'governance.hold.release_attempted', dataset_ids=[dataset_id], status='attempted')
        ref = root(dataset_id) + '/hold-v' + str(saved['version']) + '.json'
        core.store.put_json(ref, saved)
        publish_state(actor, dataset_id, 'governance_hold', ref, saved['version'])
        audit.append(actor, 'governance.hold.placed' if body.active else 'governance.hold.released', dataset_ids=[dataset_id])
    return detail(actor, dataset_id)


def restricted_datasets(actor, ids):
    if core.is_administrator(actor):
        return set()
    return {id for id in ids if active(id)['controls']['masking_enabled']}


def safe_reader_path():
    context = audit.request_context.get()
    if context is None:
        return False
    path = context['path']
    if context['method'] != 'GET':
        return False
    return (path in ('/api/datasets', '/api/knowledge-bases', '/api/extractions', '/api/extract-data', '/api/extract-data/export', '/api/metadata-relationships', '/api/dataset-chat/catalog', '/api/dataset-chat/conversations')
            or path.startswith('/api/governance/')
            or re.fullmatch(r'/api/dataset-chat/conversations/[^/]+', path) is not None
            or re.fullmatch(r'/api/extractions/[^/]+(?:/versions|/export)?', path) is not None)


def dashboard_chat_request():
    context = audit.request_context.get()
    return bool(context and context['method'] == 'POST' and context['path'] in ('/api/dataset-chat/messages', '/api/dataset-chat/reply'))


def ensure_grounded_chat_allowed(actor, dataset_ids):
    if restricted_datasets(actor, dataset_ids):
        raise HTTPException(403, 'This dataset privacy policy permits general chat and masked results. Grounded chat and original-source access are restricted.')


def ensure_chat_history_allowed(actor, data):
    if restricted_datasets(actor, data.get('dataset_ids', [])) and any(
            message.get('role') == 'assistant' and
            (message.get('request_route') or {}).get('routing_mode') != 'dataset_general_chat'
            for message in data.get('messages', [])):
        raise HTTPException(403, 'Saved grounded chat is restricted by this dataset privacy policy. Start a separate general conversation.')


def filter_scope(actor, ids):
    # Internal workers retain their processing contracts. Only HTTP reads and
    # writes are subject to this privacy boundary; masked readers cannot reach
    # originals, source previews, chats, indexing, or unredacted Parquet.
    if audit.request_context.get() is None or core.is_administrator(actor) or safe_reader_path() or dashboard_chat_request():
        return ids
    return ids - restricted_datasets(actor, ids)


SENSITIVE_KEYS = {'email', 'emailaddress', 'phone', 'phonenumber', 'mobile', 'mobilenumber', 'ssn', 'socialsecuritynumber',
                  'aadhaar', 'aadharnumber', 'aadhaarnumber', 'pan', 'pannumber', 'passport', 'passportnumber',
                  'bankaccount', 'bankaccountnumber', 'accountnumber', 'iban', 'creditcard', 'creditcardnumber', 'dob', 'dateofbirth', 'address'}
PATTERNS = {
    'email': re.compile(r'(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?!\w)'),
    'ssn': re.compile(r'(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)'),
    'pan': re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b'),
    'iban': re.compile(r'\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b'),
    'phone_or_account': re.compile(r'(?<![\w-])(?:\+\d{1,3}[ -]?)?(?:\d[ -]?){10,19}(?![\w-])'),
}


def sensitive_counts(value, fields=()):
    counts = {}
    keys = SENSITIVE_KEYS | {re.sub(r'[^a-z0-9]', '', field.casefold().split('.')[-1]) for field in fields}
    def visit(item, key=''):
        normalized = re.sub(r'[^a-z0-9]', '', key.casefold())
        if normalized in keys and item not in (None, '', [], {}):
            counts['sensitive_field'] = counts.get('sensitive_field', 0) + 1
        if isinstance(item, dict):
            for child, value in item.items(): visit(value, child)
        elif isinstance(item, list):
            for child in item: visit(child, key)
        elif isinstance(item, str):
            for name, pattern in PATTERNS.items():
                count = len(pattern.findall(item))
                if count: counts[name] = counts.get(name, 0) + count
    visit(value)
    return counts


def masked(actor, record, value):
    policy = active(record.parent_id) if record.parent_id else {'version': 0, 'controls': Controls().model_dump()}
    controls = policy['controls']
    if core.is_administrator(actor) or not controls['masking_enabled']:
        return value
    keys = SENSITIVE_KEYS | {re.sub(r'[^a-z0-9]', '', field.casefold().split('.')[-1]) for field in controls['sensitive_fields']}
    def visit(item, key=''):
        if re.sub(r'[^a-z0-9]', '', key.casefold()) in keys and item is not None:
            return '[REDACTED]'
        if isinstance(item, dict): return {key: visit(value, key) for key, value in item.items()}
        if isinstance(item, list): return [visit(value) for value in item]
        if isinstance(item, str):
            for pattern in PATTERNS.values(): item = pattern.sub('[REDACTED]', item)
        return item
    result = visit(value)
    context = audit.request_context.get()
    if context is not None: context.setdefault('masked_versions', {})[record.parent_id] = policy['version']
    if isinstance(result, dict):
        result.pop('output_reference', None)
        result.pop('output_sha256', None)
        result['governance_masked'] = True
    return result


def install(app, auth):
    @app.get('/api/governance/datasets/{id}/controls')
    def get_controls(id: str, actor=Depends(auth)):
        return detail(actor, id)

    @app.post('/api/governance/datasets/{id}/controls/proposals')
    def propose_controls(id: str, body: Proposal, actor=Depends(auth)):
        return propose(actor, id, body)

    @app.post('/api/governance/datasets/{id}/controls/decision')
    def decide_controls(id: str, body: Decision, actor=Depends(auth)):
        return decide(actor, id, body)

    @app.put('/api/governance/datasets/{id}/hold')
    def change_hold(id: str, body: Hold, actor=Depends(auth)):
        return set_hold(actor, id, body)

    @app.get('/api/governance/audit')
    def audit_events(dataset_id: list[str] = Query(default=[]), offset: int = Query(0, ge=0),
                     limit: int = Query(50, ge=1, le=200), actor=Depends(auth)):
        return audit.read(actor, dataset_id, offset, limit)

    from . import governance_quality, governance_automation, governance_retention
    governance_quality.install(app, auth)
    governance_automation.install(app, auth)
    governance_retention.install(app, auth)
