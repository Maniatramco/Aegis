"""Provision AGS_OWNER privately; never rotate an existing owner's password."""
import argparse
import re
from pathlib import Path
import oracledb

root=Path(__file__).resolve().parents[2]
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=1521)
    p.add_argument('--service',default='FREEPDB1')
    p.add_argument('--admin-password-file',type=Path,default=root/'secrets/oracle/admin-password')
    p.add_argument('--app-password-file',type=Path,default=root/'secrets/oracle/app-password')
    args=p.parse_args();admin=args.admin_password_file.read_text().strip();password=args.app_password_file.read_text().strip()
    if not re.fullmatch(r'[A-Za-z0-9_]{16,64}',password):raise SystemExit('Use the generated private application password file.')
    with oracledb.connect(user='SYSTEM',password=admin,host=args.host,port=args.port,service_name=args.service) as c:
        cursor=c.cursor();cursor.execute('SELECT COUNT(*) FROM dba_users WHERE username=:name',name='AGS_OWNER')
        if not cursor.fetchone()[0]:
            cursor.execute(f'CREATE USER AGS_OWNER IDENTIFIED BY "{password}" DEFAULT TABLESPACE USERS QUOTA 512M ON USERS')
        cursor.execute('GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE TO AGS_OWNER')
    print('AGS_OWNER exists with application privileges. Existing credentials were preserved.')
