"""Interactive Aegis release in free OCI Cloud Shell; no managed build service."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('aegis_cloud_shell_base',ROOT/'ags_deploy/scripts/release_cli.py')
cli=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class CloudShellWorkflow(cli.Workflow):
    requires_powershell=False

    def prepare(self):
        if not os.environ.get('OCI_CLI_CLOUD_SHELL') or not os.environ.get('OCI_CS_USER_OCID'):
            raise cli.DeploymentStopped('Run this route inside OCI Cloud Shell, not on a live application node')
        if sys.version_info<(3,10):
            raise cli.DeploymentStopped('Use the included python3.12 runtime')
        if 'DatabaseAction' in self.values:
            raise cli.DeploymentStopped('Cloud Shell uses DB_Object Y/N and DB_ReleaseFile; legacy SQLcl install is not supported here')
        self.tenancy=os.environ.get('OCI_TENANCY','')
        if not self.tenancy.startswith('ocid1.tenancy.'):
            raise cli.DeploymentStopped('Cannot identify the Cloud Shell tenancy')
        if not os.environ.get('OCI_REGION'):
            raise cli.DeploymentStopped('Cannot identify the Cloud Shell region')
        self.machine=platform.machine()
        if self.components and self.machine not in ('aarch64','x86_64'):
            raise cli.DeploymentStopped('Unsupported Cloud Shell architecture')
        for tool in ('git','oci',*(['podman','kubectl'] if self.components else [])):
            if not shutil.which(tool):raise cli.DeploymentStopped('Required Cloud Shell tool missing: '+tool)
        super().prepare()
        for name in ('cloud_shell/cloud_shell_release.py','cloud_shell/deploy-cloud-shell.sh',
                     'scripts/release_cli.py','scripts/check-code-release.py',
                     'scripts/oci_schema_check.py','scripts/oracle_release.py'):
            current=ROOT/'ags_deploy'/name
            exported=self.source/'ags_deploy'/name
            if not exported.is_file() or current.read_bytes().replace(b'\r\n',b'\n')!=exported.read_bytes().replace(b'\r\n',b'\n'):
                raise cli.DeploymentStopped('Use the tested committed Cloud Shell route: '+name)
        self.storage={
            'backend':self.directory/'podman-backend',
            'frontend':Path('/tmp')/('aegis-'+self.release+'-frontend')}
        self.record.update(build_route='OCI Cloud Shell / Podman; no managed-build compute',
            cloud_shell_tenancy=self.tenancy,cloud_shell_region=os.environ.get('OCI_REGION',''),
            storage_roots={k:str(v) for k,v in self.storage.items() if k in self.components})

    def approve_connection(self):
        print('Cloud Shell tenancy: '+self.tenancy+'. Read-only preflight also verifies its remaining free Cloud Shell allowance.')
        super().approve_connection()
        self.check_allowance()

    def check_allowance(self):
        if not self.connect_approved:
            raise cli.DeploymentStopped('CONNECT approval required before OCI allowance inspection')
        raw=self.runner.capture(['oci','limits','resource-availability','get',
            '--service-name','cloud-shell','--limit-name','usage-hours','--compartment-id',self.tenancy,
            '--region',os.environ['OCI_REGION'],'--output','json'])
        allowance=json.loads(raw)['data']
        available=allowance.get('available')
        if not isinstance(available,(int,float)) or available<2:
            raise cli.DeploymentStopped('At least two verified free Cloud Shell hours must remain; no paid fallback is allowed')
        self.record['free_cloud_shell_hours_available']=available

    def metadata_preflight(self):
        result=super().metadata_preflight()
        expected='linux/arm64' if self.machine=='aarch64' else 'linux/amd64'
        if self.platform!=expected:
            raise cli.DeploymentStopped('Cloud Shell architecture does not match the ready OKE nodes; no emulation or node changes are performed')
        self.check_allowance()
        if not getattr(self,'build_started',False):
            for component in self.components:
                location=self.directory if component=='backend' else Path('/tmp')
                if shutil.disk_usage(location).free < 3.5*1024**3:
                    raise cli.DeploymentStopped('Insufficient Cloud Shell build space for '+component+'; no new storage is provisioned')
        return result

    def podman(self,component):
        root=self.storage[component]
        # Podman's runroot must be shorter than 50 characters on Cloud Shell.
        token=hashlib.sha256(self.release.encode()).hexdigest()[:12]
        runroot=Path('/tmp')/('ags-'+token+'-'+component)
        return ['podman','--root',str(root/'storage'),'--runroot',str(runroot)]

    def image(self,component):
        return self.web_image if component=='frontend' else self.backend_image

    def build(self):
        # One isolated store per filesystem keeps the two builds within Cloud
        # Shell's existing home and /tmp allocations. No global prune or cleanup.
        self.runner.capture(['podman','login','--get-login',self.registry])
        self.build_started=True
        for component in self.components:
            root=self.storage[component]
            root.mkdir(parents=True,exist_ok=False)
            args=self.podman(component)+['build','--format','docker','--platform',self.platform,
                '--label','org.opencontainers.image.revision='+self.commit,'-t',self.image(component)]
            if component=='backend':
                for name,value in (('INSTALL_LOCAL_EMBEDDINGS','false'),('INSTALL_CLOUD_MODELS','true'),
                                   ('INSTALL_ORACLE','true'),('INSTALL_OCI','true')):
                    args+=['--build-arg',name+'='+value]
            self.runner.interactive(args+[str(self.source/('ags_'+component))])
        self.image_ids=self.inspect_image_ids()

    def inspect_image_ids(self):
        result={}
        for component in self.components:
            image=self.image(component)
            info=json.loads(self.runner.capture(self.podman(component)+['image','inspect',image]))[0]
            if info['Os']+'/'+info['Architecture']!=self.platform:
                raise cli.DeploymentStopped('Built Cloud Shell image architecture mismatch')
            image_id=info['Id']
            if not image_id.startswith('sha256:'):image_id='sha256:'+image_id
            if not re.fullmatch(r'sha256:[a-f0-9]{64}',image_id):
                raise cli.DeploymentStopped('Invalid built Cloud Shell image ID')
            result[image]=image_id
        return result

    def release_images(self):
        if not self.publish_approved:raise cli.DeploymentStopped('PUBLISH approval required')
        self.check_target_file()
        if self.inspect_image_ids()!=self.image_ids:
            raise cli.DeploymentStopped('Reviewed Cloud Shell images changed')
        receipt=self.source/'ags_deploy/deployment-records'/('cloud-shell-'+self.release+'.json')
        receipt.parent.mkdir(parents=True,exist_ok=True)
        record={'context':self.record['context'],'server':self.record['server'],'namespace':self.options.namespace,
            'release':self.release,'components':self.components,'route':'OCI Cloud Shell',
            'previous':[{'deployment':name,'containers':[{'name':n,'image':image} for n,image in item['images'].items()]}
                        for name,item in self.baseline['deployments'].items()],
            'web_image':None,'backend_image':None,'published_components':[],
            'attempted_rollouts':[],'completed_rollouts':[]}
        def checkpoint():receipt.write_text(json.dumps(record,indent=2),encoding='utf-8')
        checkpoint()
        self.record['receipt']=str(receipt)
        self.runner.last_receipt=str(receipt)
        for component in self.components:
            digest_path=self.directory/(component+'-published-digest.txt')
            self.runner.interactive(self.podman(component)+['push','--digestfile',str(digest_path),
                self.image(component),'docker://'+self.image(component)])
            published=digest_path.read_text().strip()
            if not re.fullmatch(r'sha256:[a-f0-9]{64}',published):
                raise cli.DeploymentStopped('Registry did not return a valid publication digest')
            record['web_image' if component=='frontend' else 'backend_image']=self.image(component).rsplit(':',1)[0]+'@'+published
            record['published_components'].append(component)
            checkpoint()
        # Publish every selected image before changing any existing deployment.
        for component in ('backend','frontend'):
            if component not in self.components:continue
            name='aegis-api-worker' if component=='backend' else 'aegis-web'
            image=record['backend_image' if component=='backend' else 'web_image']
            containers=('api','worker') if component=='backend' else ('web',)
            record['attempted_rollouts'].append(component)
            checkpoint()
            self.kubectl(['set','image','deployment/'+name,*[c+'='+image for c in containers]])
            self.kubectl(['rollout','status','deployment/'+name,'--timeout=15m'],timeout=940)
            record['completed_rollouts'].append(component)
            checkpoint()
        return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--check-only',action='store_true')
    options=parser.parse_args()
    try:
        CloudShellWorkflow(cli.load_inputs(options.inputs),options.check_only).run()
    except (KeyboardInterrupt,EOFError):
        print('Cancelled. Inspect the exact result/receipt before retrying.',file=sys.stderr)
        return 130
    except Exception as error:
        if isinstance(error,(cli.DeploymentStopped,cli.ORACLE_RELEASE.OracleReleaseError,cli.SCHEMA.SchemaMismatch,cli.GUARD.ReleaseCheckError)):
            print('Cloud Shell release stopped: '+str(error),file=sys.stderr)
        else:print('Cloud Shell release stopped: '+type(error).__name__+'; inspect the exact result/receipt.',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
