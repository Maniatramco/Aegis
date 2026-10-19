"""Prepare only the dedicated offline Oracle Free and downloaded Qwen pilot.

Images and qwen3:4b must already be cached. This launcher never pulls images
or models and never contacts OCI. Private state stays in ignored ags_runtime/.
"""
import argparse
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'ags_runtime' / 'select-ai-local'
ENV = STATE / 'local.env'
COMPOSE = ROOT / 'ags_local_use' / 'compose.select-ai-local.yaml'
ORACLE = 'aegis-select-ai-local-oracle-1'
SCHEMA = 'AEGIS_LOCAL_AI'
PROFILE = 'AEGIS_LOCAL_METADATA'


def run(args, content=None):
    result = subprocess.run(args, input=content.encode() if content is not None else None,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=ROOT)
    if result.returncode:
        # Driver logs can contain credentials. Keep them private.
        (STATE / 'setup-error.log').write_bytes(result.stdout)
        raise RuntimeError('Local setup failed; inspect ags_runtime/select-ai-local/setup-error.log.')
    return result.stdout.decode(errors='replace')


def bash(script):
    return run(['docker', 'exec', '-i', ORACLE, 'bash'], script.replace('\r\n', '\n'))


def sql(script):
    return run(['docker', 'exec', '-i', ORACLE, 'bash', '-c',
                '"$ORACLE_HOME/bin/sqlplus" -s / as sysdba'],
               'whenever sqlerror exit failure rollback\nset echo off feedback off verify off define off\n'
               + script + '\nexit\n')


