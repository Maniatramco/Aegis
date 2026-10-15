"""Interactive, input-file driven Aegis release. No infrastructure provisioning.

Run through deploy.ps1. All external mutation is below the explicit PUBLISH
checkpoint; CONNECT permits read-only target discovery. No --yes bypass exists.
"""
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace
import urllib.request
import uuid
import zipfile


ROOT = Path(__file__).resolve().parents[1]
FIELDS = {'SourcePath', 'Ref', 'Kubeconfig', 'Context', 'Namespace', 'Registry',
          'RegistryNamespace', 'Platform', 'AppUrl', 'DatabaseAction', 'WalletPath',
          'DatabaseOwner', 'ServiceAlias', 'ExpectedService', 'SqlclPath',
          'BackupReference', 'ValidationReference'}


def module_from(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GUARD = module_from(ROOT/'ags_deploy/check-code-release.py', 'release_guard')
SCHEMA = module_from(ROOT/'ags_deploy/oci_schema_check.py', 'oci_schema_check')


class DeploymentStopped(RuntimeError):
    pass


class Runner:
    last_receipt = None

    def capture(self, arguments, *, cwd=None, input_text=None, timeout=60):
        result = subprocess.run(arguments, cwd=cwd, input=input_text, text=True,
                                encoding='utf-8', errors='replace', capture_output=True, timeout=timeout)
        if result.returncode:
            raise DeploymentStopped(Path(str(arguments[0])).name+' failed; inspect existing access and the reported phase. Sensitive command output was withheld.')
        return result.stdout

    def interactive(self, arguments, *, cwd=None):
        result = subprocess.run(arguments, cwd=cwd)
        if result.returncode:
            raise DeploymentStopped('The interactive tool failed; no dependent step was started')

    def stream(self, arguments, *, cwd=None):
        self.last_receipt = None
        receipts = []
        with subprocess.Popen(arguments, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding='utf-8', errors='replace') as process:
            for line in process.stdout:
                print(line, end='', flush=True)
                prefix = 'Previous images and destination saved: '
                if line.strip().startswith(prefix):
                    receipts.append(line.strip()[len(prefix):])
                    if len(receipts) == 1:
                        self.last_receipt = receipts[0]
            code = process.wait()
        if code:
            raise DeploymentStopped('Application release failed; inspect the saved phases/images before retrying. No automatic rollback was attempted')
        if len(receipts) != 1:
            raise DeploymentStopped('The release did not report exactly one receipt; inspect current images before any retry')
        return Path(receipts[0])


def ask(label, default='', input_fn=input):
    result = input_fn(label+(f' [{default}]' if default else '')+': ').strip()
    return result or default


def confirm(token, message, input_fn=input):
    print(message)
    if input_fn(f'Type {token} to continue: ').strip() != token:
        raise DeploymentStopped('Not approved. No dependent action was started')


def require_pattern(value, pattern, label):
    if not re.fullmatch(pattern, value):
        raise DeploymentStopped('Invalid '+label)
    return value


def load_inputs(path):
    if path is None:
        return {}
    path = path.resolve(strict=True)
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or set(data)-FIELDS:
        raise DeploymentStopped('Input JSON contains unsupported fields. Use the non-secret example; passwords/tokens are not accepted in this file')
    if not all(isinstance(value, str) for value in data.values()):
        raise DeploymentStopped('Every input JSON value must be a string')
    for field in ('SourcePath', 'Kubeconfig', 'WalletPath'):
        if data.get(field):
            candidate = Path(data[field]).expanduser()
            data[field] = str(candidate if candidate.is_absolute() else (path.parent/candidate).resolve())
    return data


def export_commit(source_root, ref, directory, runner):
    commit = runner.capture(['git', '-C', str(source_root), 'rev-parse', '--verify', '--end-of-options', ref+'^{commit}']).strip()
    require_pattern(commit, r'[a-f0-9]{40,64}', 'source commit')
    archive = directory/'source.zip'
    runner.capture(['git', '-C', str(source_root), 'archive', '--format=zip', '--output', str(archive), commit])
    source = directory/'source'
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            path = PurePosixPath(member.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in member.filename:
                raise DeploymentStopped('Invalid source archive path')
        package.extractall(source)
    for relative in ('ags_frontend/Dockerfile', 'ags_backend/Dockerfile', 'ags_database/install.sql',
                     'ags_database/deploy-oci-database.ps1', 'ags_deploy/deploy-aegis-code.ps1'):
        if not (source/relative).is_file():
            raise DeploymentStopped('The selected commit lacks required release files: '+relative)
    return source, commit


def source_fingerprint(source):
    hashes = {}
    for prefix in ('ags_frontend', 'ags_backend', 'ags_database'):
        for path in sorted((source/prefix).rglob('*')):
            if path.is_file():
                hashes[path.relative_to(source).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    hashes['release-helper'] = hashlib.sha256((source/'ags_deploy/deploy-aegis-code.ps1').read_bytes()).hexdigest()
    return GUARD.fingerprint(hashes)


def compare_protected(before, after):
    for field in ('context', 'server', 'namespace', 'resources'):
        if before[field] != after[field]:
            raise DeploymentStopped('Target/configuration changed during preparation: '+field)
    if set(before['deployments']) != set(after['deployments']):
        raise DeploymentStopped('Deployment set changed during preparation')
    for name, item in before['deployments'].items():
        current = after['deployments'][name]
        if any(item[key] != current[key] for key in ('uid', 'configuration_sha256', 'images')):
            raise DeploymentStopped('Deployment settings/images changed during preparation: '+name)


def infer_registry(deployments):
    prefixes = set()
    for name, containers in GUARD.APP_CONTAINERS.items():
        for container in containers:
            parts = deployments[name]['images'][container].split('/')
            if len(parts) < 3:
                return '', ''
            prefixes.add((parts[0], parts[1]))
    return next(iter(prefixes)) if len(prefixes) == 1 else ('', '')


def infer_platform(nodes, deployments, requested=''):
    choices = set()
    for node in nodes:
        if node.get('spec', {}).get('unschedulable'):
            continue
        if not any(item.get('type') == 'Ready' and item.get('status') == 'True' for item in node.get('status', {}).get('conditions', [])):
            continue
        labels = node['metadata'].get('labels', {})
        choices.add(labels.get('kubernetes.io/os', '')+'/'+labels.get('kubernetes.io/arch', ''))
    if not choices <= {'linux/arm64', 'linux/amd64'} or not choices:
        raise DeploymentStopped('Cannot verify a supported ready-node architecture')
    if len(choices) == 1:
        platform = next(iter(choices))
        if requested and requested != platform:
            raise DeploymentStopped('Requested image platform differs from the ready nodes')
        return platform
    if not requested or requested not in choices or not all(
            item['spec']['template']['spec'].get('nodeSelector', {}).get('kubernetes.io/arch') == requested.split('/')[1]
            for item in deployments):
        raise DeploymentStopped('Mixed architectures need existing matching node placement; this script will not change it')
    return requested


def infer_url(resources):
    hosts = set()
    for item in resources:
        if item['kind'] == 'ConfigMap' and 'Caddyfile' in item.get('data', {}):
            match = re.search(r'(?m)^\s*([A-Za-z0-9][A-Za-z0-9.-]+)\s*\{', item['data']['Caddyfile'])
            if match:
                hosts.add('https://'+match[1])
    return next(iter(hosts)) if len(hosts) == 1 else ''


def ps_literal(value):
    return "'"+str(value).replace("'", "''")+"'"


def empty_owner_driver(wallet, owner, alias, service, log):
    for path in (wallet, log):
        if any(character in str(path) for character in ('"', '\r', '\n')):
            raise DeploymentStopped('SQLcl paths cannot contain quotes or line breaks')
    require_pattern(owner, r'[A-Z][A-Z0-9_$#]{0,127}', 'database owner')
    require_pattern(alias, r'[A-Za-z0-9_.-]+', 'wallet alias')
    require_pattern(service, r'[A-Za-z0-9_.-]+', 'full database service')
    if owner in ('SYS', 'SYSTEM'):
        raise DeploymentStopped('Use the prepared application owner')
    return f'''SET ECHO OFF
SET VERIFY OFF
SET DEFINE OFF
SET SERVEROUTPUT ON
WHENEVER OSERROR EXIT FAILURE ROLLBACK
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
SET CLOUDCONFIG "{wallet}"
CONNECT {owner}@{alias}
SPOOL "{log}"
SET TRANSACTION READ ONLY;
DECLARE
  objects NUMBER; available NUMBER; privileges NUMBER; probe NUMBER;
BEGIN
  IF USER <> '{owner}' OR SYS_CONTEXT('USERENV','CURRENT_SCHEMA') <> '{owner}'
     OR LOWER(SYS_CONTEXT('USERENV','SERVICE_NAME')) <> LOWER('{service}') THEN
    RAISE_APPLICATION_ERROR(-20001,'Wrong destination owner/service');
  END IF;
  SELECT COUNT(*) INTO objects FROM user_objects;
  IF objects <> 0 THEN RAISE_APPLICATION_ERROR(-20002,'Fresh installation requires an empty owner'); END IF;
  SELECT COUNT(*) INTO privileges FROM session_privs WHERE privilege='CREATE TABLE';
  IF privileges=0 THEN RAISE_APPLICATION_ERROR(-20003,'CREATE TABLE privilege is missing'); END IF;
  SELECT COUNT(*) INTO available FROM user_ts_quotas q,user_users u
    WHERE q.tablespace_name=u.default_tablespace AND (q.max_bytes=-1 OR q.max_bytes>q.bytes);
  SELECT COUNT(*) INTO privileges FROM session_privs WHERE privilege='UNLIMITED TABLESPACE';
  IF available=0 AND privileges=0 THEN RAISE_APPLICATION_ERROR(-20004,'Prepared owner needs quota'); END IF;
  SELECT LENGTH(CAST('x' AS VARCHAR2(32767 BYTE))) INTO probe FROM dual;
  SELECT CASE WHEN CAST(TRUE AS BOOLEAN) THEN 1 ELSE 0 END INTO probe FROM dual;
  IF probe<>1 THEN RAISE_APPLICATION_ERROR(-20005,'SQL BOOLEAN unavailable'); END IF;
  SELECT VECTOR_DISTANCE(TO_VECTOR('[1,0]'),TO_VECTOR('[1,0]'),COSINE) INTO probe FROM dual;
  IF probe<>0 THEN RAISE_APPLICATION_ERROR(-20006,'Native vector support unavailable'); END IF;
  DBMS_OUTPUT.PUT_LINE('AEGIS_EMPTY_OWNER_OK|{owner}|{service}|0');
END;
/
ROLLBACK;
SPOOL OFF
EXIT SUCCESS
'''


class Workflow:
    def __init__(self, values, check_only=False, runner=None, input_fn=input):
        self.values = dict(values)
        self.check_only = check_only
        self.runner = runner or Runner()
        self.input = input_fn
        self.phase = 'local preparation'
        self.record = {'state': 'preparing', 'phases': [], 'database_installed': False}
        self.directory = None
        self.connect_approved = False
        self.publish_approved = False

    def value(self, key, label, default='', required=True):
        value = self.values.get(key, '').strip()
        if not value:
            value = ask(label, default, self.input)
        if required and not value:
            raise DeploymentStopped('Required input missing: '+key)
        self.values[key] = value
        return value

    def save(self, phase):
        self.phase = phase
        self.record['phases'].append({'phase': phase, 'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()})
        print('\n'+phase, flush=True)
        if self.directory:
            (self.directory/'result.json').write_text(json.dumps(self.record, indent=2), encoding='utf-8')

    def kubectl(self, arguments, input_text=None, timeout=50):
        if not self.connect_approved:
            raise DeploymentStopped('CONNECT approval is required before target inspection')
        self.check_target_file()
        request_timeout = '0' if arguments[:2] == ['rollout', 'status'] else '25s'
        command = ['kubectl', '--kubeconfig', str(self.options.kubeconfig), '--context', self.options.context,
                   '--request-timeout='+request_timeout, '-n', self.options.namespace, *arguments]
        return self.runner.capture(command, input_text=input_text, timeout=timeout)

    def check_target_file(self):
        if hashlib.sha256(self.options.kubeconfig.read_bytes()).hexdigest() != self.kubeconfig_hash:
            raise DeploymentStopped('Kubeconfig changed after target selection; select and approve the destination again')

    def target_json(self, arguments, input_text=None):
        return json.loads(self.kubectl(arguments, input_text))

    def prepare(self):
        root_value = self.values.get('SourcePath') or str(ROOT)
        self.source_root = Path(root_value).expanduser().resolve(strict=True)
        ref = self.values.get('Ref') or 'ags_sprint1'
        require_pattern(ref, r'[A-Za-z0-9_][A-Za-z0-9_./-]*', 'source ref')
        kubeconfig = Path(self.value('Kubeconfig', 'Existing destination kubeconfig path')).expanduser().resolve(strict=True)
        self.kubeconfig_hash = hashlib.sha256(kubeconfig.read_bytes()).hexdigest()
        local = json.loads(self.runner.capture(['kubectl', '--kubeconfig', str(kubeconfig), 'config', 'view', '-o', 'json']))
        contexts = {item['name']: item['context'] for item in local.get('contexts', [])}
        if not contexts:
            raise DeploymentStopped('This kubeconfig contains no contexts')
        context = self.values.get('Context', '')
        if not context:
            if len(contexts) == 1:
                context = next(iter(contexts))
            else:
                print('Local kubeconfig contexts: '+', '.join(sorted(contexts)))
                context = self.value('Context', 'Choose the destination context')
        if context not in contexts:
            raise DeploymentStopped('The selected context is absent from the supplied kubeconfig')
        clusters = {item['name']: item['cluster'] for item in local.get('clusters', [])}
        server = clusters[contexts[context]['cluster']]['server']
        from urllib.parse import urlsplit
        parsed = urlsplit(server)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise DeploymentStopped('The existing Kubernetes server must be a credential-free HTTPS endpoint')
        namespace = self.values.get('Namespace') or 'aegis-oci'
        require_pattern(namespace, r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', 'namespace')
        action = self.values.get('DatabaseAction', '').lower()
        if not action:
            action = ask('Database action: verify existing schema, or install into a prepared empty owner', 'verify', self.input).lower()
        if action not in ('verify', 'install'):
            raise DeploymentStopped('DatabaseAction must be verify or install')
        self.action = action
        self.options = SimpleNamespace(kubeconfig=kubeconfig, context=context, namespace=namespace)
        self.release = 'release-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
        self.directory = self.source_root/'ags_deploy/deployment-records'/self.release
        self.directory.mkdir(parents=True, exist_ok=False)
        self.source, self.commit = export_commit(self.source_root, ref, self.directory, self.runner)
        self.source_hash = source_fingerprint(self.source)
        self.powershell = shutil.which('pwsh') or shutil.which('powershell')
        if not self.powershell:
            raise DeploymentStopped('PowerShell is required for the existing release helpers')
        self.record.update(source_commit=self.commit, source_fingerprint=self.source_hash,
                           context=context, server=server, namespace=namespace, database_action=action,
                           release=self.release, regression_tests='Not run by this CLI; operator evidence required')
        if action == 'install':
            self.wallet = Path(self.value('WalletPath', 'Destination wallet ZIP path')).expanduser().resolve(strict=True)
            self.db_owner = self.value('DatabaseOwner', 'Prepared EMPTY database owner').upper()
            self.alias = self.value('ServiceAlias', 'Destination wallet service alias')
            self.service = self.value('ExpectedService', 'Full server database service name')
            self.sqlcl = shutil.which(self.values.get('SqlclPath') or 'sql')
            if not self.sqlcl:
                raise DeploymentStopped('SQLcl must already be installed for a fresh schema installation')
            self.database_args = ['-WalletPath', str(self.wallet), '-UserName', self.db_owner,
                                  '-ServiceAlias', self.alias, '-ExpectedService', self.service,
                                  '-SqlclPath', self.sqlcl]
            self.ps_helper(self.source/'ags_database/deploy-oci-database.ps1', self.database_args+['-CheckOnly'])

    def ps_helper(self, path, arguments, stream=False):
        command = [self.powershell, '-NoProfile', '-File', str(path), *arguments]
        return self.runner.stream(command) if stream else self.runner.interactive(command)

    def approve_connection(self):
        self.check_target_file()
        confirm('CONNECT', 'Read-only access requested: '+self.record['context']+' / '+self.record['server']+
                ' / namespace '+self.record['namespace']+'. Database action: '+self.action+
                '. No table creation, image publishing or configuration changes during discovery.', self.input)
        self.connect_approved = True

    def metadata_preflight(self):
        deployments = self.target_json(['get', 'deployment', 'aegis-web', 'aegis-api-worker', '-o', 'json'])['items']
        records = {item['metadata']['name']: GUARD.deployment_record(item) for item in deployments}
        if set(records) != set(GUARD.APP_CONTAINERS):
            raise DeploymentStopped('Prepared Aegis Deployments are missing. This command does not provision them')
        resources = self.target_json(['get', GUARD.CONFIG_RESOURCES, '-o', 'json'])['items']
        snapshot = {'context': self.options.context, 'server': self.record['server'],
                    'namespace': self.options.namespace, 'deployments': records, 'resources': GUARD.resource_records(resources)}
        if not hasattr(self, 'initial_metadata'):
            nodes = self.target_json(['get', 'nodes', '-o', 'json'])['items']
            self.platform = infer_platform(nodes, deployments, self.values.get('Platform', ''))
            registry, namespace = infer_registry(records)
            self.registry = self.values.get('Registry') or registry or self.value('Registry', 'Existing OCIR host')
            self.registry_namespace = self.values.get('RegistryNamespace') or namespace or self.value('RegistryNamespace', 'Existing registry namespace')
            require_pattern(self.registry, r'[A-Za-z0-9.-]+', 'registry host')
            require_pattern(self.registry_namespace, r'[A-Za-z0-9_-]+', 'registry namespace')
            self.url = self.values.get('AppUrl') or infer_url(resources)
            if not self.url:
                ingress = self.target_json(['get', 'ingress', '-o', 'json']).get('items', [])
                hosts = {rule['host'] for item in ingress for rule in item.get('spec', {}).get('rules', []) if rule.get('host')}
                self.url = 'https://'+next(iter(hosts)) if len(hosts) == 1 else self.value('AppUrl', 'Existing application HTTPS URL')
            from urllib.parse import urlsplit
            parsed = urlsplit(self.url)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise DeploymentStopped('Provide the existing credential-free HTTPS application URL; this command does not configure DNS/TLS')
            self.web_image = f'{self.registry}/{self.registry_namespace}/ags-aegis-web:{self.release}'
            self.backend_image = f'{self.registry}/{self.registry_namespace}/ags-aegis-backend:{self.release}'
        return snapshot

    def snapshot(self):
        if not self.connect_approved:
            raise DeploymentStopped('CONNECT approval is required before target inspection')
        self.check_target_file()
        snapshot = GUARD.collect(self.options)
        GUARD.require_ready(snapshot)
        GUARD.validate_source(snapshot, self.source)
        return snapshot

    def verify_database(self):
        result = self.target_json(['exec', '-i', 'deployment/aegis-api-worker', '-c', 'api', '--', 'python', '-B', '-'], SCHEMA.inspection_script(self.source))
        totals = SCHEMA.verify_schema(self.source, result)
        for input_key, result_key in (('DatabaseOwner', 'owner'), ('ExpectedService', 'service_name'), ('ServiceAlias', 'wallet_alias')):
            expected = self.values.get(input_key, '')
            if expected and expected.casefold() != result[result_key].casefold():
                raise DeploymentStopped('Saved application database differs from the requested '+input_key)
        if self.action == 'install' and (result['owner'].upper() != self.db_owner or result['service_name'].casefold() != self.service.casefold()):
            raise DeploymentStopped('Prepared application connection does not point to the installed database; no configuration was changed')
        if result['active_jobs']:
            raise DeploymentStopped('Active database jobs exist; let them finish before releasing')
        return dict(totals, owner=result['owner'], service_name=result['service_name'], wallet_alias=result['wallet_alias'], active_jobs=0)

    def verify_empty_owner(self, number):
        if not self.connect_approved:
            raise DeploymentStopped('CONNECT approval is required before database inspection')
        log = self.directory/f'empty-owner-{number}.log'
        driver = self.directory/f'empty-owner-{number}.sql'
        driver.write_text(empty_owner_driver(self.wallet, self.db_owner, self.alias, self.service, log), encoding='utf-8')
        wrapper = self.directory/f'empty-owner-{number}.ps1'
        wrapper.write_text("$ErrorActionPreference='Stop'\n& "+ps_literal(self.sqlcl)+" -L /nolog "+ps_literal('@"'+str(driver)+'"')+"\nexit $LASTEXITCODE\n", encoding='utf-8-sig')
        print('SQLcl will privately prompt for the destination password (read-only empty-owner check).')
        self.ps_helper(wrapper, [])
        marker = f'AEGIS_EMPTY_OWNER_OK|{self.db_owner}|{self.service}|0'
        if not log.is_file() or marker not in log.read_text(encoding='utf-8-sig', errors='replace').splitlines():
            raise DeploymentStopped('The read-only empty-owner success marker is missing')
        return {'owner': self.db_owner, 'service_name': self.service, 'wallet_alias': self.alias,
                'existing_objects': 0, 'action': 'Create thirteen application tables only'}

    def inspect_image_ids(self):
        ids = {}
        for image in (self.web_image, self.backend_image):
            data = json.loads(self.runner.capture(['docker', 'image', 'inspect', image]))
            if len(data) != 1 or data[0]['Os']+'/'+data[0]['Architecture'] != self.platform:
                raise DeploymentStopped('A prepared image has the wrong platform')
            ids[image] = data[0]['Id']
        return ids

    def build(self):
        self.runner.interactive(['docker', 'build', '--platform', self.platform, '-t', self.web_image, str(self.source/'ags_frontend')])
        self.runner.interactive(['docker', 'build', '--platform', self.platform,
                                 '--build-arg', 'INSTALL_LOCAL_EMBEDDINGS=false', '--build-arg', 'INSTALL_CLOUD_MODELS=false',
                                 '--build-arg', 'INSTALL_ORACLE=true', '--build-arg', 'INSTALL_OCI=true',
                                 '-t', self.backend_image, str(self.source/'ags_backend')])
        self.image_ids = self.inspect_image_ids()

    def approve_publication(self):
        confirm('PUBLISH', 'Review the saved plan above. Approval covers this exact source, target, images and database action. '
                'Existing Recreate deployments restart pods and can briefly interrupt the app. '
                'Infrastructure, configuration, model mappings and data are preserved; no automatic rollback.', self.input)
        self.publish_approved = True

    def install_database(self):
        if not self.publish_approved:
            raise DeploymentStopped('PUBLISH approval is required before schema installation')
        self.record['database_install_attempted'] = True
        self.save('Running the guarded schema installer; DDL can commit partially on failure')
        self.ps_helper(self.source/'ags_database/deploy-oci-database.ps1', self.database_args)
        self.record['database_installed'] = True

    def release_images(self):
        if not self.publish_approved:
            raise DeploymentStopped('PUBLISH approval is required before image publication')
        self.check_target_file()
        arguments = ['-SourcePath', str(self.source), '-Kubeconfig', str(self.options.kubeconfig),
                     '-Context', self.options.context, '-Namespace', self.options.namespace,
                     '-Registry', self.registry, '-RegistryNamespace', self.registry_namespace,
                     '-Platform', self.platform, '-Release', self.release, '-SkipBuild']
        receipt = self.ps_helper(self.source/'ags_deploy/deploy-aegis-code.ps1', arguments, stream=True).resolve(strict=True)
        expected_directory = (self.source/'ags_deploy/deployment-records').resolve()
        if receipt.parent != expected_directory:
            raise DeploymentStopped('The reported receipt is outside this invocation source directory')
        return receipt

    def wait_after_schema(self):
        print('Waiting up to five minutes per existing deployment for readiness; no restart or configuration repair is performed.')
        for deployment in ('aegis-api-worker', 'aegis-web'):
            self.kubectl(['rollout', 'status', 'deployment/'+deployment, '--timeout=5m'], timeout=330)
        snapshot = self.snapshot()
        compare_protected(self.initial_metadata, snapshot)
        return snapshot

    def run(self):
        try:
            self.prepare()
            self.save('Awaiting read-only connection approval')
            self.approve_connection()
            self.save('Read-only target and database preflight')
            self.initial_metadata = self.metadata_preflight()
            if self.action == 'verify':
                self.baseline = self.snapshot()
                compare_protected(self.initial_metadata, self.baseline)
                self.database = self.verify_database()
            else:
                self.database = self.verify_empty_owner(1)
                self.baseline = None
            self.record.update(database=self.database, public_url=self.url, platform=self.platform,
                               previous_images={name: item['images'] for name, item in self.initial_metadata['deployments'].items()},
                               preserved_configuration='Fingerprints recorded; no infrastructure/configuration mutation is permitted',
                               model_checks='Model/relay configuration preserved; provider inference is not run by this CLI')
            if self.check_only:
                self.record.update(state='preflight-only', builds='Not run', publication='Not attempted')
                print(json.dumps(self.record, indent=2))
                self.save('Read-only preflight completed; no release attempted')
                return self.record
            self.backup = self.values.get('BackupReference') or ('New verified empty owner; no existing database data' if self.action == 'install' else self.value('BackupReference', 'Existing backup/restore point reference (not created by this command)'))
            self.validation = self.values.get('ValidationReference') or self.value('ValidationReference', 'Regression/CI evidence for this source (operator reference; tests are not run here)')
            self.save('Building local release images; nothing is published')
            self.build()
            if source_fingerprint(self.source) != self.source_hash:
                raise DeploymentStopped('Exported source changed during preparation')
            self.record.update(images=self.image_ids, backup_reference=self.backup, validation_reference=self.validation,
                               planned_actions=['Install thirteen tables in the verified empty owner' if self.action == 'install' else 'Verify existing schema; no DDL',
                                                'Verify schema and app configuration/readiness before publishing',
                                                'Push the two reviewed images; record immutable digests and previous images',
                                                'Update api and worker images, await readiness; update web image, await readiness',
                                                'Compare configuration fingerprints, verify schema and HTTPS'],
                               readiness='Verified' if self.baseline else 'Conditional: app readiness and saved-connection verification must pass after schema installation',
                               state='awaiting-publication-approval')
            compare_protected(self.initial_metadata, self.metadata_preflight())
            if self.baseline:
                GUARD.compare(self.baseline, self.snapshot())
                self.verify_database()
            plan = self.directory/'plan.json'
            plan.write_text(json.dumps(self.record, indent=2), encoding='utf-8')
            print('\nDEPLOYMENT PLAN\n'+json.dumps(self.record, indent=2))
            print('Private plan: '+str(plan))
            self.approve_publication()
            self.save('Rechecking the approved source, target and local image IDs')
            if source_fingerprint(self.source) != self.source_hash or self.inspect_image_ids() != self.image_ids:
                raise DeploymentStopped('Approved source/images changed; approval is no longer valid')
            compare_protected(self.initial_metadata, self.metadata_preflight())
            if self.action == 'install':
                self.verify_empty_owner(2)
                self.save('Installing the explicitly approved empty-owner schema')
                self.install_database()
                self.save('Checking app readiness and saved connection after schema installation')
                self.baseline = self.wait_after_schema()
                self.database = self.verify_database()
            else:
                GUARD.compare(self.baseline, self.snapshot())
                self.verify_database()
            (self.directory/'baseline.json').write_text(json.dumps(self.baseline, indent=2), encoding='utf-8')
            self.save('Publishing reviewed images and releasing API, worker and frontend')
            receipt = self.release_images()
            self.record['receipt'] = str(receipt)
            self.save('Verifying released images, preserved configuration and database schema')
            released = json.loads(receipt.read_text(encoding='utf-8-sig'))
            GUARD.compare(self.baseline, self.snapshot(), released)
            self.verify_database()
            with urllib.request.urlopen(self.url, timeout=20) as response:
                if response.status != 200:
                    raise DeploymentStopped('Application HTTPS check did not return HTTP 200')
            self.record.update(state='complete', https_status=200, web_image=released['web_image'], backend_image=released['backend_image'])
            self.save('Release completed; configuration checks passed')
            print('Application: '+self.url+'\nReceipt: '+str(receipt)+'\nRecord: '+str(self.directory/'result.json'))
            print('No inference or upload/extraction write tests were run. No infrastructure or configuration changes were made by this command.')
            return self.record
        except (Exception, KeyboardInterrupt) as error:
            self.record.update(state='stopped', stopped_at_phase=self.phase, error=type(error).__name__)
            if getattr(self.runner, 'last_receipt', None):
                self.record['reported_receipt'] = str(self.runner.last_receipt)
            if self.directory:
                (self.directory/'result.json').write_text(json.dumps(self.record, indent=2), encoding='utf-8')
                print('Stopped. Review phase/receipt before retrying: '+str(self.directory/'result.json'), file=sys.stderr)
                if self.record.get('database_installed'):
                    print('The approved schema was installed before the failure. Do not rerun a fresh install over it.', file=sys.stderr)
                elif self.record.get('database_install_attempted'):
                    print('Schema DDL was attempted and may have committed partially. Inspect the SQLcl log and owner before any retry.', file=sys.stderr)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, help='Non-secret destination JSON; missing values are prompted/discovered')
    parser.add_argument('--check-only', action='store_true', help='Read-only target/schema preflight; no builds, DDL, push or rollout')
    options = parser.parse_args()
    try:
        Workflow(load_inputs(options.inputs), options.check_only).run()
    except (DeploymentStopped, GUARD.ReleaseCheckError, SCHEMA.SchemaMismatch, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print('Aegis deployment stopped: '+str(error), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('Aegis deployment cancelled; inspect the private record before retrying.', file=sys.stderr)
        return 130
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
