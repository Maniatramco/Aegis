"""Per-account feature access, published through the existing SQL catalog.

The exact persisted username ``mani`` is the initial governance pilot. An
explicit administrator decision, including disabling mani, takes precedence.
Grants reference immutable control-volume snapshots; missing snapshots deny
access rather than restoring a default. Dataset grants and roles stay separate.
"""
import hashlib
import time

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import select

from . import core

KIND = 'user_feature_access'


class Features(BaseModel):
    model_config = ConfigDict(extra='forbid')
    data_governance: StrictBool


class Snapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')
    user_id: str
    version: int = Field(ge=1, strict=True)
    features: Features
    updated_at: float
    updated_by: str


def record_id(user_id):
    return 'ufea-' + hashlib.sha256(user_id.encode()).hexdigest()[:40]


def public(user, session=None):
    if session is None:
        with core.Session() as active:
            return public(user, active)
    if not user:
        return {'features': {'data_governance': False}, 'feature_access_version': 0,
                'feature_access_updated_at': None, 'feature_access_updated_by': None}
    record = session.get(core.Record, record_id(user.id))
    if not record:
        return {'features': {'data_governance': user.username == 'mani'}, 'feature_access_version': 0,
                'feature_access_updated_at': None, 'feature_access_updated_by': None}
    try:
        if record.kind != KIND or record.owner != user.id or not record.ref.startswith('configuration/user-features/' + record.id + '/'):
            raise ValueError('Invalid grant reference')
        saved = Snapshot.model_validate(core.local_store.json(record.ref))
        if saved.user_id != user.id or saved.version != record.version:
            raise ValueError('Grant version mismatch')
    except (OSError, ValueError, TypeError, KeyError):
        raise HTTPException(503, 'Feature access could not be verified. Data Governance remains unavailable.') from None
    return {'features': saved.features.model_dump(), 'feature_access_version': saved.version,
            'feature_access_updated_at': saved.updated_at, 'feature_access_updated_by': saved.updated_by}


def governance_enabled(actor, session=None):
    if session is None:
        with core.Session() as active:
            return governance_enabled(actor, active)
    return public(session.get(core.User, actor), session)['features']['data_governance']


def summary(user, session=None):
    """Keep account administration available when one entitlement is damaged."""
    try:
        return public(user, session) | {'feature_access_available': True}
    except HTTPException as error:
        if error.status_code != 503:
            raise
        return {'features': {'data_governance': False}, 'feature_access_version': None,
                'feature_access_updated_at': None, 'feature_access_updated_by': None,
                'feature_access_available': False}


def require_governance(actor, session=None):
    from .governance_audit import request_context
    context = request_context.get()
    if context is not None and context['actor'] is None:
        context['actor'] = actor
    if not governance_enabled(actor, session):
        raise HTTPException(403, 'Data Governance is disabled for your account. Ask an administrator to enable it under Users & passwords > Feature access.')


def save(actor, user_id, features, expected_version, *, current_password=None):
    """Persist an admin decision; HTTP callers must provide their password.

    Trusted fixture/operator calls may omit the password but still require an
    actual persisted administrator. No governance entitlement is required to
    administer feature access, so the pilot cannot lock administrators out.
    """
    from . import governance_audit as audit, user_management
    with core.document_lock('administrator-auth'), core.document_lock('user-feature-access'), user_management.account_audit(actor):
        with core.Session.begin() as session:
            accounts = list(session.scalars(select(core.User).order_by(core.User.id).with_for_update()))
            administrator = next((user for user in accounts if user.id == actor), None)
            if not administrator or administrator.role != 'administrator':
                raise HTTPException(403, 'Administrator access required.')
            if current_password is not None:
                user_management.verify_password(administrator, current_password)
            user = next((user for user in accounts if user.id == user_id), None)
            if not user:
                raise HTTPException(404, 'User not found.')
            previous = public(user, session)
            if previous['feature_access_version'] != expected_version:
                raise HTTPException(409, 'Feature access changed. Refresh this user and review the current setting before saving.')
            saved = Snapshot(user_id=user.id, version=expected_version + 1, features=Features.model_validate(features),
                             updated_at=time.time(), updated_by=actor)
            id = record_id(user.id)
            reference = f'configuration/user-features/{id}/v{saved.version}-{core.uid()}.json'
            core.local_store.put_json(reference, saved.model_dump())
            if Snapshot.model_validate(core.local_store.json(reference)) != saved:
                raise HTTPException(503, 'Feature access could not be saved and verified. No grant was published.')
            audit.append(actor, 'user.features.change_attempted')
            record = session.get(core.Record, id)
            if record:
                record.ref = reference
                record.version = saved.version
            else:
                session.add(core.Record(id=id, kind=KIND, owner=user.id, name='User feature access',
                                        ref=reference, version=saved.version))
            session.flush()
            result = user_management.public_user(user, session)
        audit.append(actor, 'user.features.changed')
    return result
