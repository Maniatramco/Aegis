"""Review-list reruns reuse the Agent's durable reindex -> extraction chain."""
import hashlib
import json
import time
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .. import core, dataset_models as routing
from . import agent_workspace as workspace


class RerunInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_version: int = Field(ge=1)
    template_id: str
    display_name: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=160)
    allow_external: bool = False


def install(app, auth, main):
    @app.post('/api/extractions/{id}/rerun')
    def rerun(id: str, body: RerunInput, owner=Depends(auth)):
        source=routing.owned(id,owner,'extraction')
        key=hashlib.sha256(json.dumps([owner,body.idempotency_key]).encode()).hexdigest()
        signature={'source_id':id,**body.model_dump()}
        with core.document_lock('extraction-rerun-'+key), core.document_lock('dataset-'+source.parent_id):
            # Return an accepted chain after a dropped HTTP reply, without
            # duplicating either indexing jobs or the eventual extraction.
            for record in routing.rows(owner,'agent_plan'):
                saved=core.store.json(record.ref)
                if saved.get('rerun_key')==key:
                    if saved.get('rerun_input')!=signature:
                        raise HTTPException(409,'Idempotency key was already used for different re-extraction inputs.')
                    with core.document_lock('agent-'+record.id):
                        return workspace.plan_public(record,main)
            source=routing.owned(id,owner,'extraction')
            if source.version!=body.source_version:
                raise HTTPException(409,'The previous extraction changed. Reload before re-extracting.')
            saved=core.store.json(source.ref)
            dataset,docs=routing.documents_scope(owner,source.parent_id,saved['document_ids'])
            template=routing.owned(body.template_id,owner,'template')
            if template.parent_id and template.parent_id!=dataset.id:
                raise HTTPException(400,'Choose a prompt template belonging to the selected dataset.')
            snapshot=routing.execution_snapshot(dataset,'extraction')
            main.external_check(body.allow_external,cfg=snapshot['settings'])
            if any(doc.status!='ready' for doc in docs):
                raise HTTPException(409,'Wait for source document processing to finish before re-extracting.')
            if any(not routing.index_matches(doc,snapshot) for doc in docs):
                main.external_check(body.allow_external,True,snapshot['embedding_execution']['settings'])
            data={'request':'Re-extract '+source.name,'explanation':'Rebuild outdated indexes, then create a separate extraction.',
                  'dataset_id':dataset.id,'document_ids':[doc.id for doc in docs],'template_id':template.id,
                  'extraction_mode':'merge','merge_strategy':'records' if saved.get('merge_records') else 'single',
                  'display_name':body.display_name,'created_at':time.time(),'rerun_key':key,'rerun_input':signature,
                  'calls':[{'tool':'reextract','title':'Re-extract fields','status':'pending'}]}
            record=routing.create('agent_plan',owner,'Re-extract '+source.name[:100],data,parent=dataset.id,status='workflow')
            try:
                with core.document_lock('agent-'+record.id):
                    return workspace.submit_extractions(record,data,data['calls'][0],workspace.ExecuteInput(
                        confirmed=True,allow_external=body.allow_external,display_name=body.display_name),owner,main)
            except HTTPException as exc:
                # Keep accepted job IDs and a visible failure if a later
                # submission fails. Never report a rolled-back workflow.
                data['auto_continue']=False
                call=next((call for call in data['calls'] if call['status']!='completed'),data['calls'][-1])
                call['error']=str(exc.detail)
                if call['status']=='pending':call['status']='failed'
                workspace.save_plan(record,data)
                return {'id':record.id,**data}
