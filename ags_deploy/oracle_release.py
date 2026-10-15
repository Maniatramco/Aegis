"""Apply an ordered, reviewed Oracle object release; never alter existing objects."""
import getpass
import hashlib
import importlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import zipfile


class OracleReleaseError(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def identifier(value):
    if not re.fullmatch(r'[A-Z][A-Z0-9_$#]{0,127}', value) or value in ('SYS', 'SYSTEM'):
        raise OracleReleaseError('Use an unquoted application/admin name other than SYS or SYSTEM')
    return '"'+value+'"'


def private_password(prompt):
    if not sys.stdin.isatty():
        raise OracleReleaseError('Run the database release in an interactive terminal for private password prompts')
    return getpass.getpass(prompt)


class ReleaseFile:
    def __init__(self, source, path):
        self.source = source.resolve()
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict) or set(data) != {'CreateSchemaIfMissing', 'Scripts'}:
            raise OracleReleaseError('Release JSON must contain CreateSchemaIfMissing and ordered Scripts')
        if data['CreateSchemaIfMissing'] not in ('Y', 'N'):
            raise OracleReleaseError('CreateSchemaIfMissing must be Y or N')
        scripts = data['Scripts']
        if not isinstance(scripts, list) or not scripts or any(not isinstance(item, str) for item in scripts):
            raise OracleReleaseError('Scripts must be a nonempty ordered list of repository-relative SQL paths')
        if len(set(scripts)) != len(scripts):
            raise OracleReleaseError('Release file contains duplicate scripts')
        self.create_schema = data['CreateSchemaIfMissing'] == 'Y'
        self.scripts, self.statements, self.hashes = scripts, [], {}
        for relative in scripts:
            part = PurePosixPath(relative)
            if part.is_absolute() or '..' in part.parts or '\\' in relative or ':' in relative:
                raise OracleReleaseError('Release script paths must stay inside the selected source commit')
            file = (self.source/relative).resolve(strict=True)
            # This release creates the maintained Aegis objects. It is not a migration engine.
            if file.parent != self.source/'ags_database/ags_tables' or file.suffix != '.sql':
                raise OracleReleaseError('Object releases select maintained ags_database/ags_tables SQL files; migrations need separate review')
            self.hashes[relative] = hashlib.sha256(file.read_bytes()).hexdigest()
            sql = re.sub(r'(?m)^\s*--[^\n]*', '', file.read_text(encoding='utf-8'))
            for statement in (item.strip() for item in sql.split(';') if item.strip()):
                table = re.match(r'^CREATE TABLE "([A-Z0-9_]+)"\s*\(', statement)
                index = re.match(r'^CREATE INDEX "([A-Z0-9_]+)" ON "([A-Z0-9_]+)"\s*\(', statement)
                if not table and not index:
                    raise OracleReleaseError('Unsupported statement in object release: '+relative)
                self.statements.append({'script': relative, 'kind': 'TABLE' if table else 'INDEX',
                                        'name': (table or index)[1], 'table': table[1] if table else index[2], 'sql': statement})
        self.fingerprint = digest({'manifest': data, 'scripts': self.hashes})

    def unchanged(self):
        return all(hashlib.sha256((self.source/path).read_bytes()).hexdigest() == value for path, value in self.hashes.items())

    def plan(self, schema, metadata):
        schema.verify_schema(self.source, metadata, allow_missing=True)
        tables = {item['name']: item for item in metadata['tables']}
        indexes = {item['name'] for table in tables.values() for item in table['indexes']}
        objects = {(item['name'], item['type']) for item in metadata.get('objects', [])}
        available, actions = set(metadata['present_tables']), []
        for item in self.statements:
            if item['kind'] == 'TABLE':
                if item['name'] in tables:
                    continue
                if any(name == item['name'] and kind != 'INDEX' for name, kind in objects):
                    raise OracleReleaseError('A conflicting object already uses the table name: '+item['name'])
                dependencies = set(re.findall(r'REFERENCES "([A-Z0-9_]+)"', item['sql']))-{item['name']}
                if dependencies-available:
                    raise OracleReleaseError('Release order is missing dependencies for '+item['name']+': '+', '.join(sorted(dependencies-available)))
                available.add(item['name'])
            else:
                if item['name'] in indexes:
                    continue
                if (item['name'], 'INDEX') in objects:
                    raise OracleReleaseError('Index name is already used outside the expected table: '+item['name'])
                if item['table'] not in available:
                    raise OracleReleaseError('Index target table is missing: '+item['table'])
            actions.append(item)
        return actions


