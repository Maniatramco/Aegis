#!/usr/bin/env python3
"""Cold, operator-led storage copy. Never removes source or copies secrets.

Run using backend dependencies with api/worker/web stopped and the same database,
local /data mount, OCI identity and settings as the application. See docs.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

repository = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repository / 'backend' if (repository / 'backend').exists() else repository))
from app.oci_adapters import OCIStorageAdapter, _key, _safe_call

CONTENT_ROOTS = {'documents', 'knowledge_base', 'conversation', 'template', 'extraction', 'jobs', 'vectors'}
LOCAL_ONLY_ROOTS = {'configuration', 'secrets', 'diagnostics'}


def content_references(references):
    """Filter known server-local refs; reject unknown roots rather than lose data."""
    result=[]
    for ref in references:
        if not ref:continue
        _key(ref)
        root=ref.split('/')[0]
        if root in LOCAL_ONLY_ROOTS:continue
        if root not in CONTENT_ROOTS:raise ValueError('Unknown database reference root; update migration rules before proceeding')
        result.append(ref)
    return result


def digest(data): return hashlib.sha256(data).hexdigest()

def metadata_digest(value): return digest(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def validate_key(key):
    _key(key)
    if key.split('/')[0] not in CONTENT_ROOTS: raise ValueError('Manifest contains a non-content key')
    return key


def destination_confirmation(descriptor):
    if descriptor['provider']=='local': return 'local-content-volume'
    return '/'.join([descriptor['region'], descriptor['namespace'], descriptor['bucket'], descriptor['prefix']])


def descriptor_from_settings(cfg):
    provider=cfg.get('storage_provider','local')
    if provider=='local':return {'provider':'local'}
    if provider!='oci':raise ValueError('Unsupported source storage provider')
    return {'provider':'oci', 'namespace':cfg.get('oci_storage_namespace') or os.getenv('OCI_NAMESPACE',''),
        'bucket':cfg.get('oci_storage_bucket') or os.getenv('OCI_BUCKET',''),
        'prefix':cfg.get('oci_storage_prefix',os.getenv('OCI_OBJECT_PREFIX','aegis')),
        'region':cfg.get('oci_storage_region') or os.getenv('OCI_REGION',''),
        'auth_mode':cfg.get('oci_storage_auth_mode') or os.getenv('OCI_AUTH_MODE','config_file'),
        'profile':cfg.get('oci_storage_profile') or os.getenv('OCI_PROFILE','DEFAULT')}


def adapter(descriptor, local):
    if descriptor['provider']=='local':return local
    if descriptor['provider']!='oci':raise ValueError('Unsupported destination')
    return OCIStorageAdapter(namespace=descriptor['namespace'],bucket=descriptor['bucket'],prefix=descriptor['prefix'],region=descriptor['region'],auth_mode=descriptor['auth_mode'],profile=descriptor['profile'])


def source_keys(source, descriptor, local_root):
    if descriptor['provider']=='local':
        keys=[]
        for name in sorted(CONTENT_ROOTS):
            folder=local_root/name
            if folder.is_symlink():raise ValueError('Symlink in content tree')
            if not folder.exists():continue
            for path in sorted(folder.rglob('*')):
                if path.is_symlink():raise ValueError('Symlink in content tree')
                if path.is_file():
                    key=path.relative_to(local_root).as_posix()
                    if key.endswith('.tmp'):raise ValueError('Unfinished content write found; inspect before migrating')
                    keys.append(validate_key(key))
        return sorted(keys)
    keys=[];prefix=descriptor['prefix']+'/' if descriptor['prefix'] else '';start=None
    while True:
        kwargs={'prefix':prefix,'fields':'name','limit':1000}
        if start:kwargs['start']=start
        response=_safe_call(source.client.list_objects,source.namespace,source.bucket,**kwargs)
        for obj in response.data.objects:
            if not obj.name.startswith(prefix):raise ValueError('Object outside selected prefix')
            key=obj.name[len(prefix):]
            if key.split('/')[0] in CONTENT_ROOTS:keys.append(validate_key(key))
        next_start=response.data.next_start_with
        if not next_start:break
        if next_start==start:raise ValueError('Object listing did not advance')
        start=next_start
    return sorted(set(keys))


def write_manifest(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.migration-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as out:
            json.dump(value,out,indent=2);out.flush();os.fsync(out.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def validate_manifest(plan):
    if plan.get('format')!='aegis-storage-migration-v1':raise ValueError('Unsupported migration manifest')
    seen=set()
    for entry in plan['objects']:
        key=validate_key(entry['key'])
        if key in seen:raise ValueError('Duplicate manifest key')
        seen.add(key)
        if not isinstance(entry['size'],int) or entry['size']<0:raise ValueError('Invalid manifest size')
        if len(entry['sha256'])!=64 or any(c not in '0123456789abcdef' for c in entry['sha256']):raise ValueError('Invalid manifest checksum')
    return plan


def create_plan(source, source_descriptor, destination, local_root, cfg, required_refs):
    keys=source_keys(source,source_descriptor,local_root)
    missing=set(required_refs)-set(keys)
    if missing:raise ValueError('Source storage is missing database-referenced content; repair before migration')
    if source_descriptor==destination:raise ValueError('Source and destination are the same')
    entries=[]
    for key in keys:
        raw=source.get(key);entries.append({'key':key,'size':len(raw),'sha256':digest(raw)})
    return {'format':'aegis-storage-migration-v1','created_at':time.time(),'phase':'planned','source':source_descriptor,'destination':destination,'settings_sha256':metadata_digest(cfg),'objects':entries,'object_count':len(entries),'total_bytes':sum(e['size'] for e in entries)}


def check_source(plan,source,local_root,cfg,required_refs):
    validate_manifest(plan)
    if metadata_digest(cfg)!=plan['settings_sha256']:raise ValueError('Settings changed after planning; create a new plan')
    if source_keys(source,plan['source'],local_root)!=sorted(e['key'] for e in plan['objects']):raise ValueError('Source inventory changed; create a new plan')
    if set(required_refs)-{e['key'] for e in plan['objects']}:raise ValueError('Database references changed; create a new plan')
    for entry in plan['objects']:
        raw=source.get(entry['key'])
        if len(raw)!=entry['size'] or digest(raw)!=entry['sha256']:raise ValueError('Source content changed after planning')


def copy_and_verify(plan,source,target):
    validate_manifest(plan)
    for entry in plan['objects']:
        key=entry['key'];raw=source.get(key)
        if len(raw)!=entry['size'] or digest(raw)!=entry['sha256']:raise ValueError('Source content changed during migration')
        try:existing=target.get(key)
        except FileNotFoundError:existing=None
        if existing is not None and digest(existing)!=entry['sha256']:raise ValueError('Destination contains conflicting content; use an empty prefix/volume')
        if existing is None:target.put(key,raw)
        result=target.get(key)
        if len(result)!=entry['size'] or digest(result)!=entry['sha256']:raise ValueError('Destination checksum verification failed')
    plan['phase']='copied_verified';plan['verified_at']=time.time()


def verify_destination(plan,target):
    for entry in plan['objects']:
        raw=target.get(entry['key'])
        if len(raw)!=entry['size'] or digest(raw)!=entry['sha256']:raise ValueError('Destination changed or incomplete')


def activate_settings(plan,cfg,local):
    if plan['phase']!='copied_verified':raise ValueError('Copy and verify must finish before activation')
    result=dict(cfg);target=plan['destination'];result['storage_provider']=target['provider']
    if target['provider']=='oci':
        for key in ('namespace','bucket','prefix','region','auth_mode','profile'):result['oci_storage_'+key]=target[key]
    local.put_json('configuration/settings.json',result)
    return result


@contextmanager
def migration_lock(root):
    import fcntl
    path=root/'.storage-migration.lock'
    with path.open('a') as handle:
        os.chmod(path,0o600)
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Another migration process is running')
        yield


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=['plan','copy','activate'])
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--writers-stopped',action='store_true',help='Required operator assertion: all API, web and workers are stopped')
    parser.add_argument('--to',choices=['local','oci'])
    for name in ('namespace','bucket','prefix','region','auth-mode','profile'):parser.add_argument('--dest-'+name)
    parser.add_argument('--confirm-destination',help='Exact region/namespace/bucket/prefix, or local-content-volume')
    args=parser.parse_args()
    if not args.writers_stopped:parser.error('Stop all writers first; --writers-stopped is required')
    from app.core import DATA, local_store, settings, Session, Record, Job
    from sqlalchemy import select
    try:
        with migration_lock(DATA):
            cfg=settings();source_desc=descriptor_from_settings(cfg);source=adapter(source_desc,local_store)
            with Session() as session:
                refs=content_references(session.scalars(select(Record.ref)))
                refs += ['jobs/'+j+'.json' for j in session.scalars(select(Job.id))]
            if args.phase=='plan':
                if Path(args.manifest).exists():raise ValueError('Manifest already exists; choose a new path')
                if not args.to:raise ValueError('--to is required for planning')
                destination={'provider':args.to}
                if args.to=='oci':
                    for name in ('namespace','bucket','prefix','region'):
                        value=getattr(args,'dest_'+name)
                        if value is None or (name!='prefix' and not value):raise ValueError('Explicit destination namespace, bucket, prefix and region required')
                        destination[name]=value
                    destination['auth_mode']=args.dest_auth_mode or os.getenv('OCI_AUTH_MODE','config_file')
                    destination['profile']=args.dest_profile or os.getenv('OCI_PROFILE','DEFAULT')
                plan=create_plan(source,source_desc,destination,DATA,cfg,refs)
                write_manifest(args.manifest,plan)
                print(json.dumps({'phase':'planned','objects':plan['object_count'],'bytes':plan['total_bytes'],'confirmation':destination_confirmation(destination)}))
                return
            plan=validate_manifest(json.loads(Path(args.manifest).read_text()))
            if args.confirm_destination!=destination_confirmation(plan['destination']):raise ValueError('Exact destination confirmation required; inspect manifest before proceeding')
            if source_desc!=plan['source']:raise ValueError('Active source differs from the planned source')
            check_source(plan,source,DATA,cfg,refs);target=adapter(plan['destination'],local_store)
            if plan['destination']['provider']=='local':source_keys(target,plan['destination'],DATA)
            if args.phase=='copy':
                copy_and_verify(plan,source,target);write_manifest(args.manifest,plan)
            else:
                verify_destination(plan,target)
                activate_settings(plan,cfg,local_store)
                plan['phase']='activated';plan['activated_at']=time.time();write_manifest(args.manifest,plan)
            print(json.dumps({'phase':plan['phase'],'objects':plan['object_count'],'source_deleted':False,'writers_restarted':False}))
    except Exception as exc:
        # Provider exceptions are sanitized; never dump auth config or content.
        from app.oci_adapters import OCIProviderUnavailable, OCIServiceFailure
        message=str(exc) if isinstance(exc,(ValueError,OCIProviderUnavailable,OCIServiceFailure,FileNotFoundError)) else 'Migration failed; inspect protected operator diagnostics'
        print(json.dumps({'ok':False,'error':message,'writers_restarted':False}),file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__':main()
