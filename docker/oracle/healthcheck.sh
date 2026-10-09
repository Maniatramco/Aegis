#!/usr/bin/env bash
set -eu
task_password=$(cat /run/secrets/aegis_oracle_password)
# A ready database must accept the application account, not just open its PDB.
# Credentials go to stdin and neither SQL*Plus output nor passwords are logged.
sqlplus -s /nolog >/dev/null 2>&1 <<SQL
whenever oserror exit failure
whenever sqlerror exit failure rollback
connect AEGIS/"$task_password"@//localhost:1521/FREEPDB1
select 1 from dual;
exit success
SQL
unset task_password
