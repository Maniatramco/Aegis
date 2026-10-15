"""Validate/render/apply Aegis's one non-secret runtime file to existing OKE."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_CONFIG=ROOT/'ags_backend/ags_app/ags_config/runtime.toml'


def plan(config,profile='oci',backend_image=None):
    spec=importlib.util.spec_from_file_location('aegis_runtime_config',ROOT/'ags_backend/ags_app/runtime_config.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    previous={key:os.environ.get(key) for key in ('AEGIS_CONFIG_FILE','AEGIS_CONFIG_PROFILE')}
    try:
        os.environ['AEGIS_CONFIG_FILE']=str(Path(config).resolve());os.environ['AEGIS_CONFIG_PROFILE']=profile
        # Render from the file only, never from the operator shell's overrides.
        _,_,document,settings,_=module._selection()
        overrides={key:os.environ.pop(key) for key in settings if key in os.environ}
        try:module.validate()
        finally:os.environ.update(overrides)
    finally:
        for key,value in previous.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
    content=Path(config).read_text(encoding='utf-8')
    if backend_image and not re.fullmatch(r'[^\s]+@sha256:[a-f0-9]{64}',backend_image):
        raise ValueError('The backend image must be pinned by digest.')
    checksum=hashlib.sha256((profile+'\n'+content).encode()).hexdigest()
    configmap={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'aegis-runtime-config'},'data':{'runtime.toml':content}}
    containers=[]
    for name in ('api','worker'):
        container={'name':name,'env':[{'name':'AEGIS_CONFIG_FILE','value':'/etc/aegis/runtime.toml'},
                                     {'name':'AEGIS_CONFIG_PROFILE','value':profile}],
                   'volumeMounts':[{'name':'runtime-config','mountPath':'/etc/aegis','readOnly':True}]}
        if backend_image:container['image']=backend_image
        containers.append(container)
    patch={'spec':{'template':{'metadata':{'annotations':{'aegis.runtime/config-sha256':checksum}},
         'spec':{'volumes':[{'name':'runtime-config','configMap':{'name':'aegis-runtime-config'}}],
                 'containers':containers}}}}
    # Retire the previous two-key budget overlay as well as duplicated envFrom
    # settings. Other infrastructure values and Kubernetes Secrets are untouched.
    environment_patch={'data':{key:None for key in settings}}
    return {'configmap':configmap,'deployment_patch':patch,'environment_patch':environment_patch,
            'profile':profile,'sha256':checksum,'managed_keys':sorted(settings)}


def apply(config,profile,kubeconfig,namespace='aegis-oci',backend_image=None):
    rendered=plan(config,profile,backend_image)
    prefix=['kubectl','--kubeconfig',str(Path(kubeconfig).resolve()),'-n',namespace]
    with tempfile.TemporaryDirectory(prefix='aegis-runtime-') as folder:
        folder=Path(folder)
        for name in ('configmap','deployment_patch','environment_patch'):
            (folder/(name+'.json')).write_text(json.dumps(rendered[name]),encoding='utf-8')
        subprocess.run(prefix+['apply','-f',str(folder/'configmap.json')],check=True)
        subprocess.run(prefix+['patch','configmap','aegis-config','--type','merge','--patch-file',str(folder/'environment_patch.json')],check=True)
        subprocess.run(prefix+['patch','deployment','aegis-api-worker','--type','strategic','--patch-file',str(folder/'deployment_patch.json')],check=True)
    return rendered


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file',type=Path,default=DEFAULT_CONFIG)
    parser.add_argument('--profile',default='oci')
    parser.add_argument('--kubeconfig',type=Path,default=ROOT/'ags_runtime/ags_oke/kubeconfig.yaml')
    parser.add_argument('--namespace',default='aegis-oci')
    parser.add_argument('--backend-image')
    parser.add_argument('--apply',action='store_true',help='Without this flag, validate and preview only.')
    args=parser.parse_args()
    rendered=(apply(args.file,args.profile,args.kubeconfig,args.namespace,args.backend_image) if args.apply
              else plan(args.file,args.profile,args.backend_image))
    print(json.dumps({'applied':args.apply,'file':str(args.file.resolve()),'profile':args.profile,
                      'managed_settings':len(rendered['managed_keys']),'config_sha256':rendered['sha256']},indent=2))


if __name__=='__main__':main()
