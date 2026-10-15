"""Read-only Oracle metadata inspection and comparison with the shipped SQL.

The remote script runs inside the already configured API container. It imports
no Aegis application modules and emits no credentials or application row data.
"""
import inspect
import re


def inspect_connection(connection, names):
    result = {'tables': []}
    with connection.cursor() as cursor:
        cursor.execute('SET TRANSACTION READ ONLY')
        cursor.execute("SELECT USER,SYS_CONTEXT('USERENV','SERVICE_NAME') FROM dual")
        result['owner'],result['service_name']=cursor.fetchone()
        cursor.execute('SELECT table_name FROM user_tables ORDER BY table_name')
        result['present_tables']=[row[0] for row in cursor.fetchall()]
        for name in names:
            if name not in result['present_tables']:continue
            cursor.execute('SELECT column_name,data_type,data_length,char_length,char_used,data_precision,data_scale,nullable,data_default,collation FROM user_tab_columns WHERE table_name=:name ORDER BY column_id',name=name)
            columns=[]
            for row in cursor.fetchall():
                values=list(row)
                if hasattr(values[8],'read'):values[8]=values[8].read()
                columns.append(dict(zip(('name','type','data_length','char_length','char_used','precision','scale','nullable','default','collation'),values)))
            cursor.execute('SELECT constraint_name,constraint_type,r_constraint_name,delete_rule,status,search_condition_vc,validated FROM user_constraints WHERE table_name=:name ORDER BY constraint_name',name=name)
            constraints=[dict(zip(('name','type','references','delete_rule','status','condition','validated'),row)) for row in cursor.fetchall()]
            cursor.execute('SELECT constraint_name,column_name,position FROM user_cons_columns WHERE table_name=:name ORDER BY constraint_name,position',name=name)
            constraint_columns=[dict(zip(('constraint','column','position'),row)) for row in cursor.fetchall()]
            cursor.execute('SELECT index_name,uniqueness,index_type,status FROM user_indexes WHERE table_name=:name ORDER BY index_name',name=name)
            indexes=[dict(zip(('name','unique','type','status'),row)) for row in cursor.fetchall()]
            cursor.execute('SELECT index_name,column_name,column_position FROM user_ind_columns WHERE table_name=:name ORDER BY index_name,column_position',name=name)
            index_columns=[dict(zip(('index','column','position'),row)) for row in cursor.fetchall()]
            ddl=''
            if name=='AEGIS_KNOWLEDGE_VECTORS':
                cursor.execute("SELECT DBMS_METADATA.GET_DDL('TABLE',:name) FROM dual",name=name)
                ddl=cursor.fetchone()[0]
                if hasattr(ddl,'read'):ddl=ddl.read()
            result['tables'].append(dict(name=name,columns=columns,constraints=constraints,constraint_columns=constraint_columns,indexes=indexes,index_columns=index_columns,ddl=ddl))
        if 'JOB_TBL' in result['present_tables']:
            cursor.execute("SELECT COUNT(*) FROM JOB_TBL WHERE LOWER(STATUS) IN ('queued','running','processing','pending','retrying')")
            result['active_jobs']=cursor.fetchone()[0]
        else:result['active_jobs']=0
        cursor.execute("SELECT VECTOR_DISTANCE(TO_VECTOR('[1,0]'),TO_VECTOR('[1,0]'),COSINE) FROM dual")
        result['vector_distance']=cursor.fetchone()[0]
    connection.rollback()
    return result


