"""Bounded shared cache for application-owned OCI JSON objects.

The bucket remains authoritative. API and worker must share the same state
volume and every write must use RoutingStorage (the existing single-writer
deployment contract). Mark uncertain writes before transmission so a crash or
failed request cannot leave an old cached value trusted. Originals and Parquet
always bypass this cache, including persistence checksum verification.
"""
import base64
import hashlib
import json
import os
import time
from . import core

ROOT = 'object-cache/'
MAX_ENTRY_BYTES = 4 * 1024 * 1024
MAX_CACHE_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 2048
PREFIXES = ('jobs/', 'agent_plan/', 'agent_onboarding/', 'agent-state/',
            'conversation/', 'knowledge_base/', 'template/', 'extraction/',
            'documents/', 'temporary_session/', 'temporary_document/')


def eligible(key):
    return key.startswith(PREFIXES) and key.endswith('.json')


class CachedObjects:
    def __init__(self, backend, destination):
        self._backend = backend
        identity = {k: destination.get(k, '') for k in (
            'oci_storage_namespace', 'oci_storage_bucket', 'oci_storage_region',
            'oci_storage_prefix', 'oci_storage_auth_mode', 'oci_storage_profile',
            'oci_storage_config_file', 'oci_storage_key_file')}
        # Credential rotation/profile edits invalidate the scope without
        # persisting credential contents in cache names or metadata.
        for field in ('oci_storage_config_file', 'oci_storage_key_file'):
            try: identity[field + '_revision'] = os.stat(identity[field]).st_mtime_ns
            except (OSError, TypeError): pass
        self.scope = json.dumps(identity, sort_keys=True)

    @property
    def backend(self):
        # A hit must avoid OCI client/key initialization as well as network IO.
        if callable(self._backend): self._backend = self._backend()
        return self._backend

    def ref(self, key):
        from .oci_adapters import _key
        _key(key)
        digest = hashlib.sha256((self.scope + '\n' + key).encode()).hexdigest()
        return ROOT + digest + '.json', 'oci-cache-' + digest

    def read(self, ref):
        try:
            value = core.local_store.json(ref)
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, ValueError, UnicodeError): return {}

    def payload(self, entry):
        if entry.get('state') != 'valid': return None
        try:
            value = base64.b64decode(entry['payload'], validate=True)
            if hashlib.sha256(value).hexdigest() == entry['sha256']: return value
        except (KeyError, ValueError): pass
        return None

    def remember(self, ref, value):
        if len(value) > MAX_ENTRY_BYTES:
            core.local_store.put_json(ref, {'state': 'uncached'})
            return
        core.local_store.put_json(ref, {'state': 'valid',
            'payload': base64.b64encode(value).decode(),
            'sha256': hashlib.sha256(value).hexdigest()})

    def get(self, key):
        ref, lock = self.ref(key); changed = False
        with core.document_lock(lock):
            entry = self.read(ref); value = self.payload(entry)
            if value is not None: return value
            if entry.get('state') == 'missing' and entry.get('until', 0) > time.time():
                raise FileNotFoundError('Stored object unavailable')
            try: value = self.backend.get(key)
            except FileNotFoundError:
                core.local_store.put_json(ref, {'state': 'missing', 'until': time.time() + 60})
                raise
            uncertain = entry.get('state') == 'pending' and (
                entry.get('delete') or entry.get('expected_sha256') != hashlib.sha256(value).hexdigest())
            # A timed-out PUT can still complete later. Until its intended
            # bytes are observed, returning current canonical bytes must not
            # promote them into a permanently trusted cache entry.
            if not uncertain:self.remember(ref, value); changed = True
        if changed: self.prune()
        return value

    def put(self, key, value):
        if not isinstance(value,bytes):raise TypeError('Storage data must be bytes')
        ref, lock = self.ref(key)
        with core.document_lock(lock):
            if self.payload(self.read(ref)) == value: return
            core.local_store.put_json(ref, {'state': 'pending','expected_sha256':hashlib.sha256(value).hexdigest()})
            self.backend.put(key, value)
            self.remember(ref, value)
        self.prune()

    def delete(self, key):
        ref, lock = self.ref(key)
        with core.document_lock(lock):
            core.local_store.put_json(ref, {'state': 'pending','delete':True})
            self.backend.delete(key)
            core.local_store.put_json(ref, {'state': 'missing', 'until': time.time() + 60})

    def prune(self):
        with core.document_lock('oci-cache-prune'):
            root = core.local_store.path(ROOT + 'marker').parent
            files = []
            for path in root.glob('*.json'):
                try: files.append((path.stat().st_mtime_ns, path, path.stat().st_size))
                except FileNotFoundError: pass
            total = sum(size for _, _, size in files); count = len(files)
            for _, path, size in sorted(files):
                if count <= MAX_ENTRIES and total <= MAX_CACHE_BYTES: break
                with core.document_lock('oci-cache-' + path.stem):
                    # Never discard the invalidation marker of an uncertain
                    # canonical write; a subsequent read must resolve it.
                    if self.read(ROOT + path.name).get('state') == 'pending': continue
                    path.unlink(missing_ok=True)
                total -= size; count -= 1
