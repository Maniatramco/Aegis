"""OCI Cloud Shell release safety checks; no cloud commands are executed."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

cloud = load(ROOT/'ags_deploy/cloud_shell/cloud_shell_release.py', 'cloud_release_tests')
fixture = load(Path(__file__).with_name('test_release_cli.py'), 'cloud_release_fixtures')
cli = cloud.cli

class CloudRunner(fixture.FakeRunner):
    available = 160
    fail_push = None
    fail_rollout = None
    def capture(self, args, **kwargs):
        if args[0] == 'oci':
            self.calls.append(args)
            self.events.append('allowance')
            return json.dumps({'data': {'available': self.available}})
        if args[0] == 'podman':
            self.calls.append(args)
            if 'inspect' in args:
                return json.dumps([{'Os': 'linux', 'Architecture': 'arm64', 'Id': 'a'*64}])
            if '--get-login' in args: return 'private-login-not-printed'
            raise AssertionError(args)
        if '-n' in args:
            command = args[args.index('-n')+2:]
            if command[:2] == ['set', 'image']:
                self.calls.append(args)
                self.events.append('rollout')
                name = command[2].split('/')[1]
                for assignment in command[3:]:
                    container, image = assignment.split('=', 1)
                    self.before['deployments'][name]['images'][container] = image
                return ''
            if command[:2] == ['rollout', 'status'] and self.fail_rollout:
                raise cli.DeploymentStopped('simulated rollout failure')
        return super().capture(args, **kwargs)

    def interactive(self, args, **kwargs):
        if args[0] != 'podman': return super().interactive(args, **kwargs)
        self.calls.append(args)
        if 'build' in args:
            self.events.append('build')
        elif 'push' in args:
            component = 'frontend' if 'ags-aegis-web:' in args[-1] else 'backend'
            self.events.append('push:'+component)
            if component == self.fail_push: raise cli.DeploymentStopped('simulated push failure')
            Path(args[args.index('--digestfile')+1]).write_text('sha256:'+'b'*64)
        else: raise AssertionError(args)

class CloudShellTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ReleaseWorkflowTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.runner = CloudRunner(self.fixture.directory)
        self.runner.before = copy.deepcopy(self.fixture.runner.before)
        self.initial = copy.deepcopy(self.runner.before)
        def answer(prompt):
            value=self.fixture.answer(prompt)
            if value=='PUBLISH':self.runner.events.append('approval')
            return value
        self.workflow = cloud.CloudShellWorkflow(
            {'DB_Object':'N', 'AppUrl':'https://application.invalid', 'ValidationReference':'offline CI'},
            runner=self.runner, input_fn=answer)
        self.fixture.workflow = self.workflow
        original_stub = self.fixture.prepare_stub
        def prepare():
            original_stub()
            w = self.workflow
            w.tenancy='ocid1.tenancy.oc1..offline'
            w.machine='aarch64'
            w.storage={c:self.fixture.directory/c for c in ('frontend','backend')}
        self.workflow.prepare=prepare
        self.fixture.action='skip'
        self.addCleanup(patch.stopall)
        patch.dict(cloud.os.environ, {'OCI_REGION':'ap-mumbai-1'}).start()
        patch.object(cloud.shutil, 'disk_usage', return_value=SimpleNamespace(free=5*1024**3)).start()
        patch.object(cli.GUARD, 'collect', side_effect=lambda _:copy.deepcopy(self.runner.before)).start()
        patch.object(cli.urllib.request, 'urlopen', self.fixture.http).start()

    def run_release(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return self.workflow.run()

    def test_builds_before_publish_and_pushes_all_before_rollouts(self):
        result=self.run_release()
        self.assertEqual(result['state'],'complete')
        events=self.runner.events
        self.assertLess(events.index('build'),events.index('approval'))
        self.assertLess(events.index('approval'),events.index('push:frontend'))
        self.assertLess(events.index('push:backend'),events.index('rollout'))
        self.assertLess(events.index('push:frontend'),events.index('rollout'))
        receipt=json.loads(Path(result['receipt']).read_text())
        self.assertEqual(receipt['completed_rollouts'],['backend','frontend'])
        self.assertEqual(self.initial['resources'],self.runner.before['resources'])
        for args in self.runner.calls:
            self.assertNotIn('docker',args[:1])
            self.assertFalse(any(x in args for x in ('apply','scale','create-project','create-build-run')))

    def test_check_only_does_not_build_or_publish(self):
        self.workflow.check_only=True
        self.fixture.responses=['CONNECT']
        self.assertEqual(self.run_release()['state'],'preflight-only')
        self.assertFalse(any(x.startswith(('build','push','rollout')) for x in self.runner.events))

    def test_declining_connection_makes_no_remote_calls(self):
        self.fixture.responses=['NO']
        with self.assertRaises(cli.DeploymentStopped):self.run_release()
        self.assertEqual(self.runner.calls,[])

    def test_declining_publish_does_not_push_or_rollout(self):
        self.fixture.responses=['CONNECT','NO']
        with self.assertRaises(cli.DeploymentStopped):self.run_release()
        self.assertIn('build',self.runner.events)
        self.assertFalse(any(e.startswith(('push','rollout')) for e in self.runner.events))

    def test_no_free_allowance_stops_before_build(self):
        self.runner.available=0
        with self.assertRaisesRegex(cli.DeploymentStopped,'free Cloud Shell'):self.run_release()
        self.assertNotIn('build',self.runner.events)

    def test_wrong_native_architecture_stops(self):
        self.workflow.machine='x86_64'
        original=self.workflow.prepare
        def prepare():
            original()
            self.workflow.machine='x86_64'
        self.workflow.prepare=prepare
        with self.assertRaisesRegex(cli.DeploymentStopped,'architecture'):self.run_release()

    def test_low_disk_stops_without_allocating_storage(self):
        with patch.object(cloud.shutil,'disk_usage',return_value=SimpleNamespace(free=1)):
            with self.assertRaisesRegex(cli.DeploymentStopped,'space'):self.run_release()
        self.assertNotIn('build',self.runner.events)

    def test_disk_check_is_not_reapplied_to_occupied_build_stores(self):
        self.run_release()
        with patch.object(cloud.shutil,'disk_usage',return_value=SimpleNamespace(free=1)):
            self.workflow.metadata_preflight()

    def test_frontend_selection_preserves_backend_and_skips_db(self):
        self.workflow.backend=False
        self.workflow.components=['frontend']
        result=self.run_release()
        self.assertNotIn('schema-check',self.runner.events)
        self.assertEqual(self.initial['deployments']['aegis-api-worker'],self.runner.before['deployments']['aegis-api-worker'])
        self.assertIsNone(json.loads(Path(result['receipt']).read_text())['backend_image'])

    def test_backend_selection_preserves_frontend_and_live_flags(self):
        self.workflow.frontend=False
        self.workflow.components=['backend']
        self.run_release()
        self.assertEqual(self.initial['deployments']['aegis-web'],self.runner.before['deployments']['aegis-web'])
        build=next(a for a in self.runner.calls if a[0]=='podman' and 'build' in a)
        for value in ('INSTALL_ORACLE=true','INSTALL_OCI=true','INSTALL_CLOUD_MODELS=true','INSTALL_LOCAL_EMBEDDINGS=false'):
            self.assertIn(value,build)

    def test_failed_second_push_records_partial_publication_without_rollout(self):
        self.runner.fail_push='backend'
        with self.assertRaises(cli.DeploymentStopped):self.run_release()
        receipt=json.loads(Path(self.runner.last_receipt).read_text())
        self.assertEqual(receipt['published_components'],['frontend'])
        self.assertEqual(receipt['attempted_rollouts'],[])
        self.assertNotIn('rollout',self.runner.events)

    def test_failed_rollout_records_attempt_and_stops_later_component(self):
        self.runner.fail_rollout=True
        with self.assertRaises(cli.DeploymentStopped):self.run_release()
        receipt=json.loads(Path(self.runner.last_receipt).read_text())
        self.assertEqual(receipt['attempted_rollouts'],['backend'])
        self.assertEqual(receipt['completed_rollouts'],[])

    def test_outside_cloud_shell_stops_before_source_or_network(self):
        with patch.dict(cloud.os.environ,{},clear=True):
            with self.assertRaisesRegex(cli.DeploymentStopped,'inside OCI Cloud Shell'):
                cloud.CloudShellWorkflow({'DB_Object':'N'}).prepare()

    def test_publish_requires_approval_even_when_called_directly(self):
        with self.assertRaisesRegex(cli.DeploymentStopped,'PUBLISH'):
            self.workflow.release_images()

    def test_podman_runtime_path_respects_cloud_shell_length_limit(self):
        self.workflow.release='release-20261016-123456-abcdef'
        self.workflow.storage={'backend':Path('/home/very-long-username/Aegis/ags_deploy/deployment-records/release/backend')}
        args=self.workflow.podman('backend')
        self.assertLess(len(args[args.index('--runroot')+1]),50)
        self.assertIn('deployment-records',args[args.index('--root')+1])

if __name__=='__main__':unittest.main()
