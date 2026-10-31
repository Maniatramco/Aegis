"""Seed first-install Aegis OCI state on an EMPTY application-state volume.

Run once, inside the destination backend image, with the application-state
claim mounted at /data, the database wallet at /run/aegis-db/wallet and the
same aegis-app Secret (AEGIS_MASTER_KEY) the Deployment will use. It writes:

  configuration/database.json   active_provider=oci + active_connection
  secrets/database/<uuid>.json  DB/wallet passwords, Fernet-encrypted
  configuration/settings.json   storage_provider=oci + bucket route

These are the files the aegis-api-worker init container checks. It uses the
application's own save_draft() so the encrypted format matches the backend.

Non-secret inputs come from environment variables (see REQUIRED below).
Passwords come only from AEGIS_SEED_DB_PASSWORD / AEGIS_SEED_WALLET_PASSWORD,
which must be supplied from a temporary Kubernetes Secret, never as arguments.

It refuses to overwrite existing state unless AEGIS_SEED_ALLOW_OVERWRITE=true.
It does not connect to the database, create tables or upload objects.
"""
import json
import os
import sys
import time
from pathlib import Path

REQUIRED = ('AEGIS_SEED_DB_USER', 'AEGIS_SEED_DB_ALIAS', 'AEGIS_SEED_DB_NAME', 'AEGIS_SEED_REGION',
            'AEGIS_SEED_BUCKET_NAMESPACE', 'AEGIS_SEED_BUCKET')


def fail(message):
    print('SEED STOPPED: ' + message, file=sys.stderr)
    sys.exit(1)


def main():
    missing = [key for key in REQUIRED + ('AEGIS_SEED_DB_PASSWORD', 'AEGIS_SEED_WALLET_PASSWORD', 'AEGIS_MASTER_KEY')
               if not os.getenv(key)]
    if missing:
        fail('missing environment values: ' + ', '.join(missing))
    # The backend image keeps the package at /app/ags_app (WORKDIR /app).
    for candidate in (os.getcwd(), '/app'):
        if (Path(candidate) / 'ags_app').is_dir() and candidate not in sys.path:
            sys.path.insert(0, candidate)
    from ags_app import core, database_control
    root = core.DATA
    database_file = root / database_control.REF
    settings_file = root / 'configuration/settings.json'
    if (database_file.exists() or settings_file.exists()) and os.getenv('AEGIS_SEED_ALLOW_OVERWRITE') != 'true':
        fail('existing state found under ' + str(root) + '; this helper is for an empty first-install volume only')
    wallet = Path(os.getenv('AEGIS_SEED_WALLET_DIR', '/run/aegis-db/wallet'))
    for name in ('tnsnames.ora', 'ewallet.pem'):
        if not (wallet / name).is_file():
            fail('wallet mount lacks ' + name + ' at ' + str(wallet))
    alias = os.environ['AEGIS_SEED_DB_ALIAS']
    if alias.lower() not in (wallet / 'tnsnames.ora').read_text(encoding='utf-8').lower():
        fail('alias ' + alias + ' is not present in tnsnames.ora')

    connection = database_control.Connection(
        provider='oci', name=os.environ['AEGIS_SEED_DB_NAME'], region=os.environ['AEGIS_SEED_REGION'],
        username=os.environ['AEGIS_SEED_DB_USER'], dsn=alias, auth_mode='mtls', wallet_directory=str(wallet))
    cfg = connection.model_dump(exclude={'password', 'wallet_password'})
    cfg['_password'] = os.environ['AEGIS_SEED_DB_PASSWORD']
    cfg['_wallet_password'] = os.environ['AEGIS_SEED_WALLET_PASSWORD']
    saved = database_control.save_draft(cfg)
    state = database_control.state()
    state.update(active_provider='oci', active_connection=saved, activated_at=time.time())
    core.local_store.put_json(database_control.REF, state)

    from ags_app.storage_config import Destination
    destination = Destination(
        storage_provider='oci', oci_storage_namespace=os.environ['AEGIS_SEED_BUCKET_NAMESPACE'],
        oci_storage_bucket=os.environ['AEGIS_SEED_BUCKET'],
        oci_storage_prefix=os.getenv('AEGIS_SEED_BUCKET_PREFIX', 'aegis'),
        oci_storage_region=os.getenv('AEGIS_SEED_BUCKET_REGION', os.environ['AEGIS_SEED_REGION']),
        oci_storage_profile=os.getenv('AEGIS_SEED_OCI_PROFILE', 'DEFAULT'))
    try:
        existing = core.local_store.json('configuration/settings.json')
    except FileNotFoundError:
        existing = {}
    core.local_store.put_json('configuration/settings.json', existing | destination.model_dump())

    # Self-check: the same assertions as the verify-existing-oci-state init container.
    d = json.loads(database_file.read_text())
    assert d.get('active_provider') == 'oci'
    assert (root / d['active_connection']['secret_ref']).is_file()
    assert json.loads(settings_file.read_text()).get('storage_provider') == 'oci'
    assert database_control.secrets_for(d['active_connection']).get('password'), 'secret does not decrypt'
    reranker = (root / 'models/reranker').is_dir()
    print(json.dumps({'seeded': True, 'root': str(root), 'secret_ref': d['active_connection']['secret_ref'],
                      'reranker_present': reranker}, indent=2))
    if not reranker:
        print('NOTE: models/reranker is still missing; copy the staged reranker files before starting the app.')


if __name__ == '__main__':
    main()
