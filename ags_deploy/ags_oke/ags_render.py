"""Render the isolated OCI deployment; rendering never applies resources.

The private release.json provides immutable image digests and the public host.
Credentials must be separate Kubernetes Secrets and are never rendered here.
"""
import argparse
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'ags_runtime/ags_oke'
NAMESPACE = 'aegis-oci'


def item(kind, name, **body):
    api = 'apps/v1' if kind == 'Deployment' else 'v1'
    return {'apiVersion': api, 'kind': kind, 'metadata': {'name': name, 'namespace': NAMESPACE}, **body}


def render(state, release):
    images = {name: release[name] for name in ('web_image', 'backend_image', 'ssh_image', 'caddy_image')}
    for image in images.values():
        if not re.fullmatch(r'[^\s]+@sha256:[a-f0-9]{64}', image):
            raise ValueError('Every image must be pinned by digest')
    host = release['hostname']
    if not re.fullmatch(r'aegis\.(?:\d{1,3}[.-]){3}\d{1,3}\.sslip\.io', host):
        raise ValueError('Use the approved generated sslip.io hostname')
    resources = [{'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': NAMESPACE}}]
    for name in ('application-state', 'https-state'):
        resources.append(item('PersistentVolumeClaim', name, spec={
            'accessModes': ['ReadWriteOnce'], 'storageClassName': 'oci-bv',
            'resources': {'requests': {'storage': '50Gi'}}}))
    spec=importlib.util.spec_from_file_location('aegis_runtime_deploy',Path(__file__).with_name('ags_runtime_config.py'))
    runtime_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime_module)
    runtime=runtime_module.plan(ROOT/'ags_backend/ags_app/ags_config/runtime.toml','oci')
    config = {
        # Oracle table names are chosen when core is imported. Use the Oracle
        # dialect even for the unused bootstrap engine; active_engine uses the
        # seeded OCI wallet/credentials. A credential-free bootstrap fails closed.
        'AEGIS_STORAGE_ROOT': '/data', 'DATABASE_PROVIDER': 'oracle',
        'DATABASE_URL': 'oracle+oracledb://', 'QUEUE_PROVIDER': 'database',
        'SEARCH_PROVIDER': 'oracle', 'MODEL_PROVIDER': 'ollama', 'EMBEDDING_PROVIDER': 'ollama',
        'AEGIS_MODEL': 'qwen3:4b', 'EMBEDDING_MODEL': 'nomic-embed-text',
        'AEGIS_OLLAMA_URL': 'http://ollama:11434', 'AEGIS_OLLAMA_ENDPOINT_HOSTS': 'ollama',

        'AEGIS_ALLOW_MOCK': 'false', 'LANGSMITH_TRACING': 'false',
        'COOKIE_SECURE': 'true', 'ALLOWED_ORIGINS': f'https://{host}',
    }
    resources.append(item('ConfigMap', 'aegis-config', data=config))
    runtime_map=runtime['configmap'];runtime_map['metadata']['namespace']=NAMESPACE
    resources.append(runtime_map)
    resources.append(item('ConfigMap', 'https-config', data={'Caddyfile':
        f'{host} {{\n  header Strict-Transport-Security "max-age=31536000"\n'
        '  reverse_proxy 127.0.0.1:3000 {\n    flush_interval -1\n  }\n}\n'}))
    volumes = [
        {'name': 'state', 'persistentVolumeClaim': {'claimName': 'application-state'}},
        {'name': 'oci', 'secret': {'secretName': 'oci-credentials', 'defaultMode': 288}},
        {'name': 'wallet', 'secret': {'secretName': 'database-wallet', 'defaultMode': 288}},
        {'name': 'ssh', 'secret': {'secretName': 'ssh-relay', 'defaultMode': 256}},
        {'name':'runtime-config','configMap':{'name':'aegis-runtime-config'}},
    ]
    mounts = [{'name':'runtime-config','mountPath':'/etc/aegis','readOnly':True},
              {'name': 'state', 'mountPath': '/data'},
        {'name': 'oci', 'mountPath': '/run/oci', 'readOnly': True},
        {'name': 'wallet', 'mountPath': '/run/aegis-db/wallet', 'readOnly': True}]
    api = {'name': 'api', 'image': images['backend_image'],
        'envFrom': [{'configMapRef': {'name': 'aegis-config'}}, {'secretRef': {'name': 'aegis-app'}}],
              'env':[{'name':'AEGIS_CONFIG_FILE','value':'/etc/aegis/runtime.toml'},{'name':'AEGIS_CONFIG_PROFILE','value':'oci'}],
        'ports': [{'containerPort': 8000}], 'volumeMounts': mounts,
        'resources': {'requests': {'cpu': '250m', 'memory': '768Mi'}, 'limits': {'cpu': '1000m', 'memory': '2Gi'}},
        'securityContext': {'runAsUser': 10001, 'runAsGroup': 10001, 'allowPrivilegeEscalation': False},
        'startupProbe': {'httpGet': {'path': '/ready', 'port': 8000}, 'periodSeconds': 10, 'failureThreshold': 60},
        'readinessProbe': {'httpGet': {'path': '/ready', 'port': 8000}, 'periodSeconds': 20, 'timeoutSeconds': 10},
        'livenessProbe': {'httpGet': {'path': '/health', 'port': 8000}, 'periodSeconds': 30, 'timeoutSeconds': 10}}
    worker = {k: v for k, v in api.items() if k not in ('ports', 'startupProbe', 'readinessProbe', 'livenessProbe')}
    worker.update(name='worker', command=['python', '-m', 'ags_app.worker'],
        resources={'requests': {'cpu': '500m', 'memory': '2Gi'}, 'limits': {'cpu': '1500m', 'memory': '4Gi'}})
    ssh = {'name': 'model-relay', 'image': images['ssh_image'],
        'ports': [{'containerPort': 2222}, {'containerPort': 11434}],
        'volumeMounts': [{'name': 'ssh', 'mountPath': '/run/ssh-keys', 'readOnly': True}],
        'resources': {'requests': {'cpu': '25m', 'memory': '32Mi'}, 'limits': {'cpu': '100m', 'memory': '128Mi'}},
        'securityContext': {'capabilities': {'drop': ['ALL'], 'add': ['SETUID', 'SETGID', 'SYS_CHROOT']}}}
    resources.append(item('Deployment', 'aegis-api-worker', spec={
        'replicas': 0 if state.get('application_paused') else 1,
        'strategy': {'type': 'Recreate'}, 'selector': {'matchLabels': {'app': 'aegis-api-worker'}},
        'template': {'metadata': {'labels': {'app': 'aegis-api-worker'},'annotations':{'aegis.runtime/config-sha256':runtime['sha256']}}, 'spec': {
            'automountServiceAccountToken': False, 'securityContext': {'fsGroup': 10001},
            'imagePullSecrets': [{'name': 'ocir-pull'}], 'volumes': volumes,
            'initContainers': [{'name': 'verify-existing-oci-state', 'image': images['backend_image'],
                'command': ['python', '-c',
                    "import json,pathlib; p=pathlib.Path('/data'); d=json.loads((p/'configuration/database.json').read_text()); "
                    "assert d.get('active_provider')=='oci', 'Seed the existing OCI configuration before starting'; "
                    "assert (p/d['active_connection']['secret_ref']).is_file(), 'Database secret reference missing'; "
                    "s=json.loads((p/'configuration/settings.json').read_text()); "
                    "assert s.get('storage_provider')=='oci', 'Expected existing OCI object storage'; "
                    "assert (p/'models/reranker').is_dir(), 'Existing reranker files missing'"],
                'securityContext': {'runAsUser': 10001, 'runAsGroup': 10001, 'allowPrivilegeEscalation': False},
                'volumeMounts': [{'name': 'state', 'mountPath': '/data'}]}],
            'containers': [api, worker, ssh]}}}))
    for name, port, target in [('api', 8000, 8000), ('ollama', 11434, 11434)]:
        resources.append(item('Service', name, spec={'type': 'ClusterIP',
            'selector': {'app': 'aegis-api-worker'}, 'ports': [{'port': port, 'targetPort': target}]}))
    resources.append(item('Service', 'model-relay-ssh', spec={'type': 'NodePort',
        'selector': {'app': 'aegis-api-worker'}, 'externalTrafficPolicy': 'Local',
        'ports': [{'port': 2222, 'targetPort': 2222, 'nodePort': 32022}]}))
    resources.append(item('Deployment', 'aegis-web', spec={
        'replicas': 1, 'strategy': {'type': 'Recreate'}, 'selector': {'matchLabels': {'app': 'aegis-web'}},
        'template': {'metadata': {'labels': {'app': 'aegis-web'}}, 'spec': {
            'automountServiceAccountToken': False, 'imagePullSecrets': [{'name': 'ocir-pull'}],
            'volumes': [{'name': 'https-state', 'persistentVolumeClaim': {'claimName': 'https-state'}},
                {'name': 'https-config', 'configMap': {'name': 'https-config'}}],
            'containers': [
                {'name': 'web', 'image': images['web_image'],
                    'env': [{'name': 'API_INTERNAL_URL', 'value': 'http://api:8000'},
                        {'name': 'AEGIS_DEPLOYMENT_TARGET', 'value': 'oci'},
                        {'name': 'AEGIS_API_LOCATION', 'value': 'oci'},
                        {'name': 'AEGIS_WORKER_LOCATION', 'value': 'oci'},
                        {'name': 'AEGIS_MODEL_LOCATION', 'value': 'local'}],
                    'ports': [{'containerPort': 3000}],
                    'resources': {'requests': {'cpu': '150m', 'memory': '512Mi'}, 'limits': {'cpu': '1000m', 'memory': '1536Mi'}},
                    'securityContext': {'runAsUser': 1001, 'allowPrivilegeEscalation': False},
                    'readinessProbe': {'httpGet': {'path': '/', 'port': 3000}, 'periodSeconds': 15}},
                {'name': 'https', 'image': images['caddy_image'],
                    'ports': [{'containerPort': 80}, {'containerPort': 443}],
                    'volumeMounts': [{'name': 'https-state', 'mountPath': '/data'},
                        {'name': 'https-config', 'mountPath': '/etc/caddy', 'readOnly': True}],
                    'resources': {'requests': {'cpu': '50m', 'memory': '64Mi'}, 'limits': {'cpu': '250m', 'memory': '256Mi'}}}
            ]}}}))
    service = item('Service', 'aegis-public', spec={'type': 'LoadBalancer', 'selector': {'app': 'aegis-web'},
        'ports': [{'name': 'http', 'port': 80, 'targetPort': 80}, {'name': 'https', 'port': 443, 'targetPort': 443}]})
    service['metadata']['annotations'] = {
        'oci.oraclecloud.com/load-balancer-type': 'lb',
        'service.beta.kubernetes.io/oci-load-balancer-shape': 'flexible',
        'service.beta.kubernetes.io/oci-load-balancer-shape-flex-min': '10',
        'service.beta.kubernetes.io/oci-load-balancer-shape-flex-max': '10',
        'service.beta.kubernetes.io/oci-load-balancer-subnet1': state['lb_subnet'],
        'service.beta.kubernetes.io/oci-load-balancer-backend-protocol': 'TCP',
        'service.beta.kubernetes.io/oci-load-balancer-connection-idle-timeout': '1800',
        'service.beta.kubernetes.io/oci-load-balancer-security-list-management-mode': 'None',
    }
    resources.append(service)
    return {'apiVersion': 'v1', 'kind': 'List', 'items': resources}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=RUNTIME / 'resources.json')
    args = parser.parse_args()
    state = json.loads((RUNTIME / 'provision-state.json').read_text())
    release = json.loads((RUNTIME / 'release.json').read_text())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(render(state, release), indent=2), encoding='utf-8')
    print('Rendered only:', args.output)