class DatabaseRelease:
    """Credentials stay in memory and are never included in plans, receipts or errors."""
    def __init__(self, schema, release, wallet, owner, alias, service, admin='ADMIN',
                 tablespace='DATA', quota_mb='256', password_fn=private_password, driver=None):
        self.schema, self.release = schema, release
        self.owner, self.admin = owner.upper(), admin.upper()
        identifier(self.owner); identifier(self.admin); identifier(tablespace.upper())
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', alias) or not re.fullmatch(r'[A-Za-z0-9_.-]+', service):
            raise OracleReleaseError('Invalid wallet alias or full database service')
        if not re.fullmatch(r'[1-9][0-9]{0,5}', quota_mb):
            raise OracleReleaseError('SchemaQuotaMB must be a positive integer string, at most 999999')
        self.alias, self.service = alias, service
        self.tablespace, self.quota = tablespace.upper(), int(quota_mb)
        self.password_fn = password_fn
        try:
            self.driver = driver or importlib.import_module('oracledb')
        except ImportError:
            raise OracleReleaseError('DB_Object=Y needs python-oracledb in the selected Python environment (use the existing Oracle requirements)') from None
        self.connections, self.passwords, self.applied = {}, {}, []
        self.temporary = tempfile.TemporaryDirectory(prefix='aegis-db-release-')
        self.wallet = Path(self.temporary.name)
        try:
            with zipfile.ZipFile(wallet) as package:
                for member in package.infolist():
                    target = (self.wallet/member.filename).resolve()
                    if self.wallet not in target.parents or '\\' in member.filename or ':' in member.filename:
                        raise OracleReleaseError('Invalid wallet archive path')
                package.extractall(self.wallet)
            tns = list(self.wallet.rglob('tnsnames.ora'))
            if len(tns) != 1 or not (tns[0].parent/'ewallet.pem').is_file():
                raise OracleReleaseError('Wallet must contain one tnsnames.ora and its ewallet.pem')
            self.wallet_dir = tns[0].parent
            text = tns[0].read_text(encoding='utf-8')
            if not re.search(r'(?im)^\s*'+re.escape(alias)+r'\s*=', text) or service.lower() not in text.lower():
                raise OracleReleaseError('Wallet does not contain the requested alias/full service')
        except BaseException:
            self.close()
            raise

    def safe(self, function):
        try:
            return function()
        except (OracleReleaseError, self.schema.SchemaMismatch):
            raise
        except Exception as error:
            code = getattr(error.args[0], 'code', None) if error.args else None
            raise OracleReleaseError('Oracle database release failed'+(' (Oracle code '+str(code)+')' if isinstance(code, int) else '')+
                                     '; inspect the recorded phase. Sensitive driver details were withheld') from None

    def connection(self, username):
        if username not in self.connections:
            if 'wallet' not in self.passwords:
                self.passwords['wallet'] = self.password_fn('OCI wallet password (private): ')
            if username not in self.passwords:
                self.passwords[username] = self.password_fn(username+' database password (private): ')
            self.connections[username] = self.safe(lambda: self.driver.connect(user=username, password=self.passwords[username],
                dsn=self.alias, config_dir=str(self.wallet_dir), wallet_location=str(self.wallet_dir),
                wallet_password=self.passwords['wallet'], tcp_connect_timeout=10, retry_count=0, ssl_server_dn_match=True))
        return self.connections[username]

    def admin_snapshot(self):
        connection = self.connection(self.admin)
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
            cursor.execute("SELECT USER,SYS_CONTEXT('USERENV','SERVICE_NAME') FROM dual")
            identity = cursor.fetchone()
            if identity[0] != self.admin or identity[1].lower() != self.service.lower():
                raise OracleReleaseError('Wrong administrator or database service')
            cursor.execute('SELECT username,oracle_maintained,user_id FROM all_users WHERE username=:owner', owner=self.owner)
            account = cursor.fetchone()
            if account and account[1] == 'Y' and self.owner != 'ADMIN':
                raise OracleReleaseError('Oracle-maintained schema cannot be an application destination')
            cursor.execute("SELECT LENGTH(CAST('x' AS VARCHAR2(32767 BYTE))) FROM dual")
            if cursor.fetchone()[0] != 1:
                raise OracleReleaseError('Extended strings are unavailable')
            cursor.execute('SELECT CASE WHEN CAST(TRUE AS BOOLEAN) THEN 1 ELSE 0 END FROM dual')
            if cursor.fetchone()[0] != 1:
                raise OracleReleaseError('SQL BOOLEAN is unavailable')
            cursor.execute("SELECT VECTOR_DISTANCE(TO_VECTOR('[1,0]'),TO_VECTOR('[1,0]'),COSINE) FROM dual")
            if cursor.fetchone()[0] != 0:
                raise OracleReleaseError('Native vectors are unavailable')
            cursor.execute('SELECT privilege FROM session_privs')
            privileges = {row[0] for row in cursor.fetchall()}
            cursor.execute("SELECT privilege FROM user_sys_privs WHERE admin_option='YES'")
            grantable = {row[0] for row in cursor.fetchall()}
            cursor.execute('SELECT tablespace_name FROM user_tablespaces WHERE tablespace_name=:name', name=self.tablespace)
            available_space = bool(cursor.fetchone())
        connection.rollback()
        if not account:
            if not self.release.create_schema:
                raise OracleReleaseError('Application schema is missing and release file does not permit creation')
            if 'CREATE USER' not in privileges or not ('GRANT ANY PRIVILEGE' in privileges or {'CREATE SESSION','CREATE TABLE'} <= grantable):
                raise OracleReleaseError('Existing admin access cannot create/grant the new application schema')
            if not available_space:
                raise OracleReleaseError('Requested existing tablespace is unavailable; no tablespace will be created')
        return list(account) if account else None

    def owner_snapshot(self):
        connection = self.connection(self.owner)
        metadata = self.schema.inspect_connection(connection, sorted(self.schema.table_definitions(self.release.source)))
        if metadata['owner'] != self.owner or metadata['service_name'].lower() != self.service.lower():
            raise OracleReleaseError('Wrong application owner or database service')
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
            cursor.execute("SELECT SYS_CONTEXT('USERENV','CURRENT_SCHEMA') FROM dual")
            if cursor.fetchone()[0] != self.owner:
                raise OracleReleaseError('Application connection has an unexpected current schema; no object DDL is permitted')
            cursor.execute('SELECT object_name,object_type FROM user_objects')
            metadata['objects'] = sorted(({'name': row[0], 'type': row[1]} for row in cursor.fetchall()), key=lambda item:(item['name'],item['type']))
            cursor.execute('SELECT privilege FROM session_privs')
            metadata['privileges'] = sorted(row[0] for row in cursor.fetchall())
            cursor.execute('SELECT default_tablespace FROM user_users')
            metadata['tablespace'] = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM user_ts_quotas WHERE tablespace_name=:name AND (max_bytes=-1 OR max_bytes>bytes)', name=metadata['tablespace'])
            metadata['quota_available'] = bool(cursor.fetchone()[0]) or 'UNLIMITED TABLESPACE' in metadata['privileges']
        connection.rollback()
        return metadata

    def discover(self):
        # Builds/approval can outlast an OCI idle session. Refresh only read-only
        # discovery connections; never retry a DDL statement automatically.
        self.close_connections()
        def inspect():
            account = self.admin_snapshot()
            metadata = self.owner_snapshot() if account else {'owner':self.owner,'service_name':self.service,'present_tables':[],
                                                             'tables':[],'objects':[],'vector_distance':0,'active_jobs':0}
            actions = self.release.plan(self.schema, metadata)
            if account and any(item['kind']=='TABLE' for item in actions):
                if 'CREATE TABLE' not in metadata['privileges'] or not metadata['quota_available']:
                    raise OracleReleaseError('Existing application owner needs CREATE TABLE and available quota; existing grants/quota will not be changed')
            if not account and self.owner not in self.passwords:
                password = self.password_fn('New '+self.owner+' password (private): ')
                if not password or any(character in password for character in ('"', "'", '\n', '\r', '\x00')):
                    raise OracleReleaseError('New password cannot be empty or contain quotes/line breaks; Oracle also enforces its configured complexity rules')
                if password != self.password_fn('Confirm new schema password (private): '):
                    raise OracleReleaseError('New schema passwords do not match')
                self.passwords[self.owner] = password
            snapshot = {'account': account, 'metadata': metadata}
            return {'snapshot': snapshot, 'fingerprint': digest(snapshot), 'actions': actions,
                    'summary': {'owner':self.owner,'admin_user':self.admin,'service_name':self.service,'wallet_alias':self.alias,'create_schema':not bool(account),
                                'new_schema_tablespace': self.tablespace if not account else None,
                                'new_schema_quota_mb': self.quota if not account else None,
                                'new_schema_grants': ['CREATE SESSION','CREATE TABLE'] if not account else [],
                                'scripts_in_order': self.release.scripts,'release_sha256':self.release.fingerprint,
                                'objects_to_create':[{'script':item['script'],'kind':item['kind'],'name':item['name']} for item in actions],
                                'existing_matching_objects':'Preserved; no drops, alterations, data writes or password resets',
                                'active_jobs':metadata['active_jobs']}}
        return self.safe(inspect)

    def apply(self, reviewed, approved, checkpoint):
        if approved is not True:
            raise OracleReleaseError('PUBLISH approval is required before database changes')
        if not self.release.unchanged():
            raise OracleReleaseError('Approved release scripts changed')
        current = self.discover()
        if current['fingerprint'] != reviewed['fingerprint']:
            raise OracleReleaseError('Database changed after plan review; review a new plan')
        def execute():
            if not current['snapshot']['account']:
                checkpoint('Creating the explicitly approved application schema/user')
                with self.connection(self.admin).cursor() as cursor:
                    # Values never enter argv, JSON, logs, error text or a saved SQL file.
                    cursor.execute('CREATE USER '+identifier(self.owner)+' IDENTIFIED BY "'+self.passwords[self.owner]+
                                   '" DEFAULT TABLESPACE '+identifier(self.tablespace)+' QUOTA '+str(self.quota)+'M ON '+identifier(self.tablespace))
                    self.applied.append({'kind':'USER','name':self.owner})
                    cursor.execute('GRANT CREATE SESSION, CREATE TABLE TO '+identifier(self.owner))
                created = self.owner_snapshot()
                if created['present_tables']:
                    raise OracleReleaseError('New schema unexpectedly contains tables; inspect before continuing')
            connection = self.connection(self.owner)
            for item in current['actions']:
                checkpoint('Creating '+item['kind']+' '+item['name']+' from '+item['script'])
                with connection.cursor() as cursor:
                    cursor.execute(item['sql'])
                self.applied.append({key:item[key] for key in ('kind','name','script')})
            after = self.discover()
            if after['actions']:
                raise OracleReleaseError('Listed objects are still missing after execution; inspect partial results')
            return {'owner':self.owner,'service_name':self.service,'completed_objects':list(self.applied),
                    'scripts_in_order':self.release.scripts,'release_sha256':self.release.fingerprint,'listed_objects_verified':True}
        return self.safe(execute)

    def close_connections(self):
        for connection in self.connections.values():
            try: connection.close()
            except Exception: pass
        self.connections.clear()

    def close(self):
        self.close_connections()
        self.passwords.clear()
        self.temporary.cleanup()
