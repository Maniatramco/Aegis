"""Read-only before/after checks for image-only releases to prepared Aegis OKE.

Uses existing kubectl access. Records hashes rather than configuration or secret
values, and never applies Kubernetes resources or imports the application.
"""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


APP_CONTAINERS = {'aegis-web': {'web'}, 'aegis-api-worker': {'api', 'worker'}}
CONFIG_RESOURCES = 'configmaps,secrets,services,persistentvolumeclaims'
RUNTIME_INSPECTION = """import hashlib,json,os
from pathlib import Path
config=Path(os.environ.get('AEGIS_CONFIG_FILE','/app/ags_app/ags_config/runtime.toml'))
root=Path(os.environ.get('AEGIS_STORAGE_ROOT','/data'))
hash_file=lambda p:hashlib.sha256(p.read_bytes().replace(b'\\r\\n',b'\\n')).hexdigest()
state={}
for name in ('database.json','settings.json'):
    path=root/'configuration'/name
    if not path.is_file():raise RuntimeError('Prepared application configuration is missing')
    state[name]=hash_file(path)
prefixes=('AEGIS_','DATABASE_','ORACLE_','OCI_','MODEL_','EMBEDDING_','OPENAI_',
          'QUEUE_','SEARCH_','QDRANT_','AWS_','AZURE_','GOOGLE_','LANGSMITH_')
names={'MASTER_KEY','DATA_DIR','ALLOWED_ORIGINS','COOKIE_SECURE','HF_HOME','API_INTERNAL_URL'}
effective={name:value for name,value in os.environ.items() if name.startswith(prefixes) or name in names}
environment_hash=hashlib.sha256(json.dumps(effective,sort_keys=True).encode()).hexdigest()
print(json.dumps({'profile':os.environ.get('AEGIS_CONFIG_PROFILE'),
    'runtime_file':hash_file(config),'saved_configuration':state,'effective_environment':environment_hash}))
"""


class ReleaseCheckError(RuntimeError):
    pass


