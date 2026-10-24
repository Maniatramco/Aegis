"""Dataset grants govern shared content; conversations remain personal."""
from contextvars import ContextVar
from fastapi import HTTPException
from sqlalchemy import select
from . import core, relational

request_actor = ContextVar('aegis_request_actor', default=None)
SHARED = {'document', 'template', 'extraction'}
PRIVATE = {'conversation', 'agent_plan', 'agent_onboarding', 'temporary_session', 'temporary_document'}


def require_admin(actor):
    # Trusted internal CLI calls and synthetic dependency overrides have no
    # authenticated HTTP actor. Every normal API request sets it in auth().
    if request_actor.get() is not None and not core.is_administrator(actor):
        raise HTTPException(403, 'Only the administrator can manage dataset and model configuration.')


def dataset_ids(actor, session):
    live = select(core.Record.id).where(core.Record.kind == 'knowledge_base', core.Record.status != 'deleted')
    if core.is_administrator(actor,session):
        return set(session.scalars(live))
    if not session.get(core.User, actor) and request_actor.get() is None:
        return set(session.scalars(live.where(core.Record.owner == actor)))
    return set(session.scalars(select(relational.UserDataset.dataset_id).where(relational.UserDataset.user_id == actor,relational.UserDataset.enabled == True,relational.UserDataset.dataset_id.in_(live))))


def allowed(record, actor, session, datasets=None, models=None):
    if not record or record.status=='deleting':
        return False
    datasets = dataset_ids(actor, session) if datasets is None else datasets
    if record.kind == 'knowledge_base':
        return record.id in datasets
    if record.kind in SHARED and record.parent_id:
        return record.parent_id in datasets
    if record.kind in PRIVATE:
        dataset_id=record.parent_id
        if record.owner!=actor:return False
        if not dataset_id and record.kind in {'conversation','agent_plan','agent_onboarding'}:
            try:
                data=core.store.json(record.ref);dataset_id=data.get('dataset_id') or data.get('kb_id')
            except FileNotFoundError:pass
        return not dataset_id or dataset_id in datasets
    if record.kind == 'model':
        if core.is_administrator(actor,session) or record.owner == actor:
            return True
        models = set(session.scalars(select(relational.DatasetModel.model_id).where(
            relational.DatasetModel.dataset_id.in_(datasets), relational.DatasetModel.enabled == True))) if models is None else models
        return record.id in models
    return record.owner == actor or (core.is_administrator(actor,session) and record.kind == 'config_profile')


def get_record(id, actor, kind=None):
    with core.Session() as session:
        record = session.get(core.Record, id)
        if not record or (kind and record.kind != kind) or not allowed(record, actor, session):
            raise HTTPException(404, 'Not found or dataset access removed.')
        return record


def rows(actor, kind):
    with core.Session() as session:
        datasets = dataset_ids(actor, session)
        models = set(session.scalars(select(relational.DatasetModel.model_id).where(
            relational.DatasetModel.dataset_id.in_(datasets), relational.DatasetModel.enabled == True))) if kind == 'model' else set()
        return [row for row in session.scalars(select(core.Record).where(core.Record.kind == kind).order_by(core.Record.created_at.desc()))
                if allowed(row, actor, session, datasets, models)]


def job_allowed(job, actor, session):
    if not job:
        return False
    target = session.get(core.Record, job.target_id)
    return allowed(target, actor, session) if target else job.owner == actor


def jobs(actor):
    with core.Session() as session:
        return [job for job in session.scalars(select(core.Job).order_by(core.Job.created_at.desc()))
                if job_allowed(job, actor, session)]
