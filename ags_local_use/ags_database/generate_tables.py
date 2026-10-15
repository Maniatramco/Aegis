"""Generate local Oracle Free DDL from API models; outputs stay in ags_local_use."""
import os
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
local_database=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'ags_backend'))
# Select Oracle metadata only; do not inherit an operator's live connection URL.
os.environ['DATABASE_URL']='oracle+oracledb://'
from ags_app import core
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import oracle

directory=local_database/'ags_tables';directory.mkdir(parents=True,exist_ok=True)
includes=[]
existing={file.stem[3:]:file.name for file in directory.glob('[0-9][0-9]_*.sql')}
next_number=max((int(name[:2]) for name in existing.values()),default=0)+1
for table in core.Base.metadata.sorted_tables:
    name=existing.get(table.name)
    if not name:name=f'{next_number:02d}_{table.name}.sql';next_number+=1
    includes.append('@@ags_tables/'+name)
    ddl=str(CreateTable(table).compile(dialect=oracle.dialect())).strip()+';\n'
    ddl+='\n'.join(str(CreateIndex(index).compile(dialect=oracle.dialect()))+';' for index in sorted(table.indexes,key=lambda i:i.name))+'\n'
    (directory/name).write_text('-- Generated from ags_backend/ags_app/core.py and relational.py. Run as AGS_OWNER on an empty schema.\n'+ddl,encoding='utf-8')
(local_database/'install.sql').write_text('set echo off\nwhenever sqlerror exit failure rollback\n-- Connect as AGS_OWNER in FREEPDB1 before running. DDL commits in Oracle.\n'+ '\n'.join(includes)+'\n',encoding='utf-8')
print(f'Generated {len(includes)} table scripts.')
