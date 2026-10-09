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


def recover(database, username, password, confirmation, *, grant_token=None):
    """Offline callers stop services; web redemption holds administrator-auth lock."""
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
        account = grant_account(connection, grant_token) if grant_token else connection.execute(
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
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='recovery_grants'").fetchone():
            connection.execute('DELETE FROM recovery_grants WHERE owner=?',(account[0],))
        connection.commit()
        return backup, revoked
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()



def issue_grant(database, username):
    """Trusted operator only: raw capability is returned in memory, never logged."""
    import time
    path=Path(database).resolve(strict=True)
    connection=connect_existing(path)
    try:
        connection.execute('BEGIN IMMEDIATE')
        account=connection.execute('SELECT id FROM users WHERE id=? AND username=?',('administrator',username)).fetchone()
        if not account:raise RecoveryError('Existing administrator not found.')
        connection.execute('CREATE TABLE IF NOT EXISTS recovery_grants (id TEXT PRIMARY KEY, owner TEXT NOT NULL, expires REAL NOT NULL)')
        connection.execute('DELETE FROM recovery_grants WHERE owner=? OR expires<=?',(account[0],time.time()))
        token=secrets.token_urlsafe(32)
        connection.execute('INSERT INTO recovery_grants VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),account[0],time.time()+300))
        connection.commit()
        return token
    except BaseException:
        connection.rollback();raise
    finally:connection.close()


def grant_account(connection, token):
    import time
    try:
        row=connection.execute('SELECT u.id,u.username FROM recovery_grants g JOIN users u ON u.id=g.owner WHERE g.id=? AND g.expires>? AND u.id=?',
             (hashlib.sha256(token.encode()).hexdigest(),time.time(),'administrator')).fetchone()
    except sqlite3.Error:
        row=None
    if not row:raise RecoveryError('This recovery link is invalid or expired. Open a new private link.')
    return row


def grant_username(database,token):
    connection=connect_existing(Path(database).resolve(strict=True))
    try:return grant_account(connection,token)[1]
    finally:connection.close()


def revoke_grant(database,token):
    connection=connect_existing(Path(database).resolve(strict=True))
    try:
        connection.execute('DELETE FROM recovery_grants WHERE id=?',(hashlib.sha256(token.encode()).hexdigest(),))
        connection.commit()
    finally:connection.close()
