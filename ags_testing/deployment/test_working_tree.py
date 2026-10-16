"""Saved local source snapshots: real Git fixtures, no Docker or OCI calls."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('working_tree_cli', ROOT/'ags_deploy/scripts/release_cli.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class WorkingTreeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='aegis saved source ')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repository = self.base/'repository with spaces'
        self.repository.mkdir()
        self.runner = cli.Runner()
        for relative in ('ags_frontend/Dockerfile','ags_backend/Dockerfile','ags_database/install.sql',
                         'ags_database/deploy-oci-database.ps1','ags_deploy/scripts/deploy-aegis-code.ps1',
                         'ags_frontend/deleted.ts','ags_frontend/staged.ts'):
            self.write(relative,'committed')
        self.write('.gitignore','node_modules/\n.env*\nags_runtime/\nags_deploy/deployment-records/\nignored.ts\n')
        for args in (['init'],['add','.'],['-c','user.name=Offline test','-c','user.email=test@example.invalid','commit','-m','fixture']):
            self.runner.capture(['git','-C',str(self.repository),*args])
        self.commit = self.runner.capture(['git','-C',str(self.repository),'rev-parse','HEAD']).strip()

    def write(self, relative, text):
        path=self.repository/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding='utf-8')
        return path

    def export(self, name):
        directory=self.base/name
        directory.mkdir()
        return cli.export_working_tree(self.repository,directory,self.runner),directory

    def test_snapshot_uses_saved_edits_new_files_and_deletions_without_commit(self):
        self.write('ags_frontend/Dockerfile','saved after commit')
        self.write('ags_frontend/new route.ts','new saved source')
        self.write('ags_frontend/staged.ts','staged version')
        self.runner.capture(['git','-C',str(self.repository),'add','ags_frontend/staged.ts'])
        self.write('ags_frontend/staged.ts','saved after staging')
        (self.repository/'ags_frontend/deleted.ts').unlink()
        status=self.runner.capture(['git','-C',str(self.repository),'status','--porcelain'])
        (source,commit),directory=self.export('run-one')
        self.assertEqual(commit,self.commit)
        self.assertEqual((source/'ags_frontend/Dockerfile').read_text(),'saved after commit')
        self.assertEqual((source/'ags_frontend/new route.ts').read_text(),'new saved source')
        self.assertEqual((source/'ags_frontend/staged.ts').read_text(),'saved after staging')
        self.assertFalse((source/'ags_frontend/deleted.ts').exists())
        self.assertEqual(status,self.runner.capture(['git','-C',str(self.repository),'status','--porcelain']))
        manifest=json.loads((directory/'source-manifest.json').read_text())
        self.assertEqual(manifest['mode'],'working-tree')
        self.assertIn('ags_frontend/new route.ts',manifest['files'])
        self.write('ags_frontend/new route.ts','next saved version')
        self.assertEqual((source/'ags_frontend/new route.ts').read_text(),'new saved source')
        (second,_),_=self.export('run-two')
        self.assertEqual((second/'ags_frontend/new route.ts').read_text(),'next saved version')
        self.assertNotEqual(cli.source_fingerprint(source),cli.source_fingerprint(second))

    def test_snapshot_excludes_ignored_private_generated_and_unrelated_files(self):
        for name in ('ags_frontend/.env.local','ags_frontend/node_modules/package/index.js',
                     'ags_frontend/ignored.ts','ags_deploy/aegis-oci-inputs.json',
                     'ags_runtime/private-state.json','delete/retired.py','outside-source.txt'):
            self.write(name,'not a build input')
        # Even an accidentally tracked key or generated file must be excluded.
        for name in ('ags_backend/private.key','ags_database/Wallet_target.zip','ags_frontend/.next/generated.js'):
            self.write(name,'private/generated')
            self.runner.capture(['git','-C',str(self.repository),'add','--force',name])
        (source,_),_=self.export('safe-run')
        self.assertFalse(any('private/generated' in path.read_text() or 'not a build input' in path.read_text()
                             for path in source.rglob('*') if path.is_file()))
        self.assertTrue((source/'ags_frontend/Dockerfile').is_file())

    def test_deleted_required_file_stops_instead_of_falling_back_to_old_commit(self):
        (self.repository/'ags_backend/Dockerfile').unlink()
        with self.assertRaisesRegex(cli.DeploymentStopped,'lacks required'):
            self.export('missing-run')

    def test_source_change_during_copy_stops_without_remote_calls(self):
        original=cli.local_source_inventory
        calls=[]
        def mutate(root,runner):
            calls.append(True)
            if len(calls)==2: self.write('ags_frontend/new file.ts','changed during snapshot')
            return original(root,runner)
        with patch.object(cli,'local_source_inventory',side_effect=mutate):
            with self.assertRaisesRegex(cli.DeploymentStopped,'changed while creating'):
                self.export('changed-run')

    def test_symlink_to_private_file_is_rejected(self):
        secret=self.base/'private.txt'
        secret.write_text('never copy this')
        link=self.repository/'ags_frontend/linked.ts'
        try: link.symlink_to(secret)
        except OSError: self.skipTest('Symlink creation is unavailable without Windows developer/admin mode')
        with self.assertRaisesRegex(cli.DeploymentStopped,'symbolic link'):
            self.export('linked-run')

    def test_workflow_selects_local_snapshot_and_labels_base_commit(self):
        self.write('ags_frontend/Dockerfile','current saved source')
        # Stop at the first local kubeconfig operation, before remote inspection.
        class LocalOnly(cli.Runner):
            def capture(self, arguments, **kwargs):
                if arguments[0]=='kubectl': raise cli.DeploymentStopped('OFFLINE-LOCAL-STOP')
                return super().capture(arguments,**kwargs)
        values={'SourcePath':str(self.repository),'Ref':'old-ref-that-does-not-exist',
                'DB_Object':'N','DeployFrontend':'Y','DeployBackend':'Y','Kubeconfig':str(self.write('client.yaml','offline'))}
        work=cli.Workflow(values,runner=LocalOnly(),working_tree=True)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(cli.DeploymentStopped,'OFFLINE-LOCAL-STOP'):
            work.prepare()
        self.assertEqual(work.record['source_mode'],'working-tree')
        self.assertEqual(work.record['source_commit'],self.commit)
        self.assertEqual((work.source/'ags_frontend/Dockerfile').read_text(),'current saved source')
        self.assertTrue(Path(work.record['source_manifest']).is_file())


if __name__=='__main__': unittest.main()