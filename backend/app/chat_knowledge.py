"""Read-only published vector view. SQL is used for access/revision guards,
never answer facts. No canonical file hydration or query-time index writes.
"""
import copy,json
from sqlalchemy import select
from fastapi import HTTPException
from . import core,knowledge,providers,dataset_access as access,relational

MAX_POINTS=6000

class PublishedKnowledge:
    def __init__(self,actor,dataset_id='',document_ids=None):
        self.actor=actor;self.dataset_id=dataset_id;self.documents=set(document_ids or [])
        with core.Session() as session:
            datasets=access.dataset_ids(actor,session)
            if dataset_id and dataset_id not in datasets:raise HTTPException(404,'Dataset access removed.')
            models=set(session.scalars(select(relational.DatasetModel.model_id).where(relational.DatasetModel.dataset_id.in_(datasets),relational.DatasetModel.enabled==True)))
            records=list(session.scalars(select(core.Record).where(core.Record.kind.in_(knowledge.KINDS))))
            self.records={r.id:r for r in records if (r.kind not in ('agent_plan','agent_onboarding') or r.owner==actor and r.parent_id in datasets)
                and not (r.kind=='agent_plan' and r.status=='query')
                and access.allowed(r,actor,session,datasets,models)
                and (not dataset_id or r.kind=='model' or (r.id if r.kind=='knowledge_base' else r.parent_id) in ('',dataset_id))}
        if any(id not in self.records or self.records[id].kind!='document' or self.records[id].parent_id!=dataset_id for id in self.documents):
            raise HTTPException(400,'Selected document is outside the authorized dataset.')
        self.snapshot=knowledge.embedding_snapshot(actor,dataset_id)
        try:self.manifest=core.local_store.json(knowledge._manifest_ref(self.snapshot))
        except FileNotFoundError:raise HTTPException(409,'Knowledge is not published yet. Wait for indexing to finish, then retry.')

    def candidate_ids(self,source_types,root_ids=None):
        types=set(source_types)
        if types-knowledge.TYPES:raise HTTPException(422,'Unsupported knowledge type.')
        kind_types={'knowledge_base':{'dataset'},'document':{'document','document_chunk'},'extraction':{'extraction'},
            'template':{'prompt'},'model':{'model'},'agent_plan':{'workflow'},'agent_onboarding':{'workflow'}}
        required=[r for r in self.records.values() if (root_ids is None or r.id in root_ids) and kind_types[r.kind]&types and
            (not self.documents or r.kind!='document' or r.id in self.documents)]
        for record in required:
            entry=self.manifest['entities'].get(record.id)
            if not entry or (entry.get('revision_stamp') or entry['stamp'])!=knowledge.entity_stamp(record):
                raise HTTPException(409,'Knowledge is updating for this scope. Retry after publication; I will not answer from an older revision.')
        permitted=[]
        for id,payload in self.manifest['points'].items():
            if payload['source_type'] not in types:continue
            root=payload['entity_id'].split(':',1)[0]
            if root_ids is not None and root not in root_ids:continue
            if payload['source_type']!='application' and root not in self.records:continue
            if payload.get('private') and payload.get('owner_id')!=self.actor:continue
            if self.dataset_id and payload.get('dataset_id') not in ('',self.dataset_id):continue
            if self.documents and payload['source_type'] in ('document','document_chunk','extraction'):
                ids=set(payload.get('document_ids',[]))
                if payload.get('merged_document_id') not in self.documents and (not ids or not ids<=self.documents):continue
            permitted.append(id)
        if len(permitted)>MAX_POINTS:raise HTTPException(413,'The knowledge scope is too large. Choose documents or specific fields.')
        return permitted

    def catalog(self,source_types):return self.fetch(self.candidate_ids(source_types))

    def fetch(self,permitted):
        points=[]
        with core.execution_context(self.snapshot):
            if self.snapshot['settings']['search_provider'] in ('oracle','qdrant'):
                from qdrant_client.models import Filter,HasIdCondition
                client=providers.client();offset=None
                if not permitted:return []
                while True:
                    page,offset=client.scroll(self.snapshot['knowledge_collection'],scroll_filter=Filter(must=[HasIdCondition(has_id=permitted)]),
                        offset=offset,limit=256,with_payload=True,with_vectors=False)
                    points.extend({'id':str(p.id),'payload':p.payload} for p in page)
                    if offset is None:break
            else:points=[{'id':id,'payload':copy.deepcopy(self.manifest['points'][id])} for id in permitted]
        if len(points)!=len(permitted):raise HTTPException(409,'Knowledge publication is incomplete. Retry when indexing finishes.')
        for p in points:
            expected=self.manifest['points'][p['id']]
            if p['payload'].get('content_digest')!=expected['content_digest'] or knowledge.digest({k:v for k,v in p['payload'].items() if k!='content_digest'})!=expected['content_digest']:
                raise HTTPException(409,'Knowledge verification failed. Republish the affected dataset before answering.')
        return points

    def search(self,query,source_types,limit=5):
        permitted=self.candidate_ids(source_types)
        if not permitted:return []
        with core.execution_context(self.snapshot):
            vector=providers.embed([query],query=True)[0]
            if self.snapshot['settings']['search_provider'] in ('oracle','qdrant'):
                from qdrant_client.models import Filter,HasIdCondition
                hits=providers.client().query_points(self.snapshot['knowledge_collection'],query=vector,
                    query_filter=Filter(must=[HasIdCondition(has_id=permitted)]),limit=limit).points
                selected={str(p.id) for p in hits}
            else:
                vectors=self.manifest.get('vectors',{})
                selected=set(sorted(permitted,key=lambda id:sum(a*b for a,b in zip(vector,vectors.get(id,[]))),reverse=True)[:limit])
        entities={self.manifest['points'][id]['entity_id'] for id in selected}
        return self.fetch([id for id in permitted if self.manifest['points'][id]['entity_id'] in entities])

def assemble(points):
    groups={}
    for point in points:groups.setdefault(point['payload']['entity_id'],[]).append(point)
    result=[]
    for entity,group in groups.items():
        group.sort(key=lambda p:p['payload']['part']);p=group[0]['payload']
        if len(group)!=p.get('part_count') or [x['payload']['part'] for x in group]!=list(range(len(group))):
            raise HTTPException(409,'A published knowledge record is incomplete. Retry after indexing finishes.')
        text=''.join(x['payload']['text'] for x in group)
        try:value=json.loads(text)
        except ValueError:value=text
        result.append(dict(p,knowledge_id=group[0]['id'],text=text,value=value))
    return result
