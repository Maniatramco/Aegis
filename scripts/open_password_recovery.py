#!/usr/bin/env python3
"""Trusted local operator opens a private, single-use browser password reset."""
import argparse
from pathlib import Path
import sys
import webbrowser

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app import password_recovery


def main(argv=None):
    parser=password_recovery.PrivateArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--username',required=True)
    args=parser.parse_args(argv)
    token=None
    try:
        token=password_recovery.issue_grant(args.database,args.username)
        # Fragment is never sent in HTTP access logs; the page immediately removes
        # it from the address/history. Never print or persist the raw capability.
        if not webbrowser.open('http://127.0.0.1:3000/recover-password#recovery='+token,new=2):
            raise RuntimeError('Browser unavailable')
        print('Private recovery page opened. The link expires in five minutes and works once.')
        print('The account owner must enter and submit the new password privately in the browser.')
        return 0
    except Exception:
        if token:
            password_recovery.revoke_grant(args.database,token)
        print('Could not open private recovery. Check the existing database, username and local browser.',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
