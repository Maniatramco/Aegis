"""LangGraph checkpoints in routed external storage, never SQL payload columns.

The caller authorizes the conversation and serializes turns before constructing
this saver. Only JSON state is supported: no pickle or arbitrary object loading.
Shared-volume locks match the current single-Pod Docker/OKE deployment contract.
"""
import json
from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple, WRITES_IDX_MAP
from .. import core


class ExternalCheckpointSaver(BaseCheckpointSaver):
    def __init__(self, thread_id):
        super().__init__()
        if not all(c.isalnum() or c == '-' for c in thread_id):
            raise ValueError('Invalid conversation identifier')
        self.thread_id = thread_id
        self.ref = f'agent-state/{thread_id}/checkpoints.json'

    def _read(self):
        try: return core.store.json(self.ref)
        except FileNotFoundError: return {'checkpoints': {}, 'writes': {}}

    def _config(self, id):
        return {'configurable': {'thread_id': self.thread_id, 'checkpoint_ns': '', 'checkpoint_id': id}}

    def _validate(self, config):
        if config['configurable']['thread_id'] != self.thread_id or config['configurable'].get('checkpoint_ns', ''):
            raise ValueError('Checkpoint scope mismatch')

    def get_tuple(self, config):
        self._validate(config)
        data = self._read()
        id = config['configurable'].get('checkpoint_id') or max(data['checkpoints'], default='')
        entry = data['checkpoints'].get(id)
        if not entry: return None
        return CheckpointTuple(config=self._config(id), checkpoint=entry['checkpoint'],
            metadata=entry['metadata'], parent_config=self._config(entry['parent']) if entry['parent'] else None,
            pending_writes=[(w['task'], w['channel'], w['value']) for w in data['writes'].get(id, {}).values()])

    def list(self, config, *, filter=None, before=None, limit=None):
        if config: self._validate(config)
        data = self._read(); count = 0
        before_id = before['configurable'].get('checkpoint_id') if before else None
        for id in sorted(data['checkpoints'], reverse=True):
            if before_id and id >= before_id: continue
            if filter and any(data['checkpoints'][id]['metadata'].get(k) != v for k,v in filter.items()): continue
            if limit is not None and count >= limit: break
            yield self.get_tuple(self._config(id)); count += 1

    def put(self, config, checkpoint, metadata, new_versions):
        self._validate(config)
        with core.document_lock('checkpoint-' + self.thread_id):
            data = self._read(); id = checkpoint['id']
            data['checkpoints'][id] = {'checkpoint': checkpoint, 'metadata': metadata,
                'parent': config['configurable'].get('checkpoint_id')}
            # Keep bounded graph history; the complete business conversation is
            # a separate external artifact, so pruning does not erase messages.
            for old in sorted(data['checkpoints'])[:-32]:
                del data['checkpoints'][old]; data['writes'].pop(old, None)
            core.store.put_json(self.ref, data)
        return self._config(id)

    def put_writes(self, config, writes, task_id, task_path=''):
        self._validate(config)
        with core.document_lock('checkpoint-' + self.thread_id):
            data = self._read(); bucket = data['writes'].setdefault(config['configurable']['checkpoint_id'], {})
            for index, (channel, value) in enumerate(writes):
                index = WRITES_IDX_MAP.get(channel, index); key = f'{task_id}:{index}'
                if index >= 0 and key in bucket: continue
                # Exception messages may contain provider bodies. Store only a
                # generic type for failed graph nodes, never a response body.
                if isinstance(value, BaseException): value = {'error_type': type(value).__name__}
                bucket[key] = {'task': task_id, 'channel': channel, 'value': value}
            core.store.put_json(self.ref, data)

    def delete_thread(self, thread_id):
        if thread_id != self.thread_id: raise ValueError('Checkpoint scope mismatch')
        with core.document_lock('checkpoint-' + thread_id): core.store.delete(self.ref)
