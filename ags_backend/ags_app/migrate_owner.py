"""Copy a stopped legacy Aegis schema into a new owner, without deleting source.

Run in the API image with the existing shared storage and password secret. The
destination must be empty. Credential URLs, row contents and hashes are not logged.
"""
import argparse
import time
from types import SimpleNamespace
from sqlalchemy import create_engine, MetaData, Table, select, func
from . import core, relational

def migrate(source_user='AEGIS'):
    if core.engine.dialect.name!='oracle' or core.URL.username==source_user:
        raise ValueError('Use Oracle with a different empty destination owner.')
    source=create_engine(core.URL.set(username=source_user),pool_pre_ping=True,hide_parameters=True)
    legacy={name:Table(name,MetaData(),autoload_with=source) for name in ('users','sessions','records','jobs')}
    with source.connect() as c:
        active=c.scalar(select(func.count()).select_from(legacy['jobs']).where(legacy['jobs'].c.status.in_(['queued','running'])))
        if active:raise ValueError('Finish or cancel active jobs and stop application writes before migration.')
        rows={name:[dict(r) for r in c.execute(select(table)).mappings()] for name,table in legacy.items()}
    core.Base.metadata.create_all(core.engine)
    with core.engine.begin() as c:
        for table in core.Base.metadata.sorted_tables:
            if c.scalar(select(func.count()).select_from(table)):
                raise ValueError('Destination is not empty. No data was copied; do not overwrite it.')
        models={'users':core.User,'sessions':core.Login,'records':core.Record,'jobs':core.Job}
        normalized={}
        stamp=time.time()
        def values_for(name,row):
            table=models[name].__table__
            values={k:v for k,v in row.items() if k in table.c}
            values.update(created_by=None,updated_by=None,created_via='legacy',updated_via='migration')
            values.setdefault('created_at',stamp);values.setdefault('updated_at',stamp)
            if name=='users':values.setdefault('role','administrator' if row['id']=='administrator' else 'user')
            return values
        for name in ('users','sessions','records'):
            normalized[name]=[values_for(name,r) for r in rows[name]]
            if normalized[name]:c.execute(models[name].__table__.insert(),normalized[name])
        rank={'model':0,'knowledge_base':1,'document':2,'template':3,'extraction':4}
        token=relational.source.set('migration')
        try:
            for values in sorted(normalized['records'],key=lambda r:rank.get(r['kind'],4)):
                record=SimpleNamespace(**values)
                relational.sync_item(c,record)
                if record.kind=='extraction':
                    for version in range(1,record.version+1):
                        ref=f'extraction/{record.id}/v{version}.json'
                        try:data=core.store.json(ref)
                        except FileNotFoundError:continue
                        if data.get('review_status')=='reviewed':
                            common={k:values[k] for k in ('created_by','updated_by','created_via','updated_via','created_at','updated_at')}
                            relational.add_review(c,record,data,ref,version,common)
        finally:relational.source.reset(token)
        for row in rows['jobs']:
            values=values_for('jobs',row)
            did=c.scalar(select(relational.Document.document_id).where(relational.Document.document_id==row['target_id']))
            eid=c.scalar(select(relational.Extraction.extract_id).where(relational.Extraction.extract_id==row['target_id']))
            values.update(document_id=did,extract_id=eid)
            c.execute(core.Job.__table__.insert().values(**values))
        # Compare every original column, including password hashes/session data,
        # in memory only. A mismatch rolls back all copied data.
        for name,model in models.items():
            copied={r['id']:dict(r) for r in c.execute(select(model.__table__)).mappings()}
            if len(copied)!=len(rows[name]):raise ValueError('Migration row count verification failed.')
            if any(any(copied[r['id']][k]!=v for k,v in r.items()) for r in rows[name]):
                raise ValueError('Migration value verification failed; target transaction rolled back.')
        report={t.name:c.scalar(select(func.count()).select_from(t)) for t in core.Base.metadata.sorted_tables}
    source.dispose()
    print('Migration committed; all original columns and IDs matched. Source retained unchanged.')
    print(report)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',default='AEGIS');args=parser.parse_args()
    migrate(args.source)
