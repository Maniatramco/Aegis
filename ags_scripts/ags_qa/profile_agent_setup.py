"""Read-only live OCI setup timing; no model inference or business mutations."""
import time,json
from sqlalchemy import event
from ags_app import core,dataset_models as routing,dataset_access,temporary_chat
from ags_app.chat_knowledge import PublishedKnowledge
actor=dataset_access.request_actor.set('administrator')
d=routing.owned('36fe2487-eaa3-5132-a9bd-12fdb48bcc52','administrator','knowledge_base')
model=routing.dataset_config(d)['default_chat_model_id']
counts={'sql':0}
def count(*args):counts['sql']+=1
event.listen(core.current_engine(),'before_cursor_execute',count)
report=[]
try:
    for name,fn in [('unscoped_model_snapshot',lambda:temporary_chat.chat_snapshot('administrator',model)),('dataset_execution_snapshot',lambda:routing.execution_snapshot(d,'chat',model)),('published_knowledge_setup',lambda:PublishedKnowledge('administrator',d.id))]:
        counts['sql']=0;t=time.perf_counter();fn();report.append({'stage':name,'seconds':round(time.perf_counter()-t,3),'sql_roundtrips':counts['sql']})
    print(json.dumps(report,indent=2))
finally:
    event.remove(core.current_engine(),'before_cursor_execute',count)
    dataset_access.request_actor.reset(actor)
