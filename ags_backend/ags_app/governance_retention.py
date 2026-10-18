"""Policy-driven retirement and scoped active-store purge with preservation fences.

Object-store version history, provider backups and external exports are outside
this application's purge scope. A retained workspace archive blocks purging.
"""
import json
import time
from contextlib import ExitStack
from pathlib import Path
from fastapi import Depends, HTTPException
from sqlalchemy import select
from . import core, governance, governance_controls as controls, governance_audit as audit
from . import dataset_lifecycle, storage_config


def related(dataset_id):
    with core.Session() as session:
        rows = list(session.scalars(select(core.Record)))
    result = [row for row in rows if row.id == dataset_id or row.parent_id == dataset_id]
    selected = {row.id for row in result}
    # Old conversations can retain scope only in their payload. Mixed histories
    # must be resolved by an operator: never erase another dataset's history.
    for row in rows:
        if row.id in selected or row.kind not in ('conversation', 'dataset_chat', 'agent_plan', 'agent_onboarding'):
            continue
        try: data = core.store.json(row.ref)
        except FileNotFoundError: continue
        ids = set(data.get('dataset_ids') or [data.get('dataset_id') or data.get('kb_id') or ''])
        if dataset_id in ids:
            if ids - {dataset_id, ''}:
                raise HTTPException(409, 'A mixed-dataset conversation retains this dataset. Resolve its retention before purging.')
            result.append(row)
    return result


def plan(actor, dataset_id):
    governance.require_manager(actor)
    with core.Session() as session:
        dataset = session.get(core.Record, dataset_id)
        if not dataset or dataset.kind != 'knowledge_base': raise HTTPException(404, 'Dataset not found.')
        # Administrators can inspect a retired dataset, but no role bypass is
        # permitted and a restored dataset must still satisfy the current policy.
        spec = controls.active(dataset_id)
        rows = related(dataset_id)
        last_activity = max(float(row.updated_at or row.created_at or 0) for row in rows
                            if not row.kind.startswith('governance') and row.id != dataset_id) if any(row.id != dataset_id and not row.kind.startswith('governance') for row in rows) else float(dataset.created_at)
        period = spec['controls']['retention_days']
        due_at = last_activity + period * 86400 if period else None
        receipt = controls._read(dataset_lifecycle.receipt_ref(dataset_id), None) if dataset.status == 'deleted' else None
        purge_at = receipt['deleted_at'] + spec['controls']['purge_grace_days'] * 86400 if receipt else None
        return {'dataset_id': dataset_id, 'action': spec['controls']['retention_action'], 'controls_version': spec['version'],
                'last_activity': last_activity, 'due_at': due_at, 'expired': bool(due_at and due_at <= time.time()),
                'retired': dataset.status == 'deleted', 'purge_at': purge_at,
                'purge_due': bool(purge_at and purge_at <= time.time()), 'legal_hold': controls.hold(dataset_id),
                'record_count': len(rows), 'scope': 'active application files, saved revisions, current objects and indexes',
                'excluded': ['object-store noncurrent versions', 'provider backups', 'external exports'],
                'automatic_deletion_enabled': spec['version'] > 0 and spec['controls']['retention_action'] != 'none'}


def _prefixes(rows):
    output = set()
    for row in rows:
        if row.kind.startswith('governance'): continue
        if '/' in row.ref:
            parts = row.ref.split('/')
            if len(parts) < 3 or parts[1] != row.id:
                raise HTTPException(409, 'A record has a nonstandard storage reference; automatic purge is blocked.')
            output.add('/'.join(parts[:2]) + '/')
        if row.kind == 'document': output.add('documents/' + row.id + '/')
        if row.kind in ('agent_plan', 'agent_onboarding', 'conversation'): output.add('agent-state/' + row.id + '/')
    return output


