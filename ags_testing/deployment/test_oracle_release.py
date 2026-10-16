"""Offline Oracle object-release simulation. No real driver or OCI connection."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
from types import SimpleNamespace
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('release_cli', ROOT/'ags_deploy/scripts/release_cli.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
oracle = cli.ORACLE_RELEASE
FIXTURE = json.loads((Path(__file__).parent/'fixtures/oci-schema.json').read_text())
SECRET = 'SyntheticPrivatePassword_123'


class Database:
    def __init__(self, exists=True, populated=False):
        self.exists = exists
        self.tables = copy.deepcopy(FIXTURE['tables']) if populated else []
        self.calls, self.writes = [], []
        self.data = {'existing-data': 'must stay unchanged'}
        self.fail_object = None
        self.current_schema = None
        self.service = FIXTURE['service_name']

    def connect(self, **kwargs):
        if kwargs['user'] == 'TEST_OWNER' and not self.exists:
            raise AssertionError('Connected to absent owner')
        return Connection(self, kwargs['user'])


class Connection:
    def __init__(self, database, username):
        self.database, self.username, self.readonly = database, username, False
    def cursor(self): return Cursor(self)
    def rollback(self): self.readonly = False
    def close(self): pass


class Cursor:
    def __init__(self, connection): self.connection = connection
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None
    def execute(self, sql, **parameters):
        db, user = self.connection.database, self.connection.username
        db.calls.append(sql)
        self.rows = []
        table = next((item for item in db.tables if item['name'] == parameters.get('name')), None)
        if sql == 'SET TRANSACTION READ ONLY': self.connection.readonly = True
        elif sql.startswith('SELECT USER,'): self.rows = [(user, db.service)]
        elif sql.startswith("SELECT SYS_CONTEXT('USERENV','CURRENT_SCHEMA')"): self.rows = [(db.current_schema or user,)]
        elif sql.startswith('SELECT username,oracle_maintained'): self.rows = [('TEST_OWNER','N',42)] if db.exists else []
        elif sql == 'SELECT privilege FROM session_privs':
            self.rows = [(item,) for item in (['CREATE USER','GRANT ANY PRIVILEGE','UNLIMITED TABLESPACE'] if user=='ADMIN' else ['CREATE SESSION','CREATE TABLE'])]
        elif sql.startswith('SELECT privilege FROM user_sys_privs'): self.rows = [('CREATE SESSION',),('CREATE TABLE',)]
        elif sql.startswith('SELECT tablespace_name FROM user_tablespaces'): self.rows = [('DATA',)]
        elif sql.startswith('SELECT default_tablespace FROM user_users'): self.rows = [('DATA',)]
        elif sql.startswith('SELECT COUNT(*) FROM user_ts_quotas'): self.rows = [(1,)]
        elif sql.startswith('SELECT LENGTH(') or sql.startswith('SELECT CASE WHEN CAST(TRUE'): self.rows = [(1,)]
        elif sql.startswith('SELECT VECTOR_DISTANCE'): self.rows = [(0,)]
        elif 'FROM user_tables' in sql: self.rows = [(item['name'],) for item in db.tables]
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
        elif 'COUNT(*) FROM JOB_TBL' in sql: self.rows = [(0,)]
        elif sql.startswith('SELECT object_name,object_type FROM user_objects'):
            self.rows = [(item['name'],'TABLE') for item in db.tables]+[(index['name'],'INDEX') for item in db.tables for index in item['indexes']]
        elif sql.startswith(('CREATE ', 'GRANT ')):
            if self.connection.readonly:
                raise AssertionError('DDL attempted while read-only transaction is active')
            if db.fail_object and db.fail_object in sql:
                raise RuntimeError(SECRET)
            db.writes.append(sql)
            if sql.startswith('CREATE USER '):
                if db.exists: raise AssertionError('Existing user was recreated')
                db.exists = True
            elif sql.startswith('GRANT '):
                if not any(item.startswith('CREATE USER ') for item in db.writes): raise AssertionError('Existing grants were modified')
            elif sql.startswith('CREATE TABLE '):
                name = re.match(r'CREATE TABLE "([A-Z0-9_]+)"',sql)[1]
                if any(item['name']==name for item in db.tables): raise AssertionError('Existing table was recreated')
                definition = copy.deepcopy(next(item for item in FIXTURE['tables'] if item['name']==name))
                definition['indexes'] = [item for item in definition['indexes'] if not item['name'].startswith('IX_')]
                definition['index_columns'] = [item for item in definition['index_columns'] if not item['index'].startswith('IX_')]
                db.tables.append(definition)
            elif sql.startswith('CREATE INDEX '):
                match = re.match(r'CREATE INDEX "([A-Z0-9_]+)" ON "([A-Z0-9_]+)"', sql)
                definition = next(item for item in FIXTURE['tables'] if item['name']==match[2])
                target = next(item for item in db.tables if item['name']==match[2])
                target['indexes'].append(copy.deepcopy(next(item for item in definition['indexes'] if item['name']==match[1])))
                target['index_columns'] += copy.deepcopy([item for item in definition['index_columns'] if item['index']==match[1]])
            else: raise AssertionError('Unexpected mutation')
        else: raise AssertionError('Unexpected SQL: '+sql)


class OracleReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)/'source'
        shutil.copytree(ROOT/'ags_database', self.source/'ags_database')
        self.manifest_path = self.source/'ags_database/release.json'
        self.manifest = oracle.ReleaseFile(self.source, self.manifest_path)

    def manager(self, database):
        manager = object.__new__(oracle.DatabaseRelease)
        manager.schema, manager.release = cli.SCHEMA, self.manifest
        manager.owner, manager.admin = 'TEST_OWNER', 'ADMIN'
        manager.alias, manager.service = FIXTURE['wallet_alias'], FIXTURE['service_name']
        manager.tablespace, manager.quota = 'DATA', 256
        manager.password_fn = lambda prompt: SECRET
        manager.passwords = {}
        manager.connections = {}
        manager.driver = database
        manager.wallet_dir = Path('/unused-offline-wallet')
        manager.applied = []
        return manager

    def test_default_release_has_exact_order_and_33_objects(self):
        self.assertEqual(len(self.manifest.scripts),13)
        self.assertEqual(len(self.manifest.statements),33)
        self.assertLess(self.manifest.scripts.index('ags_database/ags_tables/12_user_dataset_tbl.sql'),
                        self.manifest.scripts.index('ags_database/ags_tables/09_extract_tbl.sql'))

    def test_wallet_constructor_is_local_only_and_checks_archive_paths(self):
        database=Database()
        wallet=Path(self.temp.name)/'wallet.zip'
        with zipfile.ZipFile(wallet,'w') as package:
            package.writestr('tnsnames.ora','test_low = (DESCRIPTION=(CONNECT_DATA=(SERVICE_NAME=test_low.adb.oraclecloud.com)))')
            package.writestr('ewallet.pem','synthetic fixture')
        manager=oracle.DatabaseRelease(cli.SCHEMA,self.manifest,wallet,'TEST_OWNER','test_low',FIXTURE['service_name'],
                                       password_fn=lambda prompt:SECRET,driver=database)
        self.assertEqual(database.calls,[])
        try:
            self.assertEqual(len(manager.discover()['actions']),33)
        finally:
            manager.close()
        with zipfile.ZipFile(wallet,'w') as package:
            package.writestr('../outside.pem','must not extract')
        with self.assertRaises(oracle.OracleReleaseError):
            oracle.DatabaseRelease(cli.SCHEMA,self.manifest,wallet,'TEST_OWNER','test_low',FIXTURE['service_name'],driver=database)

    def test_absent_schema_and_objects_created_only_after_approval(self):
        database = Database(exists=False)
        manager = self.manager(database)
        reviewed = manager.discover()
        self.assertTrue(reviewed['summary']['create_schema'])
        self.assertEqual(database.writes, [])
        with self.assertRaisesRegex(oracle.OracleReleaseError, 'approval'):
            manager.apply(reviewed, False, lambda phase:None)
        result = manager.apply(reviewed, True, lambda phase:None)
        self.assertEqual(len(database.writes),35)  # user + minimum grants + 13 tables + 20 indexes
        self.assertTrue(result['listed_objects_verified'])
        self.assertNotIn(SECRET,json.dumps(result)+json.dumps(reviewed))
        self.assertEqual(database.data, {'existing-data':'must stay unchanged'})
        self.assertEqual(manager.discover()['actions'], [])

    def test_matching_schema_is_read_only_and_idempotent(self):
        database = Database(populated=True)
        manager = self.manager(database)
        reviewed = manager.discover()
        self.assertEqual(reviewed['actions'], [])
        objects=reviewed['snapshot']['metadata']['objects']
        self.assertEqual(objects,sorted(objects,key=lambda item:(item['name'],item['type'])))
        self.assertFalse(reviewed['summary']['create_schema'])
        manager.apply(reviewed,True,lambda phase:None)
        self.assertEqual(database.writes, [])

    def test_missing_index_only_is_created_existing_tables_and_grants_preserved(self):
        database = Database(populated=True)
        table = next(item for item in database.tables if item['name']=='AEGIS_ITEMS')
        index = next(item['name'] for item in table['indexes'] if item['name'].startswith('IX_'))
        table['indexes'] = [item for item in table['indexes'] if item['name']!=index]
        table['index_columns'] = [item for item in table['index_columns'] if item['index']!=index]
        manager = self.manager(database)
        reviewed = manager.discover()
        self.assertEqual([item['name'] for item in reviewed['actions']],[index])
        manager.apply(reviewed,True,lambda phase:None)
        self.assertEqual(len(database.writes),1)
        self.assertTrue(database.writes[0].startswith('CREATE INDEX'))

    def test_manifest_selects_only_listed_script(self):
        content = json.loads(self.manifest_path.read_text())
        content['Scripts'] = ['ags_database/ags_tables/01_user_tbl.sql']
        self.manifest_path.write_text(json.dumps(content))
        self.manifest = oracle.ReleaseFile(self.source,self.manifest_path)
        database = Database()
        manager = self.manager(database)
        manager.apply(manager.discover(),True,lambda phase:None)
        self.assertEqual([item['name'] for item in database.tables],['USER_TBL'])
        self.assertEqual(len(database.writes),1)

    def test_incompatible_existing_table_stops_before_any_ddl(self):
        database = Database(populated=True)
        database.tables[0]['columns'][0]['char_length']=999
        with self.assertRaises(cli.SCHEMA.SchemaMismatch):
            self.manager(database).discover()
        self.assertEqual(database.writes,[])

    def test_wrong_service_stops_before_any_ddl(self):
        database = Database()
        database.service = 'wrong.service'
        with self.assertRaisesRegex(oracle.OracleReleaseError,'service'):
            self.manager(database).discover()
        self.assertEqual(database.writes,[])

    def test_wrong_current_schema_stops_before_any_object_ddl(self):
        database=Database()
        database.current_schema='OTHER_OWNER'
        with self.assertRaisesRegex(oracle.OracleReleaseError,'current schema'):
            self.manager(database).discover()
        self.assertEqual(database.writes,[])

    def test_partial_failure_is_reported_without_password_or_auto_rollback(self):
        database = Database(exists=False)
        manager = self.manager(database)
        reviewed = manager.discover()
        database.fail_object = '"AEGIS_ITEMS"'
        with self.assertRaises(oracle.OracleReleaseError) as caught:
            manager.apply(reviewed,True,lambda phase:None)
        self.assertNotIn(SECRET,str(caught.exception))
        self.assertTrue(database.exists)
        self.assertEqual([item['name'] for item in database.tables],['USER_TBL'])
        self.assertEqual([item['kind'] for item in manager.applied],['USER','TABLE'])

    def test_changed_source_or_target_invalidates_approval(self):
        database = Database()
        manager = self.manager(database)
        reviewed = manager.discover()
        database.tables.append(copy.deepcopy(next(item for item in FIXTURE['tables'] if item['name']=='USER_TBL')))
        with self.assertRaisesRegex(oracle.OracleReleaseError,'changed after plan'):
            manager.apply(reviewed,True,lambda phase:None)
        database.tables.clear()
        (self.source/self.manifest.scripts[0]).write_text('-- changed')
        with self.assertRaisesRegex(oracle.OracleReleaseError,'scripts changed'):
            manager.apply(reviewed,True,lambda phase:None)
        self.assertEqual(database.writes,[])

    def test_invalid_release_paths_duplicates_and_dependency_order_rejected(self):
        for scripts in (['../outside.sql'], ['ags_database/install.sql'], [self.manifest.scripts[0]]*2):
            self.manifest_path.write_text(json.dumps({'CreateSchemaIfMissing':'Y','Scripts':scripts}))
            with self.assertRaises(oracle.OracleReleaseError):
                oracle.ReleaseFile(self.source,self.manifest_path)
        self.manifest_path.write_text(json.dumps({'CreateSchemaIfMissing':'Y','Scripts':list(reversed(self.manifest.scripts))}))
        self.manifest = oracle.ReleaseFile(self.source,self.manifest_path)
        database = Database()
        with self.assertRaisesRegex(oracle.OracleReleaseError,'dependencies'):
            self.manager(database).discover()
        self.assertEqual(database.writes,[])


if __name__=='__main__':
    unittest.main()
