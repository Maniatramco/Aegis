"""A single LangGraph handoff owns onboarding/upload/extraction proposals.

The routing model chooses the operation once. This agent uses validated tools,
then the confirmed durable workflow performs API business logic, without a
second model call to rediscover that same operation. No mutation is proposed
from filenames, saved conversation text, or retrieved document instructions.
"""
from fastapi import HTTPException

OPERATIONS={'onboard_dataset','upload','extract','upload_extract'}

class OnboardExtractAgent:
    name='onboard_extract'

    def __init__(self,tools):self.tools=tools

    def prepare(self,decision):
        operation=decision['operation']
        if operation not in OPERATIONS:raise HTTPException(422,'Unsupported Onboard & Extract operation.')
        if operation=='onboard_dataset':
            name=decision.get('dataset_name','').strip()
            if name and name.casefold() not in self.tools.body.text.casefold():name=''
            tool='prepare_dataset_onboarding'
            arguments={'name':name,'description':decision.get('dataset_description','')}
        else:
            attached={name.casefold() for name in self.tools.body.attached_filenames}
            names=[name for name in decision.get('document_names',[]) if name.casefold() not in attached]
            if names:
                available=self.tools.documents();selected=[]
                for name in names:
                    matches=[doc for doc in available if doc.name.casefold()==name.casefold()]
                    if len(matches)!=1:
                        raise HTTPException(422,'Select the specific document in the file filter: '+name+'. '+('Several files have this name.' if matches else 'No file with that exact name is available in this scope.'))
                    selected.append(matches[0].id)
                self.tools.body.document_ids=list(dict.fromkeys(selected))
            tool='prepare_workflow'
            arguments={'operation':operation,'document_ids':self.tools.body.document_ids,
                'template_id':self.tools.body.template_id}
        result=self.tools.run(tool,arguments)
        if self.tools.proposal:
            self.tools.proposal['agent']=self.name
            answer=('Review the new dataset, model mappings, documents and prompt, then confirm Onboard & Extract.'
                if operation=='onboard_dataset' else 'Review the dataset, documents and prompt below, then confirm processing.')
            answer+=' Processing begins after confirmation; completion includes saved results and verified knowledge updates.'
        else:answer=result.get('message','The existing processing state is preserved.')
        return {'tool':tool,'arguments':arguments,'result':result,'answer':answer}

def publish_call(record,data,call):
    """A processing call completes only after its saved artifacts are indexed."""
    from .. import core, dataset_access
    from . import agent_onboarding
    ids=[];documents=list(call.get('uploaded_document_ids',[]))
    entries=call.get('result',{}).get('extractions',[])
    ids.extend(entry['extraction_id'] for entry in entries if not entry.get('superseded'))
    if call.get('result',{}).get('extraction_id'):ids.append(call['result']['extraction_id'])
    ids=list(dict.fromkeys(ids))
    for id in ids:
        extraction=dataset_access.get_record(id,record.owner,'extraction')
        documents.extend(core.store.json(extraction.ref).get('document_ids',[]))
    if not documents:documents=data.get('document_ids',[])
    bundle={'dataset_id':data['dataset_id'],'template_id':data.get('template_id',''),
        'document_ids':list(dict.fromkeys(documents)),'extraction_ids':ids}
    agent_onboarding.publish_knowledge(bundle,record.owner)
    call['vector_publication']=bundle['vector_publication']
    call.pop('publication_error',None);call.pop('error',None)