def _objects(prefix):
    # Include the pinned destination and any older explicit markers for this
    # entity. This preserves storage switches and never lists an entire bucket.
    destinations = [storage_config.route(prefix + 'marker')]
    for path in (core.DATA / 'storage-routes').glob('*.json'):
        entry = json.loads(path.read_text(encoding='utf-8'))
        if entry['key'].rstrip('/') == prefix.rstrip('/') or entry['key'].startswith(prefix):
            destinations.append(entry['destination'])
    destinations.append({'storage_provider': 'local', 'local_storage_path': str(core.DATA)})
    seen = set()
    output = []
    for destination in destinations:
        identity = json.dumps({key: destination.get(key) for key in storage_config.FIELDS}, sort_keys=True)
        if identity in seen: continue
        seen.add(identity)
        if destination['storage_provider'] == 'oci':
            backend = core.oci_storage(destination)
            start = None
            object_prefix = backend.object_key(prefix.rstrip('/')) + '/'
            while True:
                response = backend.client.list_objects(backend.namespace, backend.bucket, prefix=object_prefix,
                                                       **({'start': start} if start else {})).data
                for item in response.objects:
                    if not item.name.startswith(object_prefix): raise ValueError('Object listing escaped the selected prefix')
                    key = prefix + item.name[len(object_prefix):]
                    output.append((key, backend, destination))
                start = response.next_start_with
                if not start: break
        else:
            backend = storage_config.DirectoryStorage(destination.get('local_storage_path'))
            folder = backend.path(prefix.rstrip('/'))
            for path in folder.rglob('*') if folder.exists() else []:
                resolved = path.resolve()
                if folder.resolve() not in resolved.parents: raise ValueError('Purge target escaped its entity folder')
                if path.is_file(): output.append((path.relative_to(backend.root).as_posix(), backend, destination))
    return output


def _purge_knowledge(dataset_id, record_ids):
    from . import knowledge
    for path in (core.DATA / 'knowledge').glob('*/manifest.json'):
        name = path.parent.name
        with core.document_lock('unified-knowledge-' + name):
            manifest = core.local_store.json(path.relative_to(core.DATA).as_posix())
            points = manifest.get('points', {})
            ids = [id for id, value in points.items() if value.get('dataset_id') == dataset_id
                   or str(value.get('entity_id', '')).split(':', 1)[0] in record_ids]
            if not ids: continue
            from . import providers
            q = providers.client() if core.settings()['search_provider'] in ('qdrant', 'oracle') else None
            if q:
                from qdrant_client.models import PointIdsList
                q.delete(name, PointIdsList(points=ids), wait=True)
            for id in ids:
                points.pop(id, None)
                manifest.get('vectors', {}).pop(id, None)
            for key in record_ids: manifest.get('entities', {}).pop(key, None)
            core.local_store.put_json(path.relative_to(core.DATA).as_posix(), manifest)


