"""Inventory and erase only explicitly selected application entity prefixes.

Pinned destinations are authoritative, including objects written before a
storage switch. Never enumerate or delete unrelated bucket objects.
"""
import json
from . import core, storage_config


def adapter(destination):
    if destination['storage_provider']=='oci':return core.oci_storage(destination)
    return storage_config.DirectoryStorage(destination.get('local_storage_path'))


def routes():
    root=core.local_store.path('storage-routes/marker').parent
    return [core.local_store.json('storage-routes/'+p.name) for p in root.glob('*.json')]


def inventory(prefixes,keys=()):
    pinned=routes();items={}
    for prefix in prefixes:
        if not prefix.endswith('/') or len(prefix.split('/'))!=3:raise ValueError('An entity directory is required')
        destinations=[storage_config.route(prefix+'marker')]
        destinations.extend(r['destination'] for r in pinned if r['key']==prefix.rstrip('/') or r['key'].startswith(prefix))
        unique={json.dumps(d,sort_keys=True):d for d in destinations}
        for destination in unique.values():
            for item in adapter(destination).list_prefix(prefix):
                if not item['key'].startswith(prefix):raise ValueError('Object outside selected entity')
                identity=(item['key'],json.dumps(destination,sort_keys=True))
                items[identity]=dict(item,destination=destination)
    for key in keys:
        destination=storage_config.route(key);meta=adapter(destination).stat(key)
        if meta:items[(key,json.dumps(destination,sort_keys=True))]=dict(meta,key=key,destination=destination)
    return list(items.values())


def erase(prefixes,keys=()):
    from .object_cache import CachedObjects,eligible
    items=inventory(prefixes,keys)
    checked=set()
    for item in items:
        destination=item['destination'];identity=json.dumps(destination,sort_keys=True)
        if destination['storage_provider']=='oci' and identity not in checked:
            adapter(destination).require_permanent_delete();checked.add(identity)
    for item in items:
        key=item['key'];destination=item['destination'];backend=adapter(destination)
        if destination['storage_provider']=='oci' and eligible(key):
            cached=CachedObjects(backend,destination);cached.delete(key)
            core.local_store.delete(cached.ref(key)[0])
        else:backend.delete(key)
    if inventory(prefixes,keys):raise RuntimeError('Document objects remain after cleanup')
    for route in routes():
        key=route['key']
        if key in keys or any(key==p.rstrip('/') or key.startswith(p) for p in prefixes):
            # Also remove caches for objects already absent in authoritative storage.
            if route['destination']['storage_provider']=='oci' and eligible(key):
                core.local_store.delete(CachedObjects(lambda:None,route['destination']).ref(key)[0])
            core.local_store.delete(storage_config.route_ref(key))
    return len(items)


def original(record,adapters=None):
    destination=storage_config.route(record.ref)
    try:
        if adapters is None:backend=adapter(destination)
        else:
            identity=json.dumps(destination,sort_keys=True)
            if identity not in adapters:adapters[identity]=adapter(destination)
            backend=adapters[identity]
        state='present' if backend.stat(record.ref) else 'missing'
    except Exception:state='unavailable'
    return {'provider':destination['storage_provider'],'bucket':destination.get('oci_storage_bucket','') if destination['storage_provider']=='oci' else '',
        'key':((destination.get('oci_storage_prefix','').strip('/')+'/') if destination['storage_provider']=='oci' and destination.get('oci_storage_prefix') else '')+record.ref,
        'status':state}
