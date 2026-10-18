"""Content-free, append-only access journal on the shared control volume.

SHA-256 chaining detects accidental edits and broken tails. This is not an
external immutable/WORM log: a storage administrator can replace the journal.
"""
import hashlib
import json
import os
import time
import uuid
from contextvars import ContextVar
from fastapi import HTTPException
from . import core

request_context = ContextVar('governance_request', default=None)
JOURNAL = 'governance-audit/events.jsonl'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def touch(dataset_id):
    context = request_context.get()
    if context is not None and dataset_id:
        context['dataset_ids'].add(dataset_id)


def _events():
    path = core.local_store.path(JOURNAL)
    if not path.exists():
        return []
    output, previous = [], '0' * 64
    with path.open('rb') as stream:
        for sequence, line in enumerate(stream, 1):
            item = json.loads(line)
            digest = item.pop('hash')
            if item['sequence'] != sequence or item['previous_hash'] != previous or hashlib.sha256(canonical(item)).hexdigest() != digest:
                raise ValueError('Audit journal integrity check failed')
            item['hash'] = digest
            output.append(item)
            previous = digest
    return output


def append(actor, action, **options):
    try:
        return _append(actor, action, **options)
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'Durable access auditing is unavailable. The operation could not be verified.') from None


def _append(actor, action, *, dataset_ids=(), status='completed', request_id=None, http_status=None):
    # No query strings, headers, bodies, filenames or extracted values enter it.
    with core.document_lock('governance-audit'):
        path = core.local_store.path(JOURNAL)
        path.parent.mkdir(parents=True, exist_ok=True)
        previous, sequence = '0' * 64, 0
        if path.exists() and path.stat().st_size:
            with path.open('rb') as stream:
                stream.seek(max(0, path.stat().st_size - 65536))
                tail = stream.read()
            if not tail.endswith(b'\n'):
                raise HTTPException(503, 'Access audit journal has an incomplete tail. An operator must repair it before continuing.')
            last = json.loads(tail.splitlines()[-1])
            digest = last.pop('hash')
            if hashlib.sha256(canonical(last)).hexdigest() != digest:
                raise HTTPException(503, 'Access audit journal integrity check failed.')
            previous, sequence = digest, last['sequence']
        item = {'sequence': sequence + 1, 'previous_hash': previous, 'at': time.time(),
                'actor_id': actor, 'action': action, 'status': status,
                'request_id': request_id or str(uuid.uuid4()), 'http_status': http_status,
                'dataset_ids': sorted(set(dataset_ids))}
        item['hash'] = hashlib.sha256(canonical(item)).hexdigest()
        with path.open('ab') as stream:
            os.chmod(path, 0o600)
            stream.write(canonical(item) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        return item


def read(actor, dataset_ids, offset=0, limit=50):
    from . import governance
    governance.require_manager(actor)
    selected = governance.scope(actor, dataset_ids, allow_retired=True)
    try:
        with core.document_lock('governance-audit'):
            events = _events()
    except (ValueError, KeyError, OSError):
        raise HTTPException(503, 'Access audit journal could not be verified. No verified audit was returned.') from None
    # Global events (login/settings) are visible only with an explicitly empty
    # dataset filter, to administrators. Never return a mixed-scope event that
    # includes a dataset this administrator no longer has access to.
    from . import dataset_access
    with core.Session() as session:
        authorized = dataset_access.dataset_ids(actor, session)
    matched = [event for event in reversed(events)
               if (not selected or set(event['dataset_ids']) <= authorized) and
               (not selected or selected.intersection(event['dataset_ids']))]
    return {'items': matched[offset:offset + limit], 'total_items': len(matched),
            'offset': offset, 'has_more': offset + limit < len(matched),
            'integrity_verified': True, 'verified_events': len(events),
            'storage': 'shared_control_volume', 'external_immutable_log': False}
