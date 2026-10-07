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


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app import password_recovery as recovery
from app.password_recovery import RecoveryError, PrivateArgumentParser, validate_password, recover


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