def fingerprint(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def metadata_configuration(item):
    metadata = item.get('metadata', {})
    annotations = dict(metadata.get('annotations', {}))
    annotations.pop('deployment.kubernetes.io/revision', None)
    return {'labels': metadata.get('labels', {}), 'annotations': annotations}


def deployment_record(item):
    name = item['metadata']['name']
    if name not in APP_CONTAINERS:
        raise ReleaseCheckError('Unexpected deployment in release inspection')
    spec = copy.deepcopy(item['spec'])
    containers = spec['template']['spec']['containers']
    images = {container['name']: container['image'] for container in containers}
    if len(images) != len(containers) or not APP_CONTAINERS[name] <= images.keys():
        raise ReleaseCheckError(f'{name}: required application containers are missing or duplicated')
    for container in containers:
        if container['name'] in APP_CONTAINERS[name]:
            container['image'] = '<application-image>'
    desired = item['spec'].get('replicas', 1)
    status = item.get('status', {})
    ready = desired > 0 and status.get('readyReplicas', 0) == desired
    ready = ready and status.get('availableReplicas', 0) == desired
    ready = ready and status.get('updatedReplicas', 0) == desired
    ready = ready and status.get('observedGeneration', 0) >= item['metadata'].get('generation', 0)
    return {'uid': item['metadata']['uid'], 'images': images, 'ready': ready,
            'configuration_sha256': fingerprint({'metadata': metadata_configuration(item), 'spec': spec})}


def resource_records(items):
    result = {}
    for item in items:
        key = item['kind'] + '/' + item['metadata']['name']
        # Status and API bookkeeping can change during a normal pod rollout.
        configuration = {field: item[field] for field in ('spec', 'data', 'binaryData', 'type', 'immutable') if field in item}
        configuration['metadata'] = metadata_configuration(item)
        result[key] = {'uid': item['metadata']['uid'], 'configuration_sha256': fingerprint(configuration)}
    return result


def kubectl_json(options, arguments):
    command = ['kubectl', '--kubeconfig', str(options.kubeconfig), '--context', options.context,
               '--request-timeout=25s', '-n', options.namespace, *arguments]
    completed = subprocess.run(command, capture_output=True, timeout=45)
    if completed.returncode:
        # kubectl output can contain destination configuration. Do not echo it.
        raise ReleaseCheckError('Read-only kubectl inspection failed; check existing access and readiness')
    try:
        return json.loads(completed.stdout)
    except (ValueError, UnicodeError) as error:
        raise ReleaseCheckError('kubectl inspection did not return valid JSON') from error


def collect(options):
    destination = kubectl_json(options, ['config', 'view', '--minify', '-o', 'json'])
    contexts = destination.get('contexts', [])
    clusters = destination.get('clusters', [])
    if len(contexts) != 1 or contexts[0]['name'] != options.context or len(clusters) != 1:
        raise ReleaseCheckError('The explicit Kubernetes context did not resolve uniquely')
    deployments = kubectl_json(options, ['get', 'deployment', *APP_CONTAINERS, '-o', 'json'])
    records = {item['metadata']['name']: deployment_record(item) for item in deployments.get('items', [])}
    if set(records) != set(APP_CONTAINERS):
        raise ReleaseCheckError('Both existing Aegis deployments are required')
    resources = kubectl_json(options, ['get', CONFIG_RESOURCES, '-o', 'json'])
    runtime = {}
    for container in ('api', 'worker'):
        runtime[container] = kubectl_json(options, ['exec', 'deployment/aegis-api-worker', '-c', container,
                                                  '--', 'python', '-B', '-c', RUNTIME_INSPECTION])
    return {'format_version': 1, 'checked_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'context': options.context, 'server': clusters[0]['cluster']['server'],
            'namespace': options.namespace, 'deployments': records,
            'resources': resource_records(resources.get('items', [])), 'runtime': runtime}


def require_ready(snapshot):
    if not all(record['ready'] for record in snapshot['deployments'].values()):
        raise ReleaseCheckError('An Aegis deployment is paused, unready or still rolling out; inspect before proceeding')
    if snapshot['runtime']['api'] != snapshot['runtime']['worker']:
        raise ReleaseCheckError('API and worker do not share the same runtime and saved configuration')


def validate_source(snapshot, source_path):
    source_config = source_path / 'ags_backend/ags_app/ags_config/runtime.toml'
    digest = hashlib.sha256(source_config.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    if any(record['runtime_file'] != digest for record in snapshot['runtime'].values()):
        raise ReleaseCheckError('Source runtime.toml differs from the active configuration; this code-only release cannot change it')


def compare(baseline, current, receipt=None, components=None):
    for key in ('format_version', 'context', 'server', 'namespace'):
        if baseline.get(key) != current.get(key):
            raise ReleaseCheckError(f'Release destination mismatch: {key}')
    if baseline['resources'] != current['resources']:
        changed = sorted(key for key in baseline['resources'].keys() | current['resources'].keys()
                         if baseline['resources'].get(key) != current['resources'].get(key))
        raise ReleaseCheckError('Configuration resources changed: ' + ', '.join(changed))
    if baseline['runtime'] != current['runtime']:
        raise ReleaseCheckError('Runtime file or saved database/storage configuration changed')
    expected_images = {name: dict(record['images']) for name, record in baseline['deployments'].items()}
    if receipt is not None:
        for key in ('context', 'server', 'namespace'):
            if receipt.get(key) != baseline[key]:
                raise ReleaseCheckError(f'Receipt destination mismatch: {key}')
        previous = {item['deployment']: {c['name']: c['image'] for c in item['containers']}
                    for item in receipt['previous']}
        if previous != expected_images:
            raise ReleaseCheckError('Receipt previous images differ from the checked baseline')
        selected = receipt.get('components', ['frontend', 'backend'])
        if (not isinstance(selected, list) or not selected or
                any(item not in ('frontend', 'backend') for item in selected) or len(set(selected)) != len(selected)):
            raise ReleaseCheckError('Receipt has invalid application components')
        if components is not None and set(selected) != set(components):
            raise ReleaseCheckError('Receipt components differ from the approved selection')
        for component, key in (('frontend', 'web_image'), ('backend', 'backend_image')):
            if component in selected:
                if not re.fullmatch(r'[^\s]+@sha256:[a-f0-9]{64}', receipt.get(key) or ''):
                    raise ReleaseCheckError('Receipt must contain immutable image digests')
            elif receipt.get(key) is not None:
                raise ReleaseCheckError('Receipt includes an image for an unselected component')
        if 'frontend' in selected:
            expected_images['aegis-web']['web'] = receipt['web_image']
        if 'backend' in selected:
            for container in ('api', 'worker'):
                expected_images['aegis-api-worker'][container] = receipt['backend_image']
    if set(baseline['deployments']) != set(current['deployments']):
        raise ReleaseCheckError('The inspected deployment set changed')
    for name, before in baseline['deployments'].items():
        after = current['deployments'][name]
        if before['uid'] != after['uid'] or before['configuration_sha256'] != after['configuration_sha256']:
            raise ReleaseCheckError(f'{name}: deployment configuration or identity changed')
        if after['images'] != expected_images[name]:
            raise ReleaseCheckError(f'{name}: images differ from the expected release')
    require_ready(current)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('snapshot', 'verify'))
    parser.add_argument('--source-path', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--kubeconfig', type=Path, required=True)
    parser.add_argument('--context', required=True)
    parser.add_argument('--namespace', default='aegis-oci')
    parser.add_argument('--output', type=Path, help='New baseline JSON file; use the ignored deployment-records folder')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--receipt', type=Path, help='Exact receipt printed by deploy-aegis-code.ps1')
    options = parser.parse_args()
    if options.mode == 'snapshot' and (options.output is None or options.baseline or options.receipt):
        parser.error('snapshot requires --output and does not accept --baseline/--receipt')
    if options.mode == 'verify' and (options.baseline is None or options.output):
        parser.error('verify requires --baseline and does not accept --output')
    if options.output and options.output.exists():
        parser.error('Baseline already exists; choose a new filename')
    options.kubeconfig = options.kubeconfig.resolve(strict=True)
    snapshot = collect(options)
    require_ready(snapshot)
    validate_source(snapshot, options.source_path.resolve(strict=True))
    if options.mode == 'snapshot':
        options.output.parent.mkdir(parents=True, exist_ok=True)
        with options.output.open('x', encoding='utf-8') as target:
            json.dump(snapshot, target, indent=2)
        print('Read-only baseline saved:', options.output)
    else:
        baseline = json.loads(options.baseline.read_text(encoding='utf-8-sig'))
        receipt = json.loads(options.receipt.read_text(encoding='utf-8-sig')) if options.receipt else None
        compare(baseline, snapshot, receipt)
        print('PASS: destination, configuration and expected images verified; both deployments are ready.')
    print('No cluster resources, database rows or application settings were changed by this check.')


if __name__ == '__main__':
    try:
        main()
    except (ReleaseCheckError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print('Release check stopped:', error, file=sys.stderr)
        raise SystemExit(1)
