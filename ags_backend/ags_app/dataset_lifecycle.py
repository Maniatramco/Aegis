"""Recoverable dataset deletion; originals, revisions and shared models stay intact."""
import time
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from . import core, dataset_access as access


class DeleteDataset(BaseModel):
    confirmation: str = Field(max_length=250)
    expected_version: int = Field(ge=1)


def receipt_ref(id):
    return 'knowledge_base/' + id + '/trash.json'


def deleted_dataset(id, session):
    row = session.get(core.Record, id)
    if not row or row.kind != 'knowledge_base' or row.status != 'deleted':
        raise HTTPException(404, 'Deleted dataset not found.')
    return row


def active_submission(call):
    if call.get('status') != 'running':
        return False
    # An interrupted HTTP upload cannot remain live indefinitely. No accepted
    # jobs or model work are discarded: both are checked separately below.
    started = call.get('started_at')
    expired_upload = (call.get('tool') == 'upload' and not call.get('job_ids')
        and isinstance(started, (int, float)) and 0 < started < time.time() - 86400)
    return not expired_upload


def ensure_idle(dataset, session):
    targets = select(core.Record.id).where((core.Record.parent_id == dataset.id) | (core.Record.id == dataset.id))
    if session.scalar(select(core.Job.id).where(core.Job.target_id.in_(targets), core.Job.status.in_(['queued', 'running', 'blocked'])).limit(1)):
        raise HTTPException(409, 'Finish or cancel this dataset’s processing jobs before deleting it.')
    for row in session.scalars(select(core.Record).where(core.Record.kind.in_(['agent_plan', 'agent_onboarding']), core.Record.parent_id.in_([dataset.id, '']))):
        try:
            data = core.store.json(row.ref)
        except FileNotFoundError:
            if row.parent_id == dataset.id:
                raise HTTPException(409, 'An Agent workflow cannot be checked. Restore its saved state before deleting this dataset.')
            continue
        if (row.parent_id or data.get('dataset_id') or data.get('kb_id')) != dataset.id:
            continue
        if (data.get('goal') or {}).get('status') in ('queued', 'running', 'retry_wait') or data.get('status') == 'running' or any(active_submission(call) for call in data.get('calls', [])):
            raise HTTPException(409, 'Finish or stop this dataset’s active Agent workflow before deleting it.')


def delete_dataset(id, body, actor):
    access.get_record(id, actor, 'knowledge_base')
    from .governance_controls import deletion_guard
    with deletion_guard(id):
        return _delete_dataset(id, body, actor)


def _delete_dataset(id, body, actor):
    access.require_admin(actor)
    with core.document_lock('dataset-' + id):
        row = access.get_record(id, actor, 'knowledge_base')
        if body.confirmation != row.name:
            raise HTTPException(400, 'Type the exact dataset name to confirm deletion.')
        if body.expected_version != row.version:
            raise HTTPException(409, 'Dataset changed. Refresh it before deleting.')
        with core.Session.begin() as session:
            current = session.get(core.Record, id)
            ensure_idle(current, session)
            core.store.put_json(receipt_ref(id), {'id': id, 'name': current.name, 'previous_status': current.status,
                'deleted_at': time.time(), 'deleted_by': actor})
            current.status = 'deleted'
            current.updated_at = time.time()
        return {'id': id, 'name': row.name, 'deleted': True, 'recoverable': True}


def trash(actor):
    access.require_admin(actor)
    with core.Session() as session:
        rows = session.scalars(select(core.Record).where(core.Record.kind == 'knowledge_base', core.Record.status == 'deleted').order_by(core.Record.updated_at.desc()))
        return [dict(core.store.json(receipt_ref(row.id)), version=row.version) for row in rows]


def restore_dataset(id, actor):
    access.require_admin(actor)
    with core.document_lock('dataset-' + id):
        with core.Session.begin() as session:
            row = deleted_dataset(id, session)
            receipt = core.store.json(receipt_ref(id))
            row.status = receipt['previous_status']
            row.updated_at = time.time()
        return {'id': id, 'name': row.name, 'restored': True}


def install(app, auth):
    @app.get('/api/dataset-trash')
    def list_deleted(actor=Depends(auth)):
        return trash(actor)

    @app.delete('/api/datasets/{id}')
    def remove(id: str, body: DeleteDataset, actor=Depends(auth)):
        return delete_dataset(id, body, actor)

    @app.post('/api/dataset-trash/{id}/restore')
    def restore(id: str, actor=Depends(auth)):
        return restore_dataset(id, actor)
