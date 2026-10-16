"""Read-only dataset-chat knowledge; existing Aegis Agent retrieval is unchanged."""
from fastapi import HTTPException
from contextlib import nullcontext
from .. import core, dataset_access as access, runtime_config
from .chat_knowledge import PublishedKnowledge, assemble as published_assemble

def assemble(points):
    records=published_assemble(points)
    locations={point['payload']['entity_id']:point for point in points}
    for record in records:
        point=locations[record['entity_id']]
        record.update({key:point[key] for key in ('_knowledge_collection','_knowledge_dataset_id') if key in point})
    return records

def validate_workspace_scope(actor,dataset_ids,document_ids=None):
    """Validate the explicit read-only scope before resolving any provider."""
    selected=set(dataset_ids)
    if not selected:raise HTTPException(422,'Choose dataset knowledge before asking a question.')
    with core.Session() as session:
        allowed=access.dataset_ids(actor,session)
        if not selected<=allowed:raise HTTPException(404,'Dataset knowledge is no longer accessible.')
        if document_ids is not None:
            if not document_ids:raise HTTPException(422,'Include at least one available file.')
            for id in document_ids:
                record=session.get(core.Record,id)
                if not record or record.kind!='document' or record.parent_id not in selected or not access.allowed(record,actor,session,allowed):
                    raise HTTPException(404,'Selected dataset knowledge is no longer accessible.')


class WorkspaceKnowledge:
    """Federated read-only retrieval across authorized embedding spaces."""
    def __init__(self,actor,dataset_ids,document_ids=None,summary=False):
        validate_workspace_scope(actor,dataset_ids,document_ids)
        self.dataset_id='';self.dataset_ids=sorted(set(dataset_ids));self.documents=set(document_ids or []);self.summary=summary
        self.views=[]
        with core.Session() as session:
            parents={id:session.get(core.Record,id).parent_id for id in self.documents}
        for id in self.dataset_ids:
            scoped=[doc for doc,parent in parents.items() if parent==id] if document_ids is not None else None
            if document_ids is not None and not scoped:continue
            self.views.append(PublishedKnowledge(actor,id,scoped))
        if not self.views:raise HTTPException(422,'Include available dataset knowledge before asking a question.')
        self.snapshot=self.views[0].snapshot
        self.snapshots=[view.snapshot for view in self.views]
        self.records={id:r for view in self.views for id,r in view.records.items()}
        self.manifest={'updated_at':min(view.manifest.get('updated_at',0) for view in self.views),
            'points':{id:p for view in self.views for id,p in view.manifest['points'].items()}}

    def search(self,query,source_types,limit=5,root_ids=None,require_rerank=False,progress=None):
        from .. import reranker
        points=[];seen=set();representatives=[];diagnostics=[]
        for view in self.views:
            found=view.search(query,set(source_types)-{'application','document'} if self.summary else source_types,limit=limit,root_ids=root_ids,require_rerank=True,progress=progress)
            if self.summary:
                catalog=view.catalog(['dataset'],{view.dataset_id});known={point['id'] for point in found}
                found.extend(point for point in catalog if point['id'] not in known)
            diagnostics.append({'dataset_id':view.dataset_id,**view.search_diagnostics})
            records=assemble(found)
            if records:
                own=[record for record in records if record.get('dataset_id')==view.dataset_id]
                content=next((record for record in own if record['source_type'] in ('document_chunk','extraction')),None)
                if content:representatives.append(content['entity_id'])
                representatives.extend(record['entity_id'] for record in own if record['source_type']=='dataset')
            for point in found:
                key=(point['payload']['entity_id'],point['payload']['part'])
                if key in seen:continue
                seen.add(key);points.append(dict(point,_knowledge_collection=view.snapshot['knowledge_collection'],_knowledge_dataset_id=view.dataset_id))
        candidates=assemble(points)
        cap=runtime_config.get('AEGIS_CHAT_SEARCH_CANDIDATES_MAX')
        if len(candidates)>cap:raise HTTPException(413,'Choose fewer datasets for this workspace question.')
        with (progress.step('Reranking workspace evidence') if progress else nullcontext()):
            ranked=reranker.rank(query,candidates,len(candidates)) if candidates else []
        # A workspace overview retains retrieved evidence from each dataset;
        # ordinary questions use the best ranked evidence across the scope.
        chosen=set(representatives) if self.summary else set()
        for record in ranked:
            if len(chosen)>=max(limit,len(representatives) if self.summary else limit):break
            chosen.add(record['entity_id'])
        self.search_diagnostics={'mode':'hybrid','reranker_enabled':True,'datasets':diagnostics,
            'returned_entities':len(chosen),'workspace_summary':self.summary}
        order={record['entity_id']:i for i,record in enumerate(ranked)}
        return sorted([point for point in points if point['payload']['entity_id'] in chosen],key=lambda point:(order[point['payload']['entity_id']],point['payload']['part']))

    def catalog(self,source_types,root_ids=None):
        points=[];seen=set()
        for view in self.views:
            for point in view.catalog(source_types,root_ids):
                key=(point['payload']['entity_id'],point['payload']['part'])
                if key in seen:continue
                seen.add(key);points.append(dict(point,_knowledge_collection=view.snapshot['knowledge_collection'],_knowledge_dataset_id=view.dataset_id))
        return points
