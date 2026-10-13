"""Disposable browser-test API: real application, explicitly scripted mock model.

Not a deployment entry point. All persistence, permissions and workers are real;
only model decisions/wording are scripted, as in backend integration fixtures.
"""
import os
if os.getenv('AEGIS_ALLOW_MOCK','').lower()!='true' or os.getenv('MODEL_PROVIDER')!='mock':
    raise RuntimeError('Browser fixtures require an explicitly disposable mock deployment.')

from app import main, core, agent_model, providers

ROUTES = {
    'List document filenames': {'agent':'chat','query':'documents'},
    'How many documents are indexed?': {'agent':'chat','query':'document_count'},
    'Summarize the key points': {'agent':'chat','query':'original','answer_kind':'summary'},
}

def scripted_complete(messages, tools, on_token=None):
    cfg=core.settings()
    protocol=(cfg.get('model_connection') or {}).get('protocol') if cfg['model_provider']=='registered' else cfg['model_provider']
    if protocol!='mock':raise providers.ProviderError('Browser test fixtures cannot contact real model providers.')
    names={tool['function']['name'] for tool in tools}
    if 'route_aegis' in names:
        request=next(m['content'] for m in reversed(messages) if m['role']=='user').split('CURRENT request: ')[-1]
        route=ROUTES.get(request)
        if request.startswith('Complete the confirmed request using its saved results: '):
            route={'agent':'chat','query':'results','answer_kind':'summary'}
        if route is None:raise providers.ProviderError('No scripted browser routing decision for this request.')
        return {'text':'','calls':[{'name':'route_aegis','arguments':route|{'request_evidence':request}}]}
    if tools:raise providers.ProviderError('Browser fixtures do not provide unscripted tool decisions.')
    text='Saved reference MOCK TEST VALUE. [1]' if any('MOCK TEST VALUE' in m.get('content','') for m in messages) else 'Synthetic source reference SYN-2026. [1]'
    if on_token:on_token(text)
    return {'text':text,'calls':[]}

agent_model.complete=scripted_complete
app=main.app

# Only the guarded synthetic deployment prints complete diagnostics. Production
# publication handlers continue to report sanitized, recoverable errors.
import traceback
from functools import wraps
from app import agent_onboarding, knowledge
def diagnostic(operation):
    @wraps(operation)
    def wrapped(*args,**kwargs):
        try:return operation(*args,**kwargs)
        except Exception:
            traceback.print_exc()
            raise
    return wrapped
agent_onboarding.publish_knowledge=diagnostic(agent_onboarding.publish_knowledge)
knowledge.sync=diagnostic(knowledge.sync)

if __name__=='__main__':
    import sys,time
    if sys.argv[1:]!=['--worker']:raise RuntimeError('Only the disposable worker entry point is supported.')
    from app import worker
    # Diagnostic traces are safe only in this synthetic, mock-only deployment.
    # Production worker logs continue to exclude provider bodies and credentials.
    worker.process=diagnostic(worker.process)
    core.init()
    while True:
        if not worker.run_once():time.sleep(2)
