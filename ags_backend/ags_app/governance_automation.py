"""Shared-volume scheduled governance work; no new cloud scheduler or model calls."""
import asyncio
import time
from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from . import core, governance, governance_controls as controls, governance_audit as audit


def state_ref(dataset_id):
    return controls.root(dataset_id) + '/automation.json'


def run_dataset(actor, dataset_id, force=False):
    governance.require_manager(actor)
    policy = controls.active(dataset_id)
    if not policy['version']:
        raise HTTPException(409, 'Approve an operational policy before scheduling governance work.')
    governance.require_manager(policy['proposed_by'])
    governance.require_manager(policy['approved_by'])
    spec = policy['controls']
    with core.document_lock('governance-automation-' + governance.policy_id(dataset_id)):
        state = controls._read(state_ref(dataset_id), {'dataset_id': dataset_id, 'tasks': {}})
        tasks = state['tasks']
        now = time.time()
        with core.Session() as session:
            dataset = session.get(core.Record, dataset_id)
            if not dataset or dataset.kind != 'knowledge_base': raise HTTPException(404, 'Dataset not found.')
        pending = [('quality', spec['auto_quality'] and dataset.status != 'deleted', spec['quality_interval_minutes']),
                   ('sync', spec['auto_sync'] and dataset.status != 'deleted', spec['sync_interval_minutes']),
                   ('retention', spec['retention_action'] != 'none', 60)]
        for name, enabled, interval in pending:
            previous = tasks.get(name, {})
            if not enabled or (not force and previous.get('attempted_at', 0) + interval * 60 > now):
                continue
            # Save the attempt before work. A process restart waits for the
            # configured interval rather than flooding OCI or repeating deletes.
            tasks[name] = {'status': 'running', 'attempted_at': now}
            core.store.put_json(state_ref(dataset_id), state)
            try:
                governance.require_manager(actor)
                if controls.active(dataset_id)['version'] != policy['version']:
                    raise HTTPException(409, 'Policy changed while automation was running.')
                if name == 'quality':
                    from .governance_quality import run
                    result = run(actor, dataset_id)
                elif name == 'sync':
                    from .governance_oci import publish_selected
                    result = publish_selected(actor, [dataset_id])
                else:
                    from .governance_retention import apply
                    result = apply(actor, dataset_id)
                tasks[name].update(status=result.get('status', 'completed'), completed_at=time.time())
            except Exception as error:
                tasks[name].update(status='blocked' if isinstance(error, HTTPException) and error.status_code in (403, 404, 409) else 'failed',
                                   completed_at=time.time(), error_code=getattr(error, 'status_code', 503),
                                   message=error.detail if isinstance(error, HTTPException) and error.status_code in (403, 404, 409) else 'Governance task failed. Inspect the service and retry; no successful stage was assumed.')
            core.store.put_json(state_ref(dataset_id), state)
        audit.append(actor, 'governance.automation.checked', dataset_ids=[dataset_id])
        return state


def tick():
    from .workspace_reset import paused
    if paused(): return
    with core.Session() as session:
        datasets = list(session.scalars(select(core.Record).where(core.Record.kind == 'knowledge_base')))
    for dataset in datasets:
        try:
            policy = controls.active(dataset.id)
            if not policy['version']: continue
            actor = policy['approved_by']
            # Both signatories must remain administrators. Removal/demotion
            # suspends automated operation until a new policy is approved.
            governance.require_manager(actor)
            governance.require_manager(policy['proposed_by'])
            run_dataset(actor, dataset.id)
        except Exception:
            # Keep other datasets running and expose a truthful suspension.
            try:
                core.store.put_json(state_ref(dataset.id), {'dataset_id': dataset.id, 'status': 'suspended',
                    'at': time.time(), 'tasks': {}, 'message': 'Policy, signatory access or saved governance state could not be verified.'})
            except Exception:
                pass  # The health endpoint below reports unreadable durable state.


async def loop():
    while True:
        await asyncio.sleep(60)
        await asyncio.to_thread(tick)


def status(actor, dataset_ids):
    governance.require_manager(actor)
    selected = governance.scope(actor, dataset_ids)
    return {'scheduler': 'application_api_shared_volume', 'poll_seconds': 60,
            'items': [controls._read(state_ref(id), {'dataset_id': id, 'status': 'not_run', 'tasks': {}}) for id in sorted(selected)]}


def install(app, auth):
    @app.get('/api/governance/automation')
    def automation_status(dataset_id: list[str] = Query(default=[]), actor=Depends(auth)):
        return status(actor, dataset_id)

    @app.post('/api/governance/datasets/{id}/automation/run')
    def run_now(id: str, actor=Depends(auth)):
        governance.scope(actor, [id])
        return run_dataset(actor, id, force=True)
