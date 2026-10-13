"""Real-model route-only checks; no workflow submissions or confirmations."""
import json,time
from app import core,dataset_access,dataset_models,agent_model,ollama_provider
owner='administrator';actor=dataset_access.request_actor.set(owner)
try:
    dataset=dataset_access.get_record('36fe2487-eaa3-5132-a9bd-12fdb48bcc52',owner,'knowledge_base')
    snapshot=dataset_models.execution_snapshot(dataset,'chat');metrics=[];original=ollama_provider.request
    def request(path,payload,timeout):
        data=original(path,payload,timeout)
        metrics.append({'input_tokens':data.get('prompt_eval_count'),'output_tokens':data.get('eval_count'),
            'load_seconds':round(data.get('load_duration',0)/1e9,3),'runtime_context':payload['options']['num_ctx']})
        return data
    ollama_provider.request=request;cases=[]
    for question,source,operation in [
        ('Re-extract the selected document with the updated prompt.','action','reextract'),
        ('Re-extract maya-rao-sample-resume.pdf using the selected saved template.','action','reextract'),
        ('Run extraction again on the saved resume with this prompt.','action','reextract'),
        ('How do I re-extract documents in Aegis?','application','none')]:
        start=time.perf_counter()
        with core.execution_context(snapshot):
            frame=agent_model.classify([{'role':'system','content':json.dumps({'selected_dataset':True,
                'selected_document_count':1,'chat_history_supplied':False})},{'role':'user','content':question}])
        cases.append({'question':question,'passed':frame['source']==source and frame['operation']==operation,
            'seconds':round(time.perf_counter()-start,3),'decision':frame,'model_metrics':metrics[-1]})
    print(json.dumps({'model':snapshot['settings']['model'],'passed':sum(c['passed'] for c in cases),'total':len(cases),'cases':cases},indent=2))
finally:
    ollama_provider.request=original;dataset_access.request_actor.reset(actor)