def apply(actor, dataset_id):
    governance.require_manager(actor)
    with core.document_lock('workspace-reset'), controls.deletion_guard(dataset_id), core.document_lock('dataset-' + dataset_id):
        receipt_ref = controls.root(dataset_id) + '/purge-receipt.json'
        previous_receipt = controls._read(receipt_ref, None)
        with core.Session() as session:
            exists = session.get(core.Record, dataset_id)
        if not exists and previous_receipt:
            if previous_receipt['status'] == 'files_purged_catalog_pending':
                if any(item[0] != dataset_lifecycle.receipt_ref(dataset_id) for prefix in previous_receipt['prefixes'] for item in _objects(prefix)):
                    raise HTTPException(503, 'Purge could not be verified. Active files remain; operator inspection is required.')
                previous_receipt.update(status='active_storage_purged', verified_at=time.time())
                core.store.put_json(receipt_ref, previous_receipt)
                audit.append(actor, 'governance.retention.purged', dataset_ids=[dataset_id])
            return previous_receipt
        current = plan(actor, dataset_id)
        if not current['automatic_deletion_enabled'] or not current['expired']:
            return dict(current, status='not_due')
        with core.Session() as session:
            dataset = session.get(core.Record, dataset_id)
            dataset_lifecycle.ensure_idle(dataset, session)
        if not current['retired']:
            audit.append(actor, 'governance.retention.retiring', dataset_ids=[dataset_id])
            # Recoverably remove the dataset from every user's authorized scope.
            core.store.put_json(dataset_lifecycle.receipt_ref(dataset_id), {'id': dataset_id, 'name': dataset.name,
                'previous_status': dataset.status, 'deleted_at': time.time(), 'deleted_by': actor,
                'retention_controls_version': current['controls_version']})
            with core.Session.begin() as session:
                row = session.get(core.Record, dataset_id)
                row.status = 'deleted'; row.updated_at = time.time()
            return dict(current, status='retired', recoverable=True)
        if current['action'] != 'purge' or not current['purge_due']:
            return dict(current, status='retired_waiting')
        for path in (core.DATA / 'workspace-archives').glob('*/manifest.json'):
            manifest = json.loads(path.read_text(encoding='utf-8'))
            if any(row['id'] == dataset_id for row in manifest.get('records', [])):
                raise HTTPException(409, 'A retained workspace archive contains this dataset. Its backup retention must be resolved before purge.')
        rows = related(dataset_id)
        record_ids = {row.id for row in rows}
        # Gather and validate all prefixes before deleting any file. Retired
        # datasets cannot accept new processing; lock every retained entity too.
        with ExitStack() as locks:
            for id in sorted(record_ids - {dataset_id}): locks.enter_context(core.document_lock(id))
            with core.Session() as session:
                jobs = list(session.scalars(select(core.Job).where(core.Job.target_id.in_(record_ids))))
            prefixes = _prefixes(rows)
            protected_ref = dataset_lifecycle.receipt_ref(dataset_id)
            objects = [item for prefix in sorted(prefixes) for item in _objects(prefix) if item[0] != protected_ref]
            for job in jobs:
                objects.extend(_objects('jobs/' + job.id + '/'))
                objects.append(('jobs/' + job.id + '.json', core.store, None))
            audit.append(actor, 'governance.retention.purge_started', dataset_ids=[dataset_id])
            from . import providers
            for row in rows:
                if row.kind == 'document': providers.delete_vectors(row.id)
            _purge_knowledge(dataset_id, record_ids)
            from .object_cache import CachedObjects
            for key, backend, destination in objects:
                if destination and destination['storage_provider'] == 'oci':
                    CachedObjects(backend, destination).delete(key)
                else:
                    backend.delete(key)
            # Historical credential revisions can leave older cache identities.
            # This derived cache is rebuildable; clear it under its own locks so
            # no prior payload survives a successful canonical-file purge.
            with core.document_lock('oci-cache-prune'):
                for path in (core.DATA / 'object-cache').glob('*.json'):
                    with core.document_lock('oci-cache-' + path.stem):
                        core.local_store.delete(path.relative_to(core.DATA).as_posix())
            if any(item[0] != protected_ref for prefix in prefixes for item in _objects(prefix)):
                raise HTTPException(503, 'Purge was partially accepted. Some active files remain; the retired dataset is preserved for retry.')
            receipt = {'dataset_id': dataset_id, 'status': 'files_purged_catalog_pending', 'at': time.time(),
                       'records_deleted': sum(not row.kind.startswith('governance') for row in rows),
                       'objects_targeted': len(objects), 'prefixes': sorted(prefixes), 'excluded': current['excluded']}
            core.store.put_json(receipt_ref, receipt)
            with core.Session.begin() as session:
                # Delete children before the dataset; projection hooks remove
                # foreign-key dependents through the existing ORM contract.
                for job in jobs:
                    item = session.get(core.Job, job.id)
                    if item: session.delete(item)
                session.flush()
                from . import relational
                for model in (relational.DatasetModel, relational.UserDataset):
                    session.execute(model.__table__.delete().where(model.dataset_id == dataset_id))
                for row in sorted(rows, key=lambda row: row.kind == 'knowledge_base'):
                    if row.kind.startswith('governance'): continue
                    if row.kind == 'knowledge_base':
                        session.execute(relational.Dataset.__table__.delete().where(relational.Dataset.dataset_id == dataset_id))
                    item = session.get(core.Record, row.id)
                    if item: session.delete(item); session.flush()
            receipt.update(status='active_storage_purged', verified_at=time.time())
            core.store.put_json(receipt_ref, receipt)
            audit.append(actor, 'governance.retention.purged', dataset_ids=[dataset_id])
            return receipt


def install(app, auth):
    @app.get('/api/governance/datasets/{id}/retention')
    def preview_retention(id: str, actor=Depends(auth)):
        return plan(actor, id)

    @app.post('/api/governance/datasets/{id}/retention/run')
    def run_retention(id: str, actor=Depends(auth)):
        return apply(actor, id)