REMOTE_INSPECTION = r'''
INSPECT_CONNECTION_SOURCE

import json,os
from pathlib import Path
from cryptography.fernet import Fernet
import oracledb
root=Path(os.environ.get('AEGIS_STORAGE_ROOT','/data')).resolve()
state=json.loads((root/'configuration/database.json').read_text())
if state.get('active_provider')!='oci':raise RuntimeError('Expected an existing OCI database connection')
cfg=state['active_connection']
secret_path=(root/cfg['secret_ref']).resolve()
if root not in secret_path.parents:raise RuntimeError('Invalid saved credential path')
key=os.environ.get('AEGIS_MASTER_KEY',os.environ.get('MASTER_KEY'))
encrypted=json.loads(secret_path.read_text())['encrypted']
secret=json.loads(Fernet(key.encode()).decrypt(encrypted.encode()))
args=dict(user=cfg['username'],password=secret['password'],dsn=cfg['dsn'],tcp_connect_timeout=10,retry_count=0,ssl_server_dn_match=True)
if cfg['auth_mode']=='mtls':args.update(config_dir=cfg['wallet_directory'],wallet_location=cfg['wallet_directory'],wallet_password=secret['wallet_password'])
with oracledb.connect(**args) as connection:
    result=inspect_connection(connection,TABLE_NAMES)
result['wallet_alias']=cfg['dsn']
print(json.dumps(result))
'''


class SchemaMismatch(RuntimeError):
    pass


def table_definitions(source):
    definitions = {}
    for path in sorted((source/'ags_database/ags_tables').glob('*.sql')):
        text = path.read_text(encoding='utf-8')
        match = re.search(r'CREATE TABLE "([A-Z0-9_]+)"', text)
        if not match:
            raise SchemaMismatch(f'Unrecognized table script: {path.name}')
        definitions[match[1]] = text
    if len(definitions) != 13:
        raise SchemaMismatch('The release must contain the thirteen OCI table definitions')
    return definitions


def inspection_script(source):
    return REMOTE_INSPECTION.replace('INSPECT_CONNECTION_SOURCE', inspect.getsource(inspect_connection)).replace('TABLE_NAMES', repr(sorted(table_definitions(source))))


def normalize(text):
    # SQL keywords are case insensitive; quoted string values are not.
    return ''.join(part if index % 2 else re.sub(r'\s+', '', part.replace('"', '')).upper()
                   for index, part in enumerate(re.split(r"('(?:''|[^'])*')", text)))


def quoted_columns(text):
    return re.findall(r'"([A-Za-z0-9_]+)"', text)


