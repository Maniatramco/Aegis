"""Public operation timings. Never expose model reasoning or tool arguments."""
import time
from contextlib import contextmanager

TOOL_LABELS={'find_extractions':'Checking saved extractions','read_extraction_results':'Reading saved fields',
    'search_knowledge':'Searching unified Aegis knowledge',
    'list_datasets':'Reading dataset catalog','list_prompts':'Reading prompt catalog',
    'get_dataset_onboarding_status':'Checking dataset onboarding', 'get_dataset_status':'Checking dataset status','get_model_configuration':'Reading model mappings',
    'get_application_info':'Reading Aegis guidance',
    'search_documents':'Retrieving document evidence','get_workflow_status':'Checking workflow status',
    'read_prompt':'Reading saved prompt','list_documents':'Checking documents',
    'prepare_dataset_onboarding':'Preparing dataset onboarding', 'prepare_workflow':'Preparing workflow','prepare_recovery':'Preparing recovery'}

class AnswerProgress:
    def __init__(self,callback=None,initial=None):
        self.callback=callback;self.started_at=(initial or {}).get('started_at',time.time()*1000);self.steps=[dict(step) for step in (initial or {}).get('steps',[])];self.status='running'

    def snapshot(self):
        return {'started_at':self.started_at,'status':self.status,'steps':[dict(s) for s in self.steps]}

    def emit(self):
        if self.callback:self.callback(self.snapshot())

    @contextmanager
    def step(self,label):
        entry={'id':str(len(self.steps)+1),'label':label,'status':'running','started_at':time.time()*1000}
        self.steps.append(entry);started=time.monotonic();self.emit()
        try:yield entry
        except BaseException:
            entry['status']='failed';raise
        finally:
            entry['duration_ms']=round((time.monotonic()-started)*1000)
            if entry['status']=='running':entry['status']='completed'
            self.emit()

    def complete(self):
        self.status='completed';self.emit()
