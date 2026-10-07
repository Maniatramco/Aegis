#!/usr/bin/env python3
"""Offline SQLite administrator recovery; passwords never accepted as arguments."""
import argparse
import csv
import getpass
import hashlib
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import warnings


class RecoveryError(Exception):
    pass


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unknown arguments, which might be passwords.
        self.exit(2, 'Invalid arguments; use --help. Enter passwords only at hidden prompts.\n')


def validate_password(password, confirmation):
    if not 12 <= len(password) <= 200:
        raise RecoveryError('Use a password of 12 to 200 characters.')
    if password != confirmation:
        raise RecoveryError('Passwords do not match; nothing changed.')


def private_backup_directory(parent):
    directory = Path(tempfile.mkdtemp(prefix='password-recovery-', dir=parent))
    if os.name == 'nt':
        # Restrict the new empty directory BEFORE any sensitive bytes are written.
        result = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'],
                                capture_output=True, text=True, check=True)
        sid = next(csv.reader(result.stdout.splitlines()))[1]
        if not sid.startswith('S-1-'):
            raise RecoveryError('Cannot determine backup owner.')
        subprocess.run(['icacls', str(directory), '/inheritance:r', '/grant:r',
                        f'*{sid}:(OI)(CI)F'], capture_output=True, check=True)
    else:
        directory.chmod(0o700)
    return directory


def connect_existing(path):
    return sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=5)


def recover(database, username, password, confirmation):
    """Caller must stop all API/worker processes, including remote replicas."""
    validate_password(password, confirmation)
    path = Path(database).resolve(strict=True)
    if not path.is_file():
        raise RecoveryError('Database must be an existing SQLite file.')
    salt = secrets.token_hex(16)
    # Matches app.core.password_hash; compatibility is covered by integration tests.
    hashed = salt + ':' + hashlib.scrypt(password.encode(), salt=salt.encode(),
                                       n=16384, r=8, p=1).hex()
    connection = connect_existing(path)
    backup = None
    try:
        connection.execute('BEGIN IMMEDIATE')
        account = connection.execute(
            'SELECT id, username FROM users WHERE id=? AND username=?',
            ('administrator', username)).fetchone()
        if account is None:
            raise RecoveryError('Existing administrator not found; nothing changed.')
        # Validate session schema before backup/update, without reading secrets.
        connection.execute('SELECT owner FROM sessions LIMIT 0')
        directory = private_backup_directory(path.parent)
        backup = directory / 'control-before-reset.db'
        fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        # The IMMEDIATE lock prevents writers. A separate reader backs up the
        # committed pre-reset state without self-deadlocking on the write lock.
        source = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)
        destination = sqlite3.connect(backup)
        try:
            source.backup(destination)
            if destination.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise RecoveryError('Backup verification failed; nothing changed.')
        finally:
            destination.close()
            source.close()
        connection.execute('UPDATE users SET password_hash=? WHERE id=?',
                           (hashed, account[0]))
        revoked = connection.execute('DELETE FROM sessions WHERE owner=?',
                                     (account[0],)).rowcount
        connection.commit()
        return backup, revoked
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def check_local_services():
    for port in (3000, 8000):
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                raise RecoveryError(f'Stop Aegis services first (port {port} is listening).')


def main(argv=None):
    parser = PrivateArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path,
                        help='Exact existing local control.db path; never a database URL')
    parser.add_argument('--username', required=True, help='Existing administrator username')
    parser.add_argument('--services-stopped', action='store_true',
                        help='Confirm ALL Aegis API and worker processes are stopped')
    args = parser.parse_args(argv)
    try:
        if not args.services_stopped:
            raise RecoveryError('Stop all Aegis API/workers, then pass --services-stopped.')
        check_local_services()
        if not sys.stdin.isatty():
            raise RecoveryError('Run in an interactive terminal; piped passwords are refused.')
        if not args.database.is_file():
            raise RecoveryError('Database does not exist; nothing changed.')
        print('Local administrator recovery. Account identity and workspace data are preserved.')
        print('Existing administrator sessions will be revoked. Keep the backup private.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass('New password (12–200 characters): ')
            confirmation = getpass.getpass('Confirm new password: ')
        validate_password(password, confirmation)
        if input('Type RESET to apply this password change: ') != 'RESET':
            raise RecoveryError('Cancelled; nothing changed.')
        backup, revoked = recover(args.database, args.username, password, confirmation)
        print(f'Password changed; {revoked} session(s) revoked. Backup: {backup}')
        print('Restart Aegis and sign in with your new password.')
        return 0
    except RecoveryError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error, subprocess.SubprocessError,
            getpass.GetPassWarning):
        # Do not dump exceptions/SQL/arguments: they might contain credential data.
        print('Recovery not completed. Check stopped services, account/database, password '
              'requirements, and backup permissions. No partial credential update was committed.',
              file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print('\nCancelled; no partial credential update was committed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