def verify_schema(source, metadata, allow_missing=False):
    expected = table_definitions(source)
    actual = {table['name']: table for table in metadata['tables']}
    if (not set(actual) <= set(expected)) or (not allow_missing and set(actual) != set(expected)):
        raise SchemaMismatch('Application tables do not match the thirteen-table release; no upgrade was attempted')
    constraints = {item['name']: (table, item) for table in actual.values() for item in table['constraints']}
    totals = {'tables': 13, 'columns': 0, 'foreign_keys': 0, 'indexes': 0}

    def require(condition, detail):
        if not condition:
            raise SchemaMismatch(detail)

    def columns(table, constraint):
        return [item['column'] for item in table['constraint_columns'] if item['constraint'] == constraint]

    for name, text in expected.items():
        if name not in actual:
            continue
        table = actual[name]
        clauses = [line.strip().rstrip(',') for line in text.splitlines() if line.startswith('  ')]
        declarations = {match[1]: match[2] for line in clauses if (match := re.match(r'^"([A-Za-z0-9_]+)" (.+)$', line))}
        require(list(declarations) == [item['name'] for item in table['columns']], f'{name}: columns/order differ')
        for column in table['columns']:
            label = name+'.'+column['name']
            part = declarations[column['name']]
            kind = column['type']
            require(('NOT NULL' in part) == (column['nullable'] == 'N'), label+': nullability differs')
            if kind == 'VARCHAR2':
                size = column['char_length'] if column['char_used'] == 'C' else column['data_length']
                unit = 'CHAR' if column['char_used'] == 'C' else 'BYTE'
                require(part.startswith(f'VARCHAR2({size} {unit}) '), label+': length/semantics differ')
            elif kind == 'NUMBER':
                number = 'NUMBER' if column['scale'] is None else f"NUMBER({column['precision'] or '*'},{column['scale']})"
                require(re.match(re.escape(number)+r'(?:\s|$)', part) is not None, label+': numeric precision differs')
            elif kind == 'VECTOR':
                require(part.startswith('VECTOR(*, FLOAT32)'), label+': vector definition differs')
                require('EMBEDDINGVECTOR(*,FLOAT32)' in normalize(table['ddl']), label+': live vector dimensions/type differ')
            else:
                require(re.match(re.escape(kind)+r'(?:\s|$)', part) is not None, label+': type differs')
            default = (column['default'] or '').strip()
            require(('DEFAULT ' in part) == bool(default), label+': default differs')
            if default:
                declared_default = re.search(r'\bDEFAULT\s+(.*?)(?=\s+NOT NULL|\s+ENABLE|$)', part)
                require(declared_default and normalize(declared_default[1]) == normalize(default), label+': default value differs')
            if kind in ('VARCHAR2', 'CLOB'):
                require(column['collation'] == 'USING_NLS_COMP' and 'COLLATE "USING_NLS_COMP"' in part, label+': collation differs')
            totals['columns'] += 1
        for kind, keyword in (('P', 'PRIMARY KEY'), ('U', 'UNIQUE')):
            declared = [quoted_columns(match[1]) for line in clauses if (match := re.search(r'\b'+keyword+r' \(([^)]+)\)', line))]
            observed = [columns(table, item['name']) for item in table['constraints'] if item['type'] == kind]
            require(sorted(declared) == sorted(observed), name+': primary/unique keys differ')
        declared_fk = []
        for line in clauses:
            match = re.search(r'FOREIGN KEY \(([^)]+)\) REFERENCES "([A-Z0-9_]+)" \(([^)]+)\)(.*)', line)
            if match:
                rule = 'CASCADE' if 'ON DELETE CASCADE' in match[4] else 'SET NULL' if 'ON DELETE SET NULL' in match[4] else 'NO ACTION'
                declared_fk.append((quoted_columns(match[1]), match[2], quoted_columns(match[3]), rule))
        observed_fk = []
        named_checks = dict(re.findall(r'CONSTRAINT "([A-Z0-9_]+)" CHECK \((.*)\) ENABLE', text))
        observed_checks = {}
        for item in table['constraints']:
            require(item['status'] == 'ENABLED' and item['validated'] == 'VALIDATED', name+': disabled/unvalidated constraint')
            if item['type'] == 'R':
                require(item['references'] in constraints, name+': foreign key references an unexpected table')
                target, primary = constraints[item['references']]
                observed_fk.append((columns(table, item['name']), target['name'], columns(target, primary['name']), item['delete_rule']))
            elif item['type'] == 'C' and not item['name'].startswith('SYS_'):
                observed_checks[item['name']] = item['condition']
        require(sorted(declared_fk) == sorted(observed_fk), name+': foreign keys/delete rules differ')
        require({key: normalize(value) for key, value in named_checks.items()} == {key: normalize(value) for key, value in observed_checks.items()}, name+': check constraints differ')
        expected_c = sum('NOT NULL' in value for value in declarations.values())+len(named_checks)
        require(sum(item['type'] == 'C' for item in table['constraints']) == expected_c, name+': check/NOT NULL constraint count differs')
        totals['foreign_keys'] += len(declared_fk)
        declared_indexes = {match[1]: quoted_columns(match[2]) for match in re.finditer(r'CREATE INDEX "([A-Z0-9_]+)" ON "'+name+r'" \(([^;]+)\);', text)}
        observed_indexes = {}
        for index in table['indexes']:
            if index['name'].startswith('IX_'):
                require(index['type'] == 'NORMAL' and index['status'] == 'VALID' and index['unique'] == 'NONUNIQUE', name+': application index is invalid')
                observed_indexes[index['name']] = [value['column'] for value in table['index_columns'] if value['index'] == index['name']]
        require((all(key in declared_indexes and declared_indexes[key] == value for key, value in observed_indexes.items()) if allow_missing else declared_indexes == observed_indexes), name+': application indexes differ')
        totals['indexes'] += len(declared_indexes)
    require(metadata.get('vector_distance') == 0, 'Native vector capability check failed')
    return totals
