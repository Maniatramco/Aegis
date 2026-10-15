"""Offline command-line release checks. All OCI, Docker and SQLcl calls are stubbed."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('release_cli', ROOT/'ags_deploy/release_cli.py')
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)
helpers = cli.module_from(Path(__file__).with_name('test_code_release_check.py'), 'guard_fixtures')


def schema_fixture():
    return json.loads((Path(__file__).parent/'fixtures/oci-schema.json').read_text(encoding='utf-8'))


class FakeRunner:
    """Emulates prepared resources, built images, schema client and release receipt."""
    last_receipt = None

    def __init__(self, directory):
        self.directory = directory
        self.events = []
        self.calls = []
        self.deployments, self.resources, self.before = helpers.fixtures()
        for item in self.deployments:
            for container in item['spec']['template']['spec']['containers']:
                container['image'] = 'registry.invalid/test/'+container['name']+':old'
        self.before['deployments'] = {item['metadata']['name']: cli.GUARD.deployment_record(item) for item in self.deployments}
        self.after, self.receipt = helpers.released(self.deployments, self.before)
        self.published = False
        self.database = schema_fixture()
        self.fail_install = False
        self.fail_release = False

    def capture(self, arguments, **kwargs):
        self.calls.append(arguments)
        if arguments[0] == 'docker':
            return json.dumps([{'Os': 'linux', 'Architecture': 'arm64', 'Id': 'sha256:local'}])
        command = arguments[arguments.index('-n')+2:]
        self.events.append('read:'+command[0])
        if command[:2] == ['get', 'deployment']:
            return json.dumps({'items': self.deployments})
        if command[:2] == ['get', cli.GUARD.CONFIG_RESOURCES]:
            return json.dumps({'items': self.resources})
        if command[:2] == ['get', 'nodes']:
            return json.dumps({'items': [{'metadata': {'labels': {'kubernetes.io/os': 'linux', 'kubernetes.io/arch': 'arm64'}},
                                         'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}}]})
        if command[0] == 'exec':
            self.events.append('schema-check')
            return json.dumps(self.database)
        if command[:2] == ['rollout', 'status']:
            return ''
        raise AssertionError('Unexpected external command: '+repr(arguments))

    def interactive(self, arguments, **kwargs):
        self.calls.append(arguments)
        if arguments[0] == 'docker':
            self.events.append('build')
            return
        script = Path(arguments[arguments.index('-File')+1])
        if script.name.startswith('empty-owner-'):
            sql = script.with_suffix('.sql').read_text(encoding='utf-8')
            log = Path(re.search(r'SPOOL "([^"]+)"', sql)[1])
            marker = re.search(r"PUT_LINE\('([^']+)'\)", sql)[1]
            self.events.append('empty-owner-check')
            log.write_text(marker+'\n', encoding='utf-8')
        elif '-CheckOnly' in arguments:
            self.events.append('local-wallet-check')
        else:
            self.events.append('install')
            if self.fail_install:
                raise cli.DeploymentStopped('Simulated partial schema failure')

    def stream(self, arguments, **kwargs):
        self.calls.append(arguments)
        self.events.append('publish')
        if '-Components' in arguments:
            component = arguments[arguments.index('-Components')+1].lower()
            self.receipt['components'] = [component]
            for name, item in self.before['deployments'].items():
                if ('frontend' if name == 'aegis-web' else 'backend') != component:
                    self.after['deployments'][name] = copy.deepcopy(item)
            self.receipt['backend_image' if component == 'frontend' else 'web_image'] = None
        script = Path(arguments[arguments.index('-File')+1])
        destination = script.parent/'deployment-records/this-invocation.json'
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(json.dumps(self.receipt), encoding='utf-8')
        self.last_receipt = str(destination)
        if self.fail_release:
            raise cli.DeploymentStopped('Simulated partial release')
        self.published = True
        return destination


class ReleaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = self.directory/'source'
        shutil.copytree(ROOT/'ags_database', self.source/'ags_database')
        config = self.source/'ags_backend/ags_app/ags_config'
        config.mkdir(parents=True)
        shutil.copyfile(ROOT/'ags_backend/ags_app/ags_config/runtime.toml', config/'runtime.toml')
        (self.source/'ags_frontend').mkdir()
        (self.source/'ags_deploy').mkdir()
        (self.source/'ags_deploy/deploy-aegis-code.ps1').write_text('test-helper', encoding='utf-8')
        self.runner = FakeRunner(self.directory)
        digest = cli.hashlib.sha256((config/'runtime.toml').read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        for snapshot in (self.runner.before, self.runner.after):
            for runtime in snapshot['runtime'].values():
                runtime['runtime_file'] = digest
        self.responses = ['CONNECT', 'PUBLISH']
        self.workflow = cli.Workflow({'AppUrl': 'https://application.invalid', 'BackupReference': 'existing restore point',
                                     'ValidationReference': 'offline test CI reference'}, runner=self.runner,
                                    input_fn=self.answer)
        self.workflow.prepare = self.prepare_stub
        self.addCleanup(patch.stopall)
        patch.object(cli.GUARD, 'collect', side_effect=lambda options: copy.deepcopy(self.runner.after if self.runner.published else self.runner.before)).start()
        self.http = patch.object(cli.urllib.request, 'urlopen').start()
        self.http.return_value.__enter__.return_value.status = 200
        self.action = 'verify'

    def answer(self, prompt):
        answer = self.responses.pop(0)
        if answer == 'PUBLISH':
            self.runner.events.append('approval')
        return answer

    def prepare_stub(self):
        work = self.workflow
        work.source = self.source
        work.directory = self.directory
        work.source_hash = cli.source_fingerprint(self.source)
        work.commit = 'a'*40
        work.release = 'offline-release'
        work.powershell = 'powershell'
        work.action = self.action
        configuration = self.directory/'offline-kubeconfig.yaml'
        configuration.write_text('offline fixture', encoding='utf-8')
        work.options = SimpleNamespace(kubeconfig=configuration, context='test-context', namespace='test-namespace')
        work.kubeconfig_hash = cli.hashlib.sha256(configuration.read_bytes()).hexdigest()
        work.record.update(context='test-context', namespace='test-namespace', server='https://test.invalid', source_commit=work.commit)
        work.wallet = self.directory/'not-opened.zip'
        work.db_owner = 'TEST_OWNER'
        work.alias = 'test_low'
        work.service = 'test_low.adb.oraclecloud.com'
        work.sqlcl = 'not-executed-sqlcl'
        work.database_args = []

    def run_quietly(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return self.workflow.run()

    def test_verify_release_builds_before_approval_and_binds_receipt(self):
        result = self.run_quietly()
        self.assertEqual(result['state'], 'complete')
        self.assertEqual(self.runner.events.count('build'), 2)
        self.assertLess(self.runner.events.index('build'), self.runner.events.index('approval'))
        self.assertLess(self.runner.events.index('approval'), self.runner.events.index('publish'))
        self.assertNotIn('install', self.runner.events)
        self.assertEqual(json.loads(Path(result['receipt']).read_text()), self.runner.receipt)
        self.assertEqual(self.runner.before['resources'], self.runner.after['resources'])
        self.assertEqual(result['backup_reference'], 'existing restore point')

    def test_release_without_backup_reference_still_requires_publication_approval(self):
        self.workflow.values.pop('BackupReference')
        result = self.run_quietly()
        self.assertEqual(result['state'], 'complete')
        self.assertIsNone(result['backup_reference'])
        self.assertEqual(self.responses, [])
        self.assertLess(self.runner.events.index('approval'), self.runner.events.index('publish'))

    def test_blank_backup_reference_does_not_prompt_or_claim_a_backup(self):
        self.workflow.values['BackupReference'] = '   '
        result = self.run_quietly()
        self.assertEqual(result['state'], 'complete')
        self.assertIsNone(result['backup_reference'])
        self.assertEqual(self.responses, [])

    def select(self, frontend, backend, action):
        self.workflow.frontend = frontend
        self.workflow.backend = backend
        self.workflow.components = [name for name, chosen in (('frontend', frontend), ('backend', backend)) if chosen]
        self.action = action

    def test_frontend_only_skips_oracle_and_keeps_backend_images(self):
        self.select(True, False, 'skip')
        result = self.run_quietly()
        self.assertEqual(result['state'], 'complete')
        self.assertEqual(self.runner.events.count('build'), 1)
        self.assertNotIn('schema-check', self.runner.events)
        self.assertEqual(self.runner.after['deployments']['aegis-api-worker'], self.runner.before['deployments']['aegis-api-worker'])
        self.assertEqual(self.runner.receipt['components'], ['frontend'])

    def test_backend_only_checks_database_compatibility_without_ddl_or_frontend_release(self):
        self.select(False, True, 'skip')
        self.run_quietly()
        self.assertEqual(self.runner.events.count('build'), 1)
        self.assertIn('schema-check', self.runner.events)
        self.assertNotIn('install', self.runner.events)
        self.assertEqual(self.runner.after['deployments']['aegis-web'], self.runner.before['deployments']['aegis-web'])
        build = next(call for call in self.runner.calls if call[:2] == ['docker', 'build'])
        self.assertIn('INSTALL_CLOUD_MODELS=true', build)
        self.assertIn('INSTALL_LOCAL_EMBEDDINGS=false', build)
        self.assertIn('INSTALL_ORACLE=true', build)

    def test_database_verify_only_builds_nothing_and_needs_no_publish_approval(self):
        self.select(False, False, 'verify')
        self.responses = ['CONNECT']
        result = self.run_quietly()
        self.assertEqual(result['state'], 'verified-only')
        self.assertIn('schema-check', self.runner.events)
        self.assertFalse({'build', 'install', 'publish', 'approval'} & set(self.runner.events))
        self.http.assert_not_called()

    def test_database_only_install_does_not_require_kubernetes_or_docker(self):
        self.select(False, False, 'install')
        work = self.workflow
        work.prepare = cli.Workflow.prepare.__get__(work)
        wallet = self.directory/'wallet.zip'
        wallet.write_text('synthetic; client stub handles the local-only package check')
        work.values.update(SourcePath=str(self.source), DatabaseAction='install', WalletPath=str(wallet),
                           DatabaseOwner='TEST_OWNER', ServiceAlias='test_low', ExpectedService='test_low.adb.oraclecloud.com')
        with patch.object(cli, 'export_commit', return_value=(self.source, 'a'*40)), \
             patch.object(cli.shutil, 'which', side_effect=lambda name: str(self.directory/'sql.cmd') if name == 'sql' else 'powershell'):
            result = self.run_quietly()
        self.assertEqual(result['state'], 'complete')
        self.assertTrue(result['database_installed'])
        self.assertFalse(any(call[0] in ('kubectl', 'docker') for call in self.runner.calls))
        self.assertFalse({'build', 'publish', 'schema-check'} & set(self.runner.events))
        self.http.assert_not_called()

    def test_frontend_only_does_not_validate_unselected_backend_source_toml(self):
        self.select(True, False, 'skip')
        (self.source/'ags_backend/ags_app/ags_config/runtime.toml').write_text('unselected backend source differs')
        self.assertEqual(self.run_quietly()['state'], 'complete')

    def test_fresh_schema_can_be_combined_with_frontend_only(self):
        self.select(True, False, 'install')
        result = self.run_quietly()
        self.assertTrue(result['database_installed'])
        self.assertEqual(self.runner.events.count('build'), 1)
        self.assertEqual(self.runner.after['deployments']['aegis-api-worker'], self.runner.before['deployments']['aegis-api-worker'])

    def test_fresh_schema_can_be_combined_with_backend_only(self):
        self.select(False, True, 'install')
        result = self.run_quietly()
        self.assertTrue(result['database_installed'])
        self.assertEqual(self.runner.events.count('build'), 1)
        self.assertEqual(self.runner.after['deployments']['aegis-web'], self.runner.before['deployments']['aegis-web'])

    def test_database_only_check_only_does_not_install_or_contact_cluster(self):
        self.select(False, False, 'install')
        self.workflow.check_only = True
        self.responses = ['CONNECT']
        result = self.run_quietly()
        self.assertEqual(result['state'], 'preflight-only')
        self.assertIn('empty-owner-check', self.runner.events)
        self.assertFalse({'build', 'install', 'publish', 'approval'} & set(self.runner.events))
        self.assertFalse(any(call[0] in ('kubectl', 'docker') for call in self.runner.calls))

    def release_file_manager(self, populated=False):
        fixtures = cli.module_from(Path(__file__).with_name('test_oracle_release.py'), 'oracle_test_fixtures')
        database = fixtures.Database(exists=True, populated=populated)
        release = cli.ORACLE_RELEASE.ReleaseFile(self.source,self.source/'ags_database/release.json')
        manager = object.__new__(cli.ORACLE_RELEASE.DatabaseRelease)
        manager.schema, manager.release = cli.SCHEMA, release
        manager.owner, manager.admin = 'TEST_OWNER','ADMIN'
        manager.alias, manager.service = 'test_low','test_low.adb.oraclecloud.com'
        manager.tablespace, manager.quota = 'DATA',256
        manager.password_fn = lambda prompt: fixtures.SECRET
        manager.passwords, manager.connections, manager.applied = {},{},[]
        manager.driver, manager.wallet_dir = database,self.directory
        manager.temporary = SimpleNamespace(cleanup=lambda:None)
        self.workflow.db_release = manager
        return database

    def test_release_file_check_only_and_denied_approval_never_create_objects(self):
        self.select(False,False,'release')
        database = self.release_file_manager()
        self.workflow.check_only = True
        self.responses = ['CONNECT']
        self.assertEqual(self.run_quietly()['state'],'preflight-only')
        self.assertEqual(database.writes,[])
        self.assertFalse(self.runner.calls)

    def test_release_file_denied_publish_never_creates_objects(self):
        self.select(False,False,'release')
        database = self.release_file_manager()
        self.responses = ['CONNECT','no']
        with self.assertRaises(cli.DeploymentStopped):
            self.run_quietly()
        self.assertEqual(database.writes,[])
        self.assertFalse(self.runner.calls)

    def test_y_flag_preparation_does_not_connect_before_permission(self):
        self.workflow.prepare = cli.Workflow.prepare.__get__(self.workflow)
        wallet = self.directory/'wallet.zip'
        wallet.write_text('constructor is stubbed; this is never opened')
        self.workflow.values.update(SourcePath=str(self.source),DB_Object='Y',DB_ReleaseFile='ags_database/release.json',
                                    DeployFrontend='N',DeployBackend='N',WalletPath=str(wallet),DatabaseOwner='TEST_OWNER',
                                    ServiceAlias='test_low',ExpectedService='test_low.adb.oraclecloud.com')
        self.workflow.frontend,self.workflow.backend,self.workflow.components=False,False,[]
        self.responses=['no']
        with patch.object(cli,'export_commit',return_value=(self.source,'a'*40)), \
             patch.object(cli.ORACLE_RELEASE,'DatabaseRelease') as manager:
            manager.return_value.admin='ADMIN'
            manager.return_value.applied=[]
            with self.assertRaises(cli.DeploymentStopped):
                self.run_quietly()
            manager.return_value.discover.assert_not_called()
            manager.return_value.apply.assert_not_called()
            manager.return_value.close.assert_called_once()

    def test_release_file_database_only_executes_its_scripts_without_images(self):
        self.select(False,False,'release')
        database = self.release_file_manager()
        result = self.run_quietly()
        self.assertEqual(result['state'],'complete')
        self.assertEqual(len(database.writes),33)
        self.assertEqual(len(result['database_completed_objects']),33)
        self.assertFalse(self.runner.calls)
        self.http.assert_not_called()

    def test_release_file_with_matching_objects_does_not_ask_to_publish_database_only(self):
        self.select(False,False,'release')
        database = self.release_file_manager(populated=True)
        self.responses = ['CONNECT']
        self.assertEqual(self.run_quietly()['state'],'verified-only')
        self.assertEqual(database.writes,[])

    def test_existing_schema_missing_index_release_needs_no_backup_reference(self):
        self.select(False, False, 'release')
        self.workflow.values.pop('BackupReference')
        database = self.release_file_manager(populated=True)
        table = next(item for item in database.tables if item['name'] == 'AEGIS_ITEMS')
        index = next(item['name'] for item in table['indexes'] if item['name'].startswith('IX_'))
        table['indexes'] = [item for item in table['indexes'] if item['name'] != index]
        table['index_columns'] = [item for item in table['index_columns'] if item['index'] != index]
        existing_data = copy.deepcopy(database.data)
        result = self.run_quietly()
        self.assertEqual(result['state'], 'complete')
        self.assertIsNone(result['backup_reference'])
        self.assertEqual(len(database.writes), 1)
        self.assertTrue(database.writes[0].startswith('CREATE INDEX'))
        self.assertEqual(database.data, existing_data)
        self.assertEqual(self.responses, [])
        self.assertFalse(self.runner.calls)

    def test_release_file_applies_objects_then_releases_selected_backend(self):
        self.select(False,True,'release')
        database = self.release_file_manager()
        result = self.run_quietly()
        self.assertEqual(result['state'],'complete')
        self.assertEqual(len(database.writes),33)
        self.assertEqual(self.runner.events.count('build'),1)
        self.assertEqual(self.runner.after['deployments']['aegis-web'],self.runner.before['deployments']['aegis-web'])

    def test_connection_denial_does_not_contact_target(self):
        self.responses = ['no']
        with self.assertRaises(cli.DeploymentStopped):
            self.run_quietly()
        self.assertEqual(self.runner.events, [])

    def test_check_only_never_builds_or_publishes(self):
        self.workflow.check_only = True
        result = self.run_quietly()
        self.assertEqual(result['state'], 'preflight-only')
        self.assertFalse({'build', 'install', 'publish', 'approval'} & set(self.runner.events))
        self.http.assert_not_called()

    def test_fresh_owner_check_only_never_creates_tables(self):
        self.action = 'install'
        self.workflow.check_only = True
        result = self.run_quietly()
        self.assertEqual(result['state'], 'preflight-only')
        self.assertIn('empty-owner-check', self.runner.events)
        self.assertFalse({'build', 'install', 'publish', 'approval'} & set(self.runner.events))

    def test_publication_denial_stops_before_any_mutation(self):
        self.workflow.values.pop('BackupReference')
        self.responses = ['CONNECT', 'no']
        with self.assertRaises(cli.DeploymentStopped):
            self.run_quietly()
        self.assertNotIn('publish', self.runner.events)
        self.assertNotIn('install', self.runner.events)

    def test_active_jobs_or_wrong_database_stop_before_build(self):
        for values in ({'active_jobs': 1}, {'owner': 'OTHER_OWNER'}):
            with self.subTest(values=values):
                self.responses = ['CONNECT']
                self.runner.events.clear()
                self.runner.database = schema_fixture() | values
                self.workflow.values['DatabaseOwner'] = 'TEST_OWNER'
                with self.assertRaises(cli.DeploymentStopped):
                    self.run_quietly()
                self.assertNotIn('build', self.runner.events)

    def test_source_or_image_drift_after_approval_stops_release(self):
        original = self.workflow.approve_publication
        def approve_and_change():
            original()
            (self.source/'ags_frontend/changed').write_text('changed', encoding='utf-8')
        self.workflow.approve_publication = approve_and_change
        with self.assertRaisesRegex(cli.DeploymentStopped, 'changed'):
            self.run_quietly()
        self.assertNotIn('publish', self.runner.events)

    def test_kubeconfig_drift_after_approval_stops_before_target_access(self):
        original = self.workflow.approve_publication
        def approve_and_change():
            original()
            self.workflow.options.kubeconfig.write_text('different destination')
        self.workflow.approve_publication = approve_and_change
        with self.assertRaisesRegex(cli.DeploymentStopped, 'Kubeconfig changed'):
            self.run_quietly()
        self.assertNotIn('publish', self.runner.events)

    def test_approved_image_id_drift_stops_before_publish(self):
        original = self.workflow.approve_publication
        def approve_and_change():
            original()
            self.workflow.inspect_image_ids = lambda: {'unexpected-image': 'different-id'}
        self.workflow.approve_publication = approve_and_change
        with self.assertRaisesRegex(cli.DeploymentStopped, 'images changed'):
            self.run_quietly()
        self.assertNotIn('publish', self.runner.events)

    def test_fresh_install_is_approved_then_verified_before_publish(self):
        self.action = 'install'
        result = self.run_quietly()
        self.assertTrue(result['database_installed'])
        for first, second in (('approval', 'install'), ('install', 'schema-check'), ('schema-check', 'publish')):
            self.assertLess(self.runner.events.index(first), self.runner.events.index(second))
        self.assertEqual(self.runner.events.count('empty-owner-check'), 2)

    def test_partial_schema_failure_records_risk_and_does_not_publish(self):
        self.action = 'install'
        self.runner.fail_install = True
        with self.assertRaises(cli.DeploymentStopped):
            self.run_quietly()
        result = json.loads((self.directory/'result.json').read_text())
        self.assertTrue(result['database_install_attempted'])
        self.assertFalse(result['database_installed'])
        self.assertEqual(result['state'], 'stopped')
        self.assertNotIn('publish', self.runner.events)

    def test_wrong_saved_connection_after_schema_does_not_publish(self):
        self.action = 'install'
        self.runner.database['owner'] = 'OTHER_OWNER'
        with self.assertRaisesRegex(cli.DeploymentStopped, 'does not point'):
            self.run_quietly()
        self.assertTrue(self.workflow.record['database_installed'])
        self.assertNotIn('publish', self.runner.events)

    def test_partial_release_preserves_exact_receipt_and_stops(self):
        self.runner.fail_release = True
        with self.assertRaises(cli.DeploymentStopped):
            self.run_quietly()
        result = json.loads((self.directory/'result.json').read_text())
        self.assertEqual(result['reported_receipt'], self.runner.last_receipt)
        self.assertEqual(result['state'], 'stopped')
        self.http.assert_not_called()

    def test_https_failure_does_not_claim_complete(self):
        self.http.return_value.__enter__.return_value.status = 503
        with self.assertRaises(cli.DeploymentStopped):
            self.run_quietly()
        self.assertTrue(self.runner.published)
        self.assertEqual(self.workflow.record['state'], 'stopped')


class InputAndSchemaTests(unittest.TestCase):
    def test_y_n_flags_select_components_and_reject_ambiguous_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'target.json'
            path.write_text('{"DB_Object":"N","DB_ReleaseFile":"ags_database/release.json","DeployFrontend":"Y","DeployBackend":"N"}')
            workflow=cli.Workflow(cli.load_inputs(path))
            self.assertEqual(workflow.components,['frontend'])
            for invalid in ('yes','true','0',''):
                with self.assertRaises(cli.DeploymentStopped):
                    cli.flag(invalid,'DB_Object')
            self.assertFalse(cli.flag('N','DB_Object'))
            self.assertTrue(cli.flag('Y','DB_Object'))

    def test_component_flags_require_real_booleans_and_noop_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'inputs.json'
            for invalid in ('"false"', '0', 'null'):
                path.write_text('{"DeployFrontend":'+invalid+'}')
                with self.assertRaises(cli.DeploymentStopped):
                    cli.load_inputs(path)
            path.write_text('{"DeployFrontend":false,"DeployBackend":true,"DatabaseAction":"skip"}')
            values = cli.load_inputs(path)
            self.assertFalse(values['DeployFrontend'])
            self.assertTrue(values['DeployBackend'])
        with self.assertRaisesRegex(cli.DeploymentStopped, 'Nothing selected'):
            cli.Workflow({'DeployFrontend':False,'DeployBackend':False,'DatabaseAction':'skip'}).prepare()

    def test_remote_database_probe_runs_read_only_without_application_imports_or_secret_output(self):
        fixture = schema_fixture()
        queries = []
        rolled_back = []
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, sql, **parameters):
                queries.append(sql)
                table = next((item for item in fixture['tables'] if item['name'] == parameters.get('name')), None)
                if sql == 'SET TRANSACTION READ ONLY': self.rows = []
                elif sql.startswith('SELECT USER,'): self.rows = [(fixture['owner'], fixture['service_name'])]
                elif 'FROM user_tables' in sql: self.rows = [(name,) for name in fixture['present_tables']]
                elif 'FROM user_tab_columns' in sql:
                    self.rows = [tuple(item[key] for key in ('name','type','data_length','char_length','char_used','precision','scale','nullable','default','collation')) for item in table['columns']]
                elif 'FROM user_constraints' in sql:
                    self.rows = [tuple(item[key] for key in ('name','type','references','delete_rule','status','condition','validated')) for item in table['constraints']]
                elif 'FROM user_cons_columns' in sql:
                    self.rows = [tuple(item[key] for key in ('constraint','column','position')) for item in table['constraint_columns']]
                elif 'FROM user_indexes' in sql:
                    self.rows = [tuple(item[key] for key in ('name','unique','type','status')) for item in table['indexes']]
                elif 'FROM user_ind_columns' in sql:
                    self.rows = [tuple(item[key] for key in ('index','column','position')) for item in table['index_columns']]
                elif 'DBMS_METADATA.GET_DDL' in sql: self.rows = [(table['ddl'],)]
                elif 'COUNT(*) FROM JOB_TBL' in sql: self.rows = [(42,)]
                elif sql.startswith('SELECT VECTOR_DISTANCE'): self.rows = [(0,)]
                else: raise AssertionError('Unexpected or mutating SQL: '+sql)
            def fetchall(self): return self.rows
            def fetchone(self): return self.rows[0]
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def cursor(self): return Cursor()
            def rollback(self): rolled_back.append(True)
        private_password = 'synthetic-private-password'
        cipher = SimpleNamespace(decrypt=lambda value: json.dumps({'password': private_password, 'wallet_password': 'synthetic-wallet-secret'}).encode())
        fake_oracle = SimpleNamespace(connect=lambda **kwargs: Connection())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'configuration').mkdir()
            (root/'secrets').mkdir()
            (root/'secrets/db.json').write_text('{"encrypted":"synthetic-ciphertext"}')
            (root/'configuration/database.json').write_text(json.dumps({'active_provider':'oci','active_connection':
                {'secret_ref':'secrets/db.json','username':fixture['owner'],'dsn':fixture['wallet_alias'],'auth_mode':'mtls','wallet_directory':'/synthetic/wallet'}}))
            output = io.StringIO()
            with patch.dict(os.environ, AEGIS_STORAGE_ROOT=str(root), AEGIS_MASTER_KEY='synthetic-key'), contextlib.redirect_stdout(output), \
                 patch.dict(sys.modules, {'oracledb':fake_oracle, 'cryptography':SimpleNamespace(),
                                         'cryptography.fernet':SimpleNamespace(Fernet=lambda key:cipher)}):
                exec(compile(cli.SCHEMA.inspection_script(ROOT), '<offline-oracle-probe>', 'exec'), {})
            metadata = json.loads(output.getvalue())
        self.assertEqual(metadata['active_jobs'], 42)
        self.assertEqual(queries[0], 'SET TRANSACTION READ ONLY')
        self.assertTrue(all(sql.startswith('SELECT ') for sql in queries[1:]))
        self.assertEqual(rolled_back, [True])
        self.assertNotIn(private_password, output.getvalue())
        self.assertEqual(cli.SCHEMA.verify_schema(ROOT, metadata)['columns'], 165)

    def test_unknown_or_secret_input_fields_are_rejected_and_paths_are_relative(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'inputs.json'
            path.write_text('{"Password":"never-used"}')
            with self.assertRaises(cli.DeploymentStopped):
                cli.load_inputs(path)
            path.write_text('{"Kubeconfig":"target.yaml","DatabaseAction":"verify"}')
            self.assertEqual(cli.load_inputs(path)['Kubeconfig'], str(Path(temporary)/'target.yaml'))

    def test_unapproved_direct_calls_are_blocked(self):
        workflow = cli.Workflow({})
        for action in (lambda: workflow.kubectl(['get', 'pods']), workflow.snapshot,
                       lambda: workflow.verify_empty_owner(1), workflow.install_database, workflow.release_images):
            with self.assertRaisesRegex(cli.DeploymentStopped, 'approval'):
                action()

    def test_historical_schema_fixture_matches_current_oci_scripts(self):
        self.assertEqual(cli.SCHEMA.verify_schema(ROOT, schema_fixture()),
                         {'tables': 13, 'columns': 165, 'foreign_keys': 49, 'indexes': 20})

    def test_column_foreign_key_index_and_constraint_drift_is_rejected(self):
        mutations = [lambda table: table['columns'][0].update(char_length=999),
                     lambda table: table['columns'][0].update(collation='BINARY'),
                     lambda table: table['columns'][0].update(default="'unexpected'"),
                     lambda table: table['constraints'].pop(),
                     lambda table: table['constraints'][0].update(validated='NOT VALIDATED'),
                     lambda table: table['indexes'][0].update(status='UNUSABLE'),
                     lambda table: next(item for item in table['index_columns'] if item['index'].startswith('IX_')).update(column='WRONG_COLUMN')]
        for mutate in mutations:
            fixture = schema_fixture()
            mutate(fixture['tables'][0])
            with self.subTest(mutation=mutate), self.assertRaises(cli.SCHEMA.SchemaMismatch):
                cli.SCHEMA.verify_schema(ROOT, fixture)

    def test_check_literals_and_vector_format_are_case_sensitive_where_required(self):
        fixture = schema_fixture()
        table = next(t for t in fixture['tables'] if t['name'] == 'USER_TBL')
        check = next(c for c in table['constraints'] if c['name'] == 'CK_USER_ROLE')
        check['condition'] = check['condition'].replace("'user'", "'USER'")
        with self.assertRaises(cli.SCHEMA.SchemaMismatch):
            cli.SCHEMA.verify_schema(ROOT, fixture)
        fixture = schema_fixture()
        next(t for t in fixture['tables'] if t['name'] == 'AEGIS_KNOWLEDGE_VECTORS')['ddl'] = '"EMBEDDING" VECTOR(1536, FLOAT64)'
        with self.assertRaises(cli.SCHEMA.SchemaMismatch):
            cli.SCHEMA.verify_schema(ROOT, fixture)

    def test_mixed_node_architecture_requires_existing_placement(self):
        def node(arch):
            return {'metadata': {'labels': {'kubernetes.io/os': 'linux', 'kubernetes.io/arch': arch}},
                    'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}}
        deployments = helpers.fixtures()[0]
        with self.assertRaises(cli.DeploymentStopped):
            cli.infer_platform([node('arm64'), node('amd64')], deployments, 'linux/arm64')
        for item in deployments:
            item['spec']['template']['spec']['nodeSelector'] = {'kubernetes.io/arch': 'arm64'}
        self.assertEqual(cli.infer_platform([node('arm64'), node('amd64')], deployments, 'linux/arm64'), 'linux/arm64')

    def test_stream_requires_one_exact_receipt_and_keeps_it_on_failure(self):
        for output, code, expected in [('Previous images and destination saved: exact.json', 0, 'exact.json'),
                                       ('nothing', 0, None), ('Previous images and destination saved: partial.json', 1, None)]:
            runner = cli.Runner()
            with contextlib.redirect_stdout(io.StringIO()):
                command = [sys.executable, '-B', '-c', f'print({output!r});raise SystemExit({code})']
                if expected:
                    self.assertEqual(runner.stream(command), Path(expected))
                else:
                    with self.assertRaises(cli.DeploymentStopped):
                        runner.stream(command)
            if code:
                self.assertEqual(runner.last_receipt, 'partial.json')

    def test_commit_export_excludes_uncommitted_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository = base/'repository'
            repository.mkdir()
            for relative in ('ags_frontend/Dockerfile', 'ags_backend/Dockerfile', 'ags_database/install.sql',
                             'ags_database/deploy-oci-database.ps1', 'ags_deploy/deploy-aegis-code.ps1'):
                path = repository/relative
                path.parent.mkdir(exist_ok=True)
                path.write_text('committed', encoding='utf-8')
            runner = cli.Runner()
            for arguments in (['init'], ['add', '.'], ['-c', 'user.name=Offline test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture']):
                runner.capture(['git', '-C', str(repository), *arguments])
            (repository/'ags_frontend/Dockerfile').write_text('uncommitted')
            (repository/'untracked-secret').write_text('must not enter archive')
            source, commit = cli.export_commit(repository, 'HEAD', base, runner)
            self.assertEqual((source/'ags_frontend/Dockerfile').read_text(), 'committed')
            self.assertFalse((source/'untracked-secret').exists())
            self.assertEqual(len(commit), 40)

    @unittest.skipUnless(os.name == 'nt' and shutil.which('powershell'), 'Windows launcher smoke test')
    def test_real_powershell_launcher_denied_connection_uses_only_local_kubeconfig(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository = base/'repository'
            repository.mkdir()
            for relative in ('ags_frontend/Dockerfile', 'ags_backend/Dockerfile', 'ags_database/install.sql',
                             'ags_database/deploy-oci-database.ps1', 'ags_deploy/deploy-aegis-code.ps1'):
                path = repository/relative
                path.parent.mkdir(exist_ok=True)
                path.write_text('committed fixture', encoding='utf-8')
            runner = cli.Runner()
            for arguments in (['init'], ['add', '.'], ['-c', 'user.name=Offline test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture']):
                runner.capture(['git', '-C', str(repository), *arguments])
            configuration = base/'kubeconfig.yaml'
            configuration.write_text('fixture; stub kubectl handles local config only')
            inputs = base/'inputs.json'
            inputs.write_text(json.dumps({'SourcePath': str(repository), 'Ref': 'HEAD',
                                          'Kubeconfig': str(configuration), 'DatabaseAction': 'verify'}))
            stub = base/'stub.py'
            stub.write_text('import sys,json,subprocess,runpy\nfrom unittest.mock import patch\noriginal_run=subprocess.run\n'
                            'def fake_run(arguments,**kwargs):\n'
                            ' if arguments[0]!="kubectl":return original_run(arguments,**kwargs)\n'
                            ' assert arguments[1:]==["--kubeconfig",'+repr(str(configuration))+',"config","view","-o","json"],"Remote access attempted"\n'
                            ' data={"contexts":[{"name":"offline","context":{"cluster":"fake"}}],"clusters":[{"name":"fake","cluster":{"server":"https://offline.invalid"}}]}\n'
                            ' return subprocess.CompletedProcess(arguments,0,json.dumps(data),"")\n'
                            'assert sys.argv[1:4]==["-B","-X","utf8"]\nsys.argv=sys.argv[4:]\n'
                            'with patch("subprocess.run",fake_run):runpy.run_path(sys.argv[0],run_name="__main__")\n')
            fake_python = base/'fake-python.cmd'
            fake_python.write_text('@"'+sys.executable+'" -B -X utf8 "'+str(stub)+'" %*\r\n')
            result = subprocess.run([shutil.which('powershell'), '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                     '-File', str(ROOT/'ags_deploy/deploy.ps1'), '-Inputs', str(inputs), '-Python', str(fake_python)],
                                    input='no\n', capture_output=True, text=True, timeout=40,
                                    env=dict(os.environ, PATH=str(base)+os.pathsep+os.environ['PATH']))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Type CONNECT', result.stdout, result.stderr)
            self.assertIn('Not approved', result.stderr)
            self.assertNotIn('Remote access attempted', result.stderr)
            records = list((repository/'ags_deploy/deployment-records').glob('*/result.json'))
            self.assertEqual(len(records), 1)
            self.assertEqual(json.loads(records[0].read_text())['state'], 'stopped')

    @unittest.skipUnless(os.name == 'nt' and shutil.which('powershell'), 'Windows release-helper simulation')
    def test_real_release_helper_builds_pushes_and_updates_only_selected_components(self):
        for selection in ('All', 'Frontend', 'Backend'):
            with self.subTest(selection=selection), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                source = base/'source'
                for component in ('ags_frontend', 'ags_backend'):
                    (source/component).mkdir(parents=True)
                    (source/component/'Dockerfile').write_text('synthetic build context')
                helper = base/'deploy-aegis-code.ps1'
                shutil.copyfile(ROOT/'ags_deploy/deploy-aegis-code.ps1', helper)
                deployments = base/'deployments.json'
                deployments.write_text(json.dumps({'items':helpers.fixtures()[0]}))
                kubeconfig = base/'kubeconfig.yaml'
                kubeconfig.write_text('synthetic; kubectl function handles all calls')
                log = base/'calls.jsonl'
                harness = base/'simulate.ps1'
                harness.write_text("$ErrorActionPreference='Stop'\n$global:LASTEXITCODE=0\n"+
                    '$global:callLog='+cli.ps_literal(log)+'\n$global:deploymentFixture='+cli.ps_literal(deployments)+'''\n
function global:docker {
    $global:LASTEXITCODE=0
    $arguments=@($args)
    @{tool='docker';arguments=$arguments} | ConvertTo-Json -Compress | Add-Content -LiteralPath $global:callLog
    if ($arguments[0] -eq 'image') {
        if ($arguments[-1] -eq '{{.Os}}/{{.Architecture}}') { 'linux/arm64' }
        else {
            $image=$arguments[2]
            $repository=$image.Substring(0,$image.LastIndexOf(':'))
            ConvertTo-Json -InputObject @($repository+'@sha256:'+('a'*64)) -Compress
        }
    } elseif ($arguments[0] -notin @('build','push')) { throw 'Unexpected Docker command' }
}
function global:kubectl {
    $global:LASTEXITCODE=0
    $arguments=@($args)
    @{tool='kubectl';arguments=$arguments} | ConvertTo-Json -Compress | Add-Content -LiteralPath $global:callLog
    if ($arguments -contains 'config') {
        '{"contexts":[{"name":"test-context"}],"clusters":[{"cluster":{"server":"https://test.invalid"}}]}'
    } elseif ($arguments -contains 'get') { Get-Content -LiteralPath $global:deploymentFixture -Raw }
    elseif ($arguments -notcontains 'set' -and $arguments -notcontains 'rollout') { throw 'Unexpected kubectl command' }
}
'''+'\n& '+cli.ps_literal(helper)+' -SourcePath '+cli.ps_literal(source)+' -Kubeconfig '+cli.ps_literal(kubeconfig)+
                    ' -Context test-context -Namespace test-namespace -Registry registry.invalid -RegistryNamespace test -Platform linux/arm64 -Release offline-release -Components '+selection+'\n', encoding='utf-8-sig')
                result = subprocess.run([shutil.which('powershell'), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(harness)],
                                        capture_output=True, text=True, timeout=40)
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = [json.loads(line) for line in log.read_text(encoding='utf-8-sig').splitlines()]
                chosen = {'frontend', 'backend'} if selection == 'All' else {selection.lower()}
                for verb in ('build', 'push'):
                    matching = [call['arguments'] for call in calls if call['tool']=='docker' and call['arguments'][0]==verb]
                    self.assertEqual(len(matching), len(chosen))
                    for arguments in matching:
                        component = 'frontend' if any('ags-aegis-web:' in value for value in arguments) else 'backend'
                        self.assertIn(component, chosen)
                        if verb == 'build' and component == 'backend':
                            self.assertIn('INSTALL_CLOUD_MODELS=true', arguments)
                            self.assertIn('INSTALL_LOCAL_EMBEDDINGS=false', arguments)
                            self.assertIn('INSTALL_ORACLE=true', arguments)
                updates = [call['arguments'] for call in calls if call['tool']=='kubectl' and 'set' in call['arguments']]
                self.assertEqual(len(updates), len(chosen))
                for arguments in updates:
                    component = 'frontend' if 'deployment/aegis-web' in arguments else 'backend'
                    self.assertIn(component, chosen)
                receipt = json.loads(next((base/'deployment-records').glob('*.json')).read_text(encoding='utf-8-sig'))
                self.assertEqual(set(receipt['components']), chosen)
                for component, key in (('frontend','web_image'), ('backend','backend_image')):
                    self.assertEqual(receipt[key] is not None, component in chosen)


if __name__ == '__main__':
    unittest.main()
