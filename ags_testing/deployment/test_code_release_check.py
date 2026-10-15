"""Offline release-guard checks; no kubectl, Docker or database connections."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('code_release_check', ROOT/'ags_deploy/check-code-release.py')
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def deployment(name, containers):
    return {'metadata': {'name': name, 'uid': 'uid-'+name, 'generation': 2,
                         'annotations': {'deployment.kubernetes.io/revision': '1'}},
            'spec': {'replicas': 1, 'strategy': {'type': 'Recreate'},
                     'template': {'spec': {'containers': [{'name': value, 'image': 'old/'+value,
                         'env': [{'name': 'PROVIDER', 'value': 'retained-provider'}]} for value in containers],
                         'initContainers': [{'name': 'prepared-state', 'image': 'old/initializer'}]}}},
            'status': {'readyReplicas': 1, 'availableReplicas': 1, 'updatedReplicas': 1,
                       'observedGeneration': 2}}


def fixtures():
    deployments = [deployment('aegis-web', ['web', 'https']),
                   deployment('aegis-api-worker', ['api', 'worker', 'model-relay'])]
    resources = [{'kind': kind, 'metadata': {'name': kind.lower(), 'uid': 'uid-'+kind},
                  ('data' if kind in ('Secret', 'ConfigMap') else 'spec'): {'value': 'retained-private-value'}}
                 for kind in ('Secret', 'ConfigMap', 'Service', 'PersistentVolumeClaim')]
    runtime = {'profile': 'oci', 'runtime_file': 'a'*64,
               'saved_configuration': {'database.json': 'b'*64, 'settings.json': 'c'*64}}
    snapshot = {'format_version': 1, 'context': 'test-context', 'server': 'https://test.invalid',
                'namespace': 'test-namespace',
                'deployments': {item['metadata']['name']: guard.deployment_record(item) for item in deployments},
                'resources': guard.resource_records(resources),
                'runtime': {'api': copy.deepcopy(runtime), 'worker': copy.deepcopy(runtime)}}
    return deployments, resources, snapshot


def receipt_for(snapshot):
    return {key: snapshot[key] for key in ('context', 'server', 'namespace')} | {
        'previous': [{'deployment': name, 'containers': [{'name': container, 'image': image}
                      for container, image in item['images'].items()]}
                     for name, item in snapshot['deployments'].items()],
        'web_image': 'registry.invalid/example/web@sha256:'+'1'*64,
        'backend_image': 'registry.invalid/example/backend@sha256:'+'2'*64}


def released(deployments, baseline):
    receipt = receipt_for(baseline)
    after = copy.deepcopy(baseline)
    for item in copy.deepcopy(deployments):
        name = item['metadata']['name']
        item['metadata']['annotations']['deployment.kubernetes.io/revision'] = '2'
        item['metadata']['generation'] += 1
        item['status']['observedGeneration'] += 1
        for container in item['spec']['template']['spec']['containers']:
            if container['name'] in guard.APP_CONTAINERS[name]:
                container['image'] = receipt['web_image' if name == 'aegis-web' else 'backend_image']
        after['deployments'][name] = guard.deployment_record(item)
    return after, receipt


class ReleaseGuardTests(unittest.TestCase):
    def setUp(self):
        self.deployments, self.resources, self.before = fixtures()

    def test_unchanged_preflight_and_image_only_release_are_accepted(self):
        guard.compare(self.before, copy.deepcopy(self.before))
        after, receipt = released(self.deployments, self.before)
        guard.compare(self.before, after, receipt)

    def test_selected_component_release_preserves_every_unselected_image(self):
        for component, unchanged, unused_key in (('frontend', 'aegis-api-worker', 'backend_image'),
                                                  ('backend', 'aegis-web', 'web_image')):
            with self.subTest(component=component):
                after, receipt = released(self.deployments, self.before)
                after['deployments'][unchanged] = copy.deepcopy(self.before['deployments'][unchanged])
                receipt.update(components=[component])
                receipt[unused_key] = None
                guard.compare(self.before, after, receipt, components=[component])
                after['deployments'][unchanged]['images'][next(iter(guard.APP_CONTAINERS[unchanged]))] = 'unexpected/image'
                with self.assertRaisesRegex(guard.ReleaseCheckError, 'images differ'):
                    guard.compare(self.before, after, receipt, components=[component])

    def test_wrong_or_invalid_component_receipt_is_rejected(self):
        after, receipt = released(self.deployments, self.before)
        with self.assertRaisesRegex(guard.ReleaseCheckError, 'approved selection'):
            guard.compare(self.before, after, receipt, components=['frontend'])
        for invalid in ([], ['frontend', 'frontend'], ['unknown'], 'frontend'):
            with self.subTest(invalid=invalid), self.assertRaises(guard.ReleaseCheckError):
                guard.compare(self.before, after, receipt | {'components': invalid})

    def test_sidecar_or_init_container_image_changes_are_rejected(self):
        for category, container in (('containers', 'model-relay'), ('initContainers', 'prepared-state')):
            with self.subTest(category=category):
                modified = copy.deepcopy(self.deployments[1])
                for item in modified['spec']['template']['spec'][category]:
                    if item['name'] == container:
                        item['image'] = 'unexpected/image'
                after = copy.deepcopy(self.before)
                after['deployments']['aegis-api-worker'] = guard.deployment_record(modified)
                with self.assertRaisesRegex(guard.ReleaseCheckError, 'configuration or identity'):
                    guard.compare(self.before, after)

    def test_replica_strategy_environment_mount_and_resource_changes_are_rejected(self):
        mutations = [lambda spec: spec.update(replicas=2),
                     lambda spec: spec.update(strategy={'type': 'RollingUpdate'}),
                     lambda spec: spec['template']['spec']['containers'][0].update(env=[]),
                     lambda spec: spec['template']['spec'].update(volumes=[{'name': 'changed'}]),
                     lambda spec: spec['template']['spec']['containers'][0].update(resources={'limits': {'cpu': '4'}})]
        for mutate in mutations:
            changed = copy.deepcopy(self.deployments[0])
            mutate(changed['spec'])
            after = copy.deepcopy(self.before)
            after['deployments']['aegis-web'] = guard.deployment_record(changed)
            with self.assertRaises(guard.ReleaseCheckError):
                guard.compare(self.before, after)

    def test_secret_configmap_service_and_volume_changes_are_rejected_without_values(self):
        for index in range(len(self.resources)):
            changed = copy.deepcopy(self.resources)
            field = 'data' if changed[index]['kind'] in ('Secret', 'ConfigMap') else 'spec'
            changed[index][field]['value'] = 'different-private-value'
            after = copy.deepcopy(self.before)
            after['resources'] = guard.resource_records(changed)
            with self.assertRaisesRegex(guard.ReleaseCheckError, 'resources changed') as caught:
                guard.compare(self.before, after)
            self.assertNotIn('private-value', str(caught.exception))
        self.assertNotIn('retained-private-value', json.dumps(self.before))

    def test_saved_connection_or_active_runtime_changes_are_rejected(self):
        for field in ('saved_configuration', 'runtime_file', 'effective_environment'):
            after = copy.deepcopy(self.before)
            if field == 'saved_configuration':
                after['runtime']['api'][field]['database.json'] = 'd'*64
            else:
                after['runtime']['api'][field] = 'd'*64
            with self.assertRaisesRegex(guard.ReleaseCheckError, 'configuration changed'):
                guard.compare(self.before, after)

    def test_different_cluster_namespace_or_recreated_deployment_is_rejected(self):
        for field in ('context', 'server', 'namespace'):
            after = copy.deepcopy(self.before)
            after[field] = 'other-target'
            with self.assertRaisesRegex(guard.ReleaseCheckError, 'destination mismatch'):
                guard.compare(self.before, after)
        after = copy.deepcopy(self.before)
        after['deployments']['aegis-web']['uid'] = 'recreated-deployment'
        with self.assertRaisesRegex(guard.ReleaseCheckError, 'identity changed'):
            guard.compare(self.before, after)

    def test_receipt_must_match_destination_previous_images_and_immutable_digests(self):
        after, receipt = released(self.deployments, self.before)
        for mutation in (lambda r: r.update(server='https://other.invalid'),
                         lambda r: r['previous'][0]['containers'][0].update(image='wrong/previous'),
                         lambda r: r.update(web_image='mutable/image:latest')):
            bad = copy.deepcopy(receipt)
            mutation(bad)
            with self.assertRaises(guard.ReleaseCheckError):
                guard.compare(self.before, after, bad)

    def test_partial_rollout_and_unexpected_images_are_rejected(self):
        after, receipt = released(self.deployments, self.before)
        after['deployments']['aegis-api-worker']['images']['worker'] = 'old/worker'
        with self.assertRaisesRegex(guard.ReleaseCheckError, 'images differ'):
            guard.compare(self.before, after, receipt)
        complete, receipt = released(self.deployments, self.before)
        with self.assertRaisesRegex(guard.ReleaseCheckError, 'images differ'):
            guard.compare(self.before, complete)

    def test_unready_or_different_api_worker_configuration_is_rejected(self):
        after = copy.deepcopy(self.before)
        after['deployments']['aegis-web']['ready'] = False
        with self.assertRaisesRegex(guard.ReleaseCheckError, 'unready'):
            guard.compare(self.before, after)
        after = copy.deepcopy(self.before)
        after['runtime']['worker']['profile'] = 'different-profile'
        with self.assertRaisesRegex(guard.ReleaseCheckError, 'do not share'):
            guard.require_ready(after)

    def test_source_runtime_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root/'ags_backend/ags_app/ags_config/runtime.toml'
            target.parent.mkdir(parents=True)
            target.write_text('different-config', encoding='utf-8')
            with self.assertRaisesRegex(guard.ReleaseCheckError, 'runtime.toml differs'):
                guard.validate_source(self.before, root)

    def test_api_errors_do_not_echo_configuration(self):
        options = SimpleNamespace(kubeconfig=Path('test-config'), context='test-context', namespace='test-namespace')
        response = subprocess.CompletedProcess([], 1, b'', b'private-secret-content')
        with patch.object(guard.subprocess, 'run', return_value=response):
            with self.assertRaises(guard.ReleaseCheckError) as caught:
                guard.kubectl_json(options, ['get', 'deployment', '-o', 'json'])
        self.assertNotIn('private-secret-content', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
