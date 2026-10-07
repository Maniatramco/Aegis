"""Isolated operator recovery contracts; no real administrator or provider calls."""
import importlib.util
import io
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/reset_admin_password.py'
spec = importlib.util.spec_from_file_location('recovery', SCRIPT)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
cli = r
r = cli.recovery
PASSWORD = 'synthetic-new-password-only'


@pytest.fixture
def database(tmp_path):
    path = tmp_path / 'control.db'
    with sqlite3.connect(path) as c:
        c.executescript('''
            CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT);
            CREATE TABLE sessions (id TEXT PRIMARY KEY, owner TEXT, csrf TEXT);
            CREATE TABLE records (id TEXT PRIMARY KEY, owner TEXT, kind TEXT, ref TEXT);
            INSERT INTO users VALUES ('administrator','operator','old-hash');
            INSERT INTO users VALUES ('other','other','other-hash');
            INSERT INTO sessions VALUES ('old','administrator','synthetic-csrf');
            INSERT INTO sessions VALUES ('other-session','other','other-csrf');
            INSERT INTO records VALUES ('doc','administrator','document','documents/doc/original');
            INSERT INTO records VALUES ('model','administrator','model','models/local');
            INSERT INTO records VALUES ('settings','administrator','config_profile','config/local');
        ''')
    original = tmp_path / 'documents/doc/original'
    original.parent.mkdir(parents=True)
    original.write_bytes(b'Synthetic preserved original')
    return path


def snapshot(path):
    with sqlite3.connect(path) as c:
        return {table: c.execute('SELECT * FROM '+table+' ORDER BY 1').fetchall()
                for table in ('users', 'sessions', 'records')}


@pytest.mark.parametrize('wal', [False, True])
def test_backup_atomic_reset_and_preservation(database, wal):
    if wal:
        with sqlite3.connect(database) as c:
            c.execute('PRAGMA journal_mode=WAL')
    before = snapshot(database)
    backup, revoked = r.recover(database, 'operator', PASSWORD, PASSWORD)
    after = snapshot(database)
    assert revoked == 1
    assert snapshot(backup) == before
    assert after['records'] == before['records']
    assert after['users'][0][:2] == before['users'][0][:2]
    assert after['users'][1] == before['users'][1]
    assert after['sessions'] == [before['sessions'][1]]
    assert (database.parent/'documents/doc/original').read_bytes() == b'Synthetic preserved original'
    from app.core import password_valid
    assert password_valid(PASSWORD, after['users'][0][2])
    assert not password_valid('wrong-password', after['users'][0][2])
    if os.name != 'nt':
        assert backup.parent.stat().st_mode & 0o777 == 0o700
        assert backup.stat().st_mode & 0o777 == 0o600
    else:
        acl = subprocess.run(['icacls', str(backup.parent)], capture_output=True, text=True, check=True).stdout
        assert '(I)' not in acl  # no inherited ACL entries


@pytest.mark.parametrize('password,confirmation', [('short','short'), ('x'*201,'x'*201), (PASSWORD,'different')])
def test_invalid_password_no_changes(database, password, confirmation):
    before = snapshot(database)
    with pytest.raises(r.RecoveryError):
        r.recover(database, 'operator', password, confirmation)
    assert snapshot(database) == before
    assert not list(database.parent.glob('password-recovery-*'))


def test_unknown_account_and_missing_database(database):
    before = snapshot(database)
    with pytest.raises(r.RecoveryError):
        r.recover(database, 'missing', PASSWORD, PASSWORD)
    missing = database.parent/'missing.db'
    with pytest.raises(FileNotFoundError):
        r.recover(missing, 'operator', PASSWORD, PASSWORD)
    assert not missing.exists()
    assert snapshot(database) == before


def test_backup_permission_failure_aborts(database, monkeypatch):
    before = snapshot(database)
    def fail(_):
        raise PermissionError('synthetic permission failure')
    monkeypatch.setattr(r, 'private_backup_directory', fail)
    with pytest.raises(PermissionError):
        r.recover(database, 'operator', PASSWORD, PASSWORD)
    assert snapshot(database) == before


def test_locked_database_never_changes_credentials(database, monkeypatch):
    before = snapshot(database)
    blocker = sqlite3.connect(database)
    blocker.execute('BEGIN IMMEDIATE')
    monkeypatch.setattr(r, 'connect_existing', lambda p: sqlite3.connect(p.as_uri()+'?mode=rw', uri=True, timeout=0))
    try:
        with pytest.raises(sqlite3.OperationalError):
            r.recover(database, 'operator', PASSWORD, PASSWORD)
    finally:
        blocker.rollback()
        blocker.close()
    assert snapshot(database) == before


def test_session_revocation_failure_rolls_back_password(database):
    with sqlite3.connect(database) as c:
        c.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON sessions BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    before = snapshot(database)
    with pytest.raises(sqlite3.IntegrityError):
        r.recover(database, 'operator', PASSWORD, PASSWORD)
    assert snapshot(database) == before
    backup = next(database.parent.glob('password-recovery-*/control-before-reset.db'))
    assert snapshot(backup) == before


def test_cli_requires_stopped_services_and_tty(database, monkeypatch, capsys):
    args = ['--database',str(database),'--username','operator']
    assert cli.main(args) == 1
    monkeypatch.setattr(cli, 'check_local_services', lambda: None)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(PASSWORD))
    assert cli.main(args+['--services-stopped']) == 1
    output = capsys.readouterr()
    assert PASSWORD not in output.out + output.err
    assert not list(database.parent.glob('password-recovery-*'))


@pytest.mark.parametrize('mode', ['cancel', 'mismatch', 'warning', 'eof', 'success'])
def test_interactive_prompt_contract(database, monkeypatch, capsys, mode):
    before = snapshot(database)
    monkeypatch.setattr(cli, 'check_local_services', lambda: None)
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: True)
    values = iter([PASSWORD, 'wrong' if mode=='mismatch' else PASSWORD])
    def prompt(_):
        if mode == 'warning':
            cli.warnings.warn('unhidden input', cli.getpass.GetPassWarning)
        if mode == 'eof':
            raise EOFError
        return next(values)
    monkeypatch.setattr(cli.getpass, 'getpass', prompt)
    monkeypatch.setattr('builtins.input', lambda _: 'no' if mode=='cancel' else 'RESET')
    result = cli.main(['--database',str(database),'--username','operator','--services-stopped'])
    assert result == (0 if mode=='success' else 1)
    if mode != 'success':
        assert snapshot(database) == before
    output = capsys.readouterr()
    assert PASSWORD not in output.out + output.err


def test_listening_service_blocks_recovery(monkeypatch):
    class Listening:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def settimeout(self, value): pass
        def connect_ex(self, address): return 0
    monkeypatch.setattr(cli.socket, 'socket', Listening)
    with pytest.raises(r.RecoveryError, match='Stop Aegis'):
        cli.check_local_services()


def test_password_argument_is_not_supported():
    result = subprocess.run([sys.executable,str(SCRIPT),'--help'], capture_output=True,text=True)
    assert result.returncode == 0
    assert '--password' not in result.stdout
    rejected = subprocess.run([sys.executable,str(SCRIPT),'--password',PASSWORD], capture_output=True,text=True)
    assert rejected.returncode == 2
    assert PASSWORD not in rejected.stdout + rejected.stderr
