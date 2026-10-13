"""Real-model routing checks, read only; no workflow confirmation or writes."""
import time,json
from sqlalchemy import select
from ags_app import core,dataset_access,dataset_models,agent_model,agent_context,ollama_provider

with core.Session() as session:
    dataset=session.scalar(select(core.Record).where(core.Record.kind=='knowledge_base',core.Record.name=='Resume Agent Verification'))
assert dataset is not None
actor=dataset_access.request_actor.set(dataset.owner)
snapshot=dataset_models.execution_snapshot(dataset,'chat')
metrics=[];original=ollama_provider.request
def measured(path,payload,timeout):
    start=time.perf_counter();result=original(path,payload,timeout)
    metrics.append({'elapsed_seconds':round(time.perf_counter()-start,3),
        'input_tokens':result.get('prompt_eval_count'),'output_tokens':result.get('eval_count'),
        'load_seconds':round(result.get('load_duration',0)/1e9,3),
        'context_window':payload['options']['num_ctx']})
    return result
ollama_provider.request=measured
cases=[
    # The adapter normalizes every run_workflow source to action after
    # validating the raw application/onboarding branch of the model grammar.
    ('onboard_named','Create a new dataset named Candidate Profiles and onboard it with model mappings, documents, a prompt and extraction.','action','onboard_dataset'),
    ('extract_selected','Extract the selected documents with the selected prompt and save the results.','action','extract'),
    ('upload_extract','Upload and extract my attached resume using the selected prompt.','action','upload_extract'),
    ('reextract','Re-extract the selected document using the updated prompt.','action','reextract'),
    ('filenames','Can you list me the douccments name available for this dataset?','metadata','none'),
    ('count','How many documents are in this dataset?','metadata','none'),
    ('help','How do I onboard and extract documents in Aegis?','application','none'),
    ('saved_summary','Summarize the completed extraction results.','results','none')]
report={'model':snapshot['settings']['model'],'cases':[]}
try:
    for label,question,source,operation in cases:
        audits=[];start=time.perf_counter()
        context={'available_result_fields':['full_name','skills','total_experience_years'],
            'latest_workflow':{'status':'completed','calls':[{'tool':'extract','status':'completed'}]},
            'recent_dataset_onboarding':[],'chat_history_supplied':False}
        with core.execution_context(snapshot),agent_context.observe(audits.append):
            decision=agent_model.classify([{'role':'system','content':'Verified reference context: '+json.dumps(context)},
                {'role':'user','content':question}])
        passed=decision['source']==source and decision['operation']==operation
        if label=='onboard_named':passed=passed and decision.get('dataset_name')=='Candidate Profiles'
        if label=='count':passed=passed and decision.get('initial_reads')==['list_documents'] and decision.get('metadata_answer')=='document_count' and decision.get('answer_kind')=='count'
        report['cases'].append({'case':label,'expected_source':source,'expected_operation':operation,
            'decision':decision,'passed':passed,'seconds':round(time.perf_counter()-start,3),
            'model_metrics':metrics[-1],'context_audit':audits})
    report['passed']=sum(c['passed'] for c in report['cases']);report['total']=len(cases)
    print(json.dumps(report,indent=2))
finally:
    ollama_provider.request=original;dataset_access.request_actor.reset(actor)
