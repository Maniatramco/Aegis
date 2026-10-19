"""Synthetic, local-only Aegis workspace for the offline Select AI preview.

Run after setup_select_ai_local.py. No existing Aegis or OCI data is opened.
Only username mani starts with Data Governance; the fixture administrator does not.
"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'ags_runtime' / 'select-ai-local' / 'preview'
STATE.mkdir(parents=True, exist_ok=True)
for key in list(os.environ):
    if key.startswith(('AEGIS_', 'DATABASE_', 'ORACLE_', 'OCI_', 'OPENAI_', 'EMBEDDING_', 'MODEL_', 'GOOGLE_', 'ANTHROPIC_', 'AZURE_', 'AWS_')):
        os.environ.pop(key)
os.environ.update(
    AEGIS_STORAGE_ROOT=str(STATE),
    DATABASE_URL='sqlite:///' + (STATE / 'preview.db').as_posix(),
    DATABASE_PROVIDER='sqlite', AEGIS_ALLOW_MOCK='true', MODEL_PROVIDER='mock',
    EMBEDDING_PROVIDER='mock', SEARCH_PROVIDER='local', STORAGE_PROVIDER='local',
    AEGIS_LOCAL_ONLY='true', AEGIS_LOCAL_SQL_ENABLED='true',
    AEGIS_LOCAL_SQL_CONNECTION_FILE=str(ROOT / 'ags_runtime/select-ai-local/connection.json'),
    ALLOWED_ORIGINS='http://localhost:60563,http://127.0.0.1:60563')
sys.path.insert(0, str(ROOT / 'ags_backend'))
from cryptography.fernet import Fernet
key_file = STATE / 'master.key'
if not key_file.exists():
    key_file.write_bytes(Fernet.generate_key())
os.environ['AEGIS_MASTER_KEY'] = key_file.read_text()
from ags_app import core, main, governance, relational
core.init()
with core.Session.begin() as session:
    for id, username, role in [('local-mani', 'mani', 'user'), ('local-admin', 'local-preview-admin', 'administrator')]:
        if not session.get(core.User, id):
            session.add(core.User(id=id, username=username, role=role,
                                  password_hash=core.password_hash('LocalSelectAI-demo-2026')))
with core.Session() as session:
    exists = session.scalar(core.select(core.Record.id).where(core.Record.kind == 'knowledge_base'))
if not exists:
    finance = main.new_record('knowledge_base', 'local-admin', 'Invoice Operations',
        data={'description': 'Synthetic supplier invoice register', 'active': True, 'mappings': []})
    contracts = main.new_record('knowledge_base', 'local-admin', 'Supplier Contracts',
        data={'description': 'Synthetic contract metadata, awaiting a steward', 'active': True, 'mappings': []})
    private = main.new_record('knowledge_base', 'local-admin', 'Administrator private dataset',
        data={'description': 'Excluded from the mani preview scope', 'active': True, 'mappings': []})
    for number, name in enumerate(['invoice-april.pdf', 'invoice-may.pdf', 'invoice-june.pdf']):
        document = main.new_record('document', 'local-admin', name, parent=finance.id)
        with core.Session.begin() as session:
            session.get(core.Record, document.id).size = (number + 1) * 1024
    main.new_record('document', 'local-admin', 'private.txt', parent=private.id)
    for number, review in enumerate(['unreviewed', 'reviewed']):
        main.new_record('extraction', 'local-admin', 'Invoice run ' + str(number + 1), parent=finance.id,
            data={'document_ids': [], 'review_status': review})
    # Explicit policy fixture creation; this does not grant the admin UI access.
    with core.Session() as session:
        record = session.get(core.Record, finance.id)
        id = governance.policy_id(finance.id)
    core.store.put_json('synthetic/finance-policy.json', {
        'owner_name': 'Finance team', 'steward': 'Accounts payable', 'classification': 'confidential',
        'purpose': 'Reconcile synthetic supplier invoices', 'retention_days': 365, 'glossary': [],
        'change_reason': 'Synthetic local preview', 'updated_by': 'local-admin'})
    with core.Session.begin() as session:
        session.add(core.Record(id=id, kind='governance_policy', owner='local-admin', parent_id=finance.id,
                                ref='synthetic/finance-policy.json', version=1))
        for dataset in (finance, contracts):
            session.add(relational.UserDataset(user_id='local-mani', dataset_id=dataset.id, enabled=True))
import uvicorn
uvicorn.run(main.app, host='127.0.0.1', port=60562, log_level='warning')