def configuration(model_volume):
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / 'audit').mkdir(exist_ok=True)
    values = {}
    if ENV.exists():
        values = dict(line.split('=', 1) for line in ENV.read_text().splitlines() if line and not line.startswith('#'))
    for key, prefix in [('LOCAL_SELECT_AI_DB_PASSWORD', 'LocalAI'),
                        ('LOCAL_SELECT_AI_APP_PASSWORD', 'AppAI'),
                        ('LOCAL_SELECT_AI_WALLET_PASSWORD', 'WalletAI')]:
        values.setdefault(key, prefix + secrets.token_hex(16))
    values.setdefault('LOCAL_SELECT_AI_TOKEN', secrets.token_urlsafe(36))
    values.setdefault('LOCAL_SELECT_AI_MODELS_VOLUME', model_volume)
    ENV.write_text(''.join(f'{key}={value}\n' for key, value in values.items()), encoding='utf-8')
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models-volume', default='aegis-oracle_ollama',
                        help='Existing Docker volume containing downloaded qwen3:4b')
    args = parser.parse_args()
    values = configuration(args.models_volume)
    import sqlglot
    if sqlglot.__version__ != '30.23.0':
        raise RuntimeError('Install ags_backend/requirements-select-ai.txt before local setup.')
    # Pure Python dependency, copied from this environment; no container downloads.
    shutil.copytree(Path(sqlglot.__file__).parent, STATE / 'dependencies/sqlglot',
                    dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    compose = ['docker', 'compose', '--project-directory', str(ROOT), '--env-file', str(ENV), '-f', str(COMPOSE)]
    print(run(compose + ['up', '-d', '--pull', 'never']))
    network = json.loads(run(['docker', 'network', 'inspect', 'aegis-select-ai-local_offline']))[0]
    if network['Internal'] is not True:
        raise RuntimeError('Refusing a network with outbound access.')
    for service in ('oracle', 'model', 'adapter', 'tls'):
        networks = json.loads(run(['docker', 'inspect', '--format', '{{json .NetworkSettings.Networks}}',
                                  f'aegis-select-ai-local-{service}-1']))
        if set(networks) != {'aegis-select-ai-local_offline'}:
            raise RuntimeError('Refusing an inference service attached to an additional network.')
    for _ in range(90):
        status = json.loads(run(['docker', 'inspect', '--format', '{{json .State}}', ORACLE]))
        if status.get('Health', {}).get('Status') == 'healthy':
            break
        time.sleep(2)
    else:
        raise RuntimeError('The dedicated Oracle Free database did not become healthy.')

    packages = "select count(*) from cdb_objects where object_name in ('DBMS_CLOUD','DBMS_CLOUD_AI') and object_type in ('PACKAGE','PACKAGE BODY') and status='VALID';"
    if '8' not in sql(packages).split():
        print('Installing Oracle-supplied DBMS_CLOUD family packages...')
        for entry in ('catclouduser', 'dbms_cloud_install'):
            bash(f'''set -eu
cd /tmp
"$ORACLE_HOME/perl/bin/perl" "$ORACLE_HOME/rdbms/admin/catcon.pl" -force_pdb_mode 'READ WRITE' -b aegis_{entry} -d "$ORACLE_HOME/rdbms/admin" -l /tmp {entry}.sql > /tmp/aegis_{entry}_driver.log 2>&1
''')
        if '8' not in sql(packages).split():
            raise RuntimeError('Oracle Select AI packages are not valid in both containers.')

    run(['docker', 'cp', 'aegis-select-ai-local-tls-1:/data/caddy/pki/authorities/local/root.crt', str(STATE / 'local-root.crt')])
    run(['docker', 'cp', str(STATE / 'local-root.crt'), ORACLE + ':/tmp/aegis-local-root.crt'])
    wallet = '/opt/oracle/oradata/local-select-ai/wallet'
    bash(f'''set -eu
mkdir -p {wallet}
if [ ! -f {wallet}/cwallet.sso ]; then
 "$ORACLE_HOME/bin/orapki" wallet create -wallet {wallet} -pwd '{values['LOCAL_SELECT_AI_WALLET_PASSWORD']}' -auto_login > /tmp/aegis_wallet.log 2>&1
 "$ORACLE_HOME/bin/orapki" wallet add -wallet {wallet} -trusted_cert -cert /tmp/aegis-local-root.crt -pwd '{values['LOCAL_SELECT_AI_WALLET_PASSWORD']}' >> /tmp/aegis_wallet.log 2>&1
fi
''')
    app_password = values['LOCAL_SELECT_AI_APP_PASSWORD']
    sql(f"""ALTER DATABASE PROPERTY SET SSL_WALLET='{wallet}';
BEGIN
 DBMS_NETWORK_ACL_ADMIN.APPEND_HOST_ACE(host=>'llm.aegis.local', lower_port=>443, upper_port=>443,
  ace=>xs$ace_type(privilege_list=>xs$name_list('http'),principal_name=>'C##CLOUD$SERVICE',principal_type=>xs_acl.ptype_db));
END;
/
ALTER SESSION SET CONTAINER=FREEPDB1;
BEGIN
 FOR row IN (SELECT username FROM dba_users WHERE username='{SCHEMA}') LOOP RETURN; END LOOP;
 EXECUTE IMMEDIATE 'CREATE USER {SCHEMA} IDENTIFIED BY "{app_password}"';
END;
/
GRANT CREATE SESSION TO {SCHEMA};
GRANT EXECUTE ON DBMS_CLOUD TO {SCHEMA};
GRANT EXECUTE ON DBMS_CLOUD_AI TO {SCHEMA};
BEGIN
 FOR principal IN (SELECT 'C##CLOUD$SERVICE' name FROM dual UNION ALL SELECT '{SCHEMA}' FROM dual) LOOP
  DBMS_NETWORK_ACL_ADMIN.APPEND_HOST_ACE(host=>'llm.aegis.local', lower_port=>443, upper_port=>443,
   ace=>xs$ace_type(privilege_list=>xs$name_list('http'),principal_name=>principal.name,principal_type=>xs_acl.ptype_db));
 END LOOP;
END;
/
""")
    exists = sql(f"ALTER SESSION SET CONTAINER=FREEPDB1;\nSELECT count(*) FROM dba_tables WHERE owner='{SCHEMA}' AND table_name IN ('LOCAL_DATASETS','LOCAL_DOCUMENTS','LOCAL_EXTRACTIONS');")
    if '3' not in exists.split():
        if '0' not in exists.split():
            raise RuntimeError('Partial local schema found. Preserve and inspect before repair.')
        sql('ALTER SESSION SET CONTAINER=FREEPDB1;\n' + (ROOT / 'ags_local_use/ags_docker/ags_select_ai/schema.sql').read_text())

    import oracledb
    with oracledb.connect(user=SCHEMA, password=app_password, dsn='127.0.0.1:1523/FREEPDB1') as connection:
        cursor = connection.cursor()
        cursor.execute("select count(*) from user_credentials where credential_name='AEGIS_LOCAL_MODEL'")
        if cursor.fetchone()[0] == 0:
            cursor.callproc('DBMS_CLOUD.CREATE_CREDENTIAL', keyword_parameters={
                'credential_name': 'AEGIS_LOCAL_MODEL', 'username': 'LOCAL_ONLY', 'password': values['LOCAL_SELECT_AI_TOKEN']})
        attrs = {'provider': 'openai', 'provider_endpoint': 'https://llm.aegis.local',
                 'credential_name': 'AEGIS_LOCAL_MODEL', 'model': 'qwen3:4b',
                 'object_list': [{'owner': SCHEMA, 'name': name} for name in ['LOCAL_DATASETS','LOCAL_DOCUMENTS','LOCAL_EXTRACTIONS']],
                 'enforce_object_list': True, 'comments': True, 'conversation': False,
                 'temperature': 0, 'max_tokens': 768}
        cursor.execute('select count(*) from user_cloud_ai_profiles where profile_name=:name', name=PROFILE)
        if cursor.fetchone()[0] == 0:
            cursor.callproc('DBMS_CLOUD_AI.CREATE_PROFILE', keyword_parameters={'profile_name': PROFILE, 'attributes': json.dumps(attrs)})
        else:
            for name, value in attrs.items():
                cursor.callproc('DBMS_CLOUD_AI.SET_ATTRIBUTE', keyword_parameters={
                    'profile_name': PROFILE, 'attribute_name': name,
                    'attribute_value': json.dumps(value) if not isinstance(value, str) else value})
    (STATE / 'connection.json').write_text(json.dumps({'user': SCHEMA, 'password': app_password,
        'host': '127.0.0.1', 'port': 1523, 'service': 'FREEPDB1', 'profile': PROFILE}, indent=2))
    print('Local Select AI profile ready. Outbound network: blocked. Cloud inference: disabled.')


if __name__ == '__main__':
    main()
