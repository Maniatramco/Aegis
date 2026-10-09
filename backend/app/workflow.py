"""Persist actual worker transitions separately from legacy numeric progress."""
import time
from . import core

STAGES=('upload','extract','index','ready')

def read(jid):
    try:return core.store.json('jobs/'+jid+'/workflow.json')
    except FileNotFoundError:return {'stages':{},'current':None,'notice':'Stage details unavailable for this older job.'}

def initialize(jid,kind='index'):
    if kind=='extract':
        core.store.put_json('jobs/'+jid+'/workflow.json',{'current':'prepare','stages':{
            'prepare':{'status':'queued'},'generate':{'status':'blocked'},
            'validate':{'status':'blocked'},'ready':{'status':'blocked'}}})
        return
    core.store.put_json('jobs/'+jid+'/workflow.json',{'current':'extract','stages':{
        'upload':{'status':'completed','completed_at':time.time()},
        'extract':{'status':'queued'},'index':{'status':'blocked'},'ready':{'status':'blocked'}}})

def transition(jid,stage,status,error=None):
    data=read(jid);data['current']=stage
    data['stages'][stage]={'status':status,'updated_at':time.time(),**({'error':error} if error else {})}
    core.store.put_json('jobs/'+jid+'/workflow.json',data)

def fail(jid,error):
    data=read(jid)
    if data.get('current'):transition(jid,data['current'],'failed',error)

def retry(jid):
    data=read(jid)
    if data.get('current'):transition(jid,data['current'],'queued')
