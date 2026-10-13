"""Active registration identity and reversible, operator-run consolidation."""
import argparse
import copy
import json
import time
from sqlalchemy import select
from . import core, dataset_models as routing, dataset_access as access


def identity(cfg, model, capabilities):
    embedding=capabilities==['embedding']
    keys=routing.EMBED_KEYS if embedding else routing.MODEL_KEYS
    values={k:cfg.get(k) for k in keys}
    # The requested provider identifier overrides the profile's generic name.
    values['embedding_model' if embedding else 'model']=model.removesuffix(':latest')
    if not embedding:values['oci_model']=values['model']
    return json.dumps({'capabilities':sorted(capabilities),'settings':values},sort_keys=True)


def equivalent(owner,cfg,model,capabilities,exclude=None):
    expected=identity(cfg,model,capabilities)
    for record in routing.rows(owner,'model'):
        if record.id==exclude:continue
        data=routing.model_data(record)
        if data.get('archived') or not data.get('enabled',True) or sorted(data['capabilities'])!=sorted(capabilities):continue
        profile=routing.owned(data['connection_profile_id'],record.owner,'config_profile')
        snapshot=routing.profile_snapshot(profile,data.get('connection_profile_version'))
        # Reusing a remote registration with a different credential identity
        # is unsafe. Deduplication here is for credential-free local models.
        if snapshot['secret_refs'].get('connection') or snapshot['secret_refs'].get('openai') or snapshot['secret_refs'].get('oci'):continue
        if identity(snapshot['settings'],data['provider_model'],data['capabilities'])==expected:return record
    return None


def consolidate(canonical,apply=False):
    """No records/files/results are deleted. Old versions remain pinned.

    Only models using the same local underlying weights as each canonical
    role are eligible. Dataset configuration receives new immutable versions;
    existing ready indexes are queued again after an embedding change.
    """
    with core.Session() as db:
        admin=db.scalar(select(core.User).where(core.User.role=='administrator'))
        if not admin:raise ValueError('Consolidation requires a persisted administrator account.')
        all_models=db.scalars(select(core.Record).where(core.Record.kind=='model')).all()
        datasets=db.scalars(select(core.Record).where(core.Record.kind=='knowledge_base')).all()
        docs=db.scalars(select(core.Record).where(core.Record.kind=='document')).all()
        active_jobs=db.scalars(select(core.Job).where(core.Job.status.in_(['queued','running']))).all()
    if active_jobs:raise ValueError('Wait for active jobs to finish before consolidating model mappings.')
    token=access.request_actor.set(admin.id)
    try:
        targets={role:routing.owned(id,admin.id,'model') for role,id in canonical.items()}
        if set(targets)!={'embedding','chat','extraction'}:raise ValueError('Supply all three canonical roles.')
        for role,record in targets.items():
            data=routing.model_data(record);public=routing.model_public(record)
            if role not in data['capabilities'] or not data.get('enabled',True) or data.get('archived') or public['provider']!='ollama':
                raise ValueError('Canonical roles must be enabled local Ollama models.')
        aliases={}
        for record in all_models:
            data=routing.model_data(record)
            if record.id in canonical.values() or data.get('archived'):continue
            public=routing.model_public(record)
            if public['provider']!='ollama':raise ValueError('Review remote models separately; they cannot be consolidated as local aliases.')
            replacements={role:canonical[role] for role in data['capabilities'] if role in targets and
                data['provider_model'].removesuffix(':latest')==routing.model_data(targets[role])['provider_model'].removesuffix(':latest')}
            if set(replacements)!=set(data['capabilities']):raise ValueError('A model uses different weights. Review it separately.')
            aliases[record.id]={'record':record,'data':data,'replacements':replacements}
        changes=[]
        keys={'embedding':'embedding_model_id','chat':'default_chat_model_id','extraction':'default_extraction_model_id'}
        for dataset in datasets:
            before=routing.dataset_config(dataset)
            if not any(m['model_id'] in aliases for m in before.get('mappings',[])):continue
            after=copy.deepcopy(before);mapped={}
            for mapping in before['mappings']:
                ids=aliases[mapping['model_id']]['replacements'].values() if mapping['model_id'] in aliases else [mapping['model_id']]
                for id in ids:mapped[id]=mapped.get(id,False) or mapping['enabled']
            after['mappings']=[{'model_id':id,'enabled':enabled} for id,enabled in mapped.items()]
            for role,key in keys.items():
                if before.get(key) in aliases:after[key]=aliases[before[key]]['replacements'][role]
            changes.append({'record':dataset,'before':before,'after':after,
                'reindex':[d.id for d in docs if d.parent_id==dataset.id and d.status=='ready'] if before['embedding_model_id']!=after['embedding_model_id'] else []})
        report={'created_at':time.time(),'canonical':canonical,'archived_count':len(aliases),'datasets_changed':len(changes),
            'reindex_count':sum(len(c['reindex']) for c in changes),'applied':apply,
            'aliases':{id:{'name':a['record'].name,'old_ref':a['record'].ref,'replacements':a['replacements'],'data':a['data']} for id,a in aliases.items()},
            'datasets':[{'id':c['record'].id,'name':c['record'].name,'old_ref':c['record'].ref,'before':c['before'],'reindex':c['reindex']} for c in changes], 'jobs':[]}
        if apply:
            ref='diagnostics/model-consolidation/'+str(int(time.time()))+'.json'
            # Save a recoverable snapshot BEFORE any changes.
            core.local_store.put_json(ref,report)
            from . import main
            for change in changes:
                data=change['after'];body=routing.MappingInput(**{k:data[k] for k in ('mappings',*keys.values())},acknowledge_reindex=True)
                with core.document_lock('dataset-'+change['record'].id):routing.save_mappings(change['record'],body)
                for id in change['reindex']:
                    job=main.reindex(id,main.Consent(),owner=admin.id);report['jobs'].append(job['id'])
                core.local_store.put_json(ref,report)
            for alias in aliases.values():
                routing.write_version(alias['record'],alias['data']|{'archived':True,'enabled':False,
                    'replacement_models':alias['replacements'],'archived_at':time.time(),'archive_reason':'Consolidated into canonical role registrations'})
            report['report_ref']=ref;core.local_store.put_json(ref,report)
        return report
    finally:access.request_actor.reset(token)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for role in ('embedding','chat','extraction'):parser.add_argument('--'+role,required=True)
    parser.add_argument('--apply',action='store_true');args=parser.parse_args();core.init()
    result=consolidate({role:getattr(args,role) for role in ('embedding','chat','extraction')},args.apply)
    print(json.dumps({k:result.get(k) for k in ('archived_count','datasets_changed','reindex_count','applied','report_ref','jobs')}))
