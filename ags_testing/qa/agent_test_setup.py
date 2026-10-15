"""Explicit operator QA setup; credentials are encrypted externally, never logged.

Not run by application startup. Creates only a separate fictional-data account.
"""
import json
import secrets
import time
import httpx
from ags_app import core
from ags_app.provision_account import create_account

REF = 'diagnostics/langgraph-ui-auth.enc'

def run():
    core.init()
    try:
        value = json.loads(core.secret_cipher().decrypt(core.local_store.get(REF)))
        print(json.dumps({'dataset_id':value['dataset_id'],'reused':True}))
        return
    except FileNotFoundError:
        pass
    value = {'username':'agent-qa-'+str(int(time.time())), 'password':secrets.token_urlsafe(24)}
    create_account(value['username'], value['password'])
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=180) as client:
        response=client.post('/api/auth/login',json=value);response.raise_for_status()
        client.headers['X-CSRF-Token']=response.json()['csrf_token']
        response=client.post('/api/datasets',json={'name':'LangGraph resume QA'});response.raise_for_status()
        value['dataset_id']=response.json()['id']
        response=client.post('/api/datasets/'+value['dataset_id']+'/migrate-settings');response.raise_for_status()
        data=response.json()
        value['model_id']=data['default_chat_model_id']
        # Use the same explicitly imported local configuration as the app.
        # Model parameters belong to /model-registrations, not /models.
    core.local_store.put(REF,core.secret_cipher().encrypt(json.dumps(value).encode()))
    print(json.dumps({'dataset_id':value['dataset_id'],'model_id':value['model_id'],'created':True}))

if __name__=='__main__':run()
