"""Finish the authorized fresh start by archiving legacy local graph state.

The new workspace lives in OCI; never copy or remove any cloud object.
"""
import hashlib
import shutil
from sqlalchemy import select
from app import core,workspace_reset as reset

ARCHIVE='9933bdb7-be9e-4dd9-af85-ba1d2b3bc153'
with core.document_lock('workspace-reset'):
    with core.Session() as session:
        assert not session.scalar(select(core.Job.id).where(core.Job.status.in_(['queued','running'])).limit(1))
        active_ids={r.id for r in session.scalars(select(core.Record)) if r.kind in reset.KINDS}
        active_ids.update(j.id for j in session.scalars(select(core.Job)))
    manifest=core.local_store.json('workspace-archives/'+ARCHIVE+'/manifest.json')
    receipt=core.local_store.json('workspace-archives/'+ARCHIVE+'/receipt.json')
    added=0
    for folder in ('agent-state','executions'):
        source=reset.safe(core.DATA/folder)
        if not source.exists():continue
        for path in source.rglob('*'):
            assert not path.is_symlink()
            assert not any(part in active_ids or part.removesuffix('.json') in active_ids for part in path.parts)
            if not path.is_file():continue
            relative=str(path.relative_to(core.DATA))
            target=reset.safe(core.DATA/'workspace-archives'/ARCHIVE/'files'/relative)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,target)
            checksum=hashlib.sha256(path.read_bytes()).hexdigest()
            assert hashlib.sha256(target.read_bytes()).hexdigest()==checksum
            manifest['files'][relative]=checksum;added+=1
        if folder not in manifest['folders']:manifest['folders'].append(folder)
    core.local_store.put_json('workspace-archives/'+ARCHIVE+'/manifest.json',manifest)
    receipt['file_count']=len(manifest['files'])
    core.local_store.put_json('workspace-archives/'+ARCHIVE+'/receipt.json',receipt)
    for folder in ('agent-state','executions'):
        source=reset.safe(core.DATA/folder)
        if source.exists():shutil.rmtree(source)
    print({'additional_legacy_files_archived':added,'archive_files':receipt['file_count']})
