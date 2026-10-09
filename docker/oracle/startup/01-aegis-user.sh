#!/usr/bin/env bash
# Startup scripts also run when the official image reuses its prebuilt database.
set -eu
for task_user in AEGIS AEGIS_TEST; do
if [[ "$task_user" == AEGIS ]]; then
  task_password=$(cat /run/secrets/aegis_oracle_password)
  task_quota=512M
else
  task_password=$(cat /run/secrets/aegis_oracle_test_password)
  task_quota=128M
fi
if [[ ! "$task_password" =~ ^[A-Za-z0-9_]{16,64}$ ]]; then
  echo 'Aegis database password must contain 16–64 letters, digits or underscores.' >&2
  exit 1
fi
if ! sqlplus -s / as sysdba >/dev/null 2>&1 <<SQL
whenever sqlerror exit failure rollback
set echo off verify off feedback off
alter session set container = FREEPDB1;
declare
  user_count number;
begin
  select count(*) into user_count from dba_users where username = '$task_user';
  if user_count = 0 then
    execute immediate 'create user $task_user identified by "$task_password" default tablespace USERS quota $task_quota on USERS';
  end if;
end;
/
grant create session, create table, create sequence to $task_user;
exit success
SQL
then
  echo 'Aegis database account setup failed; check the database and secret configuration.' >&2
  exit 1
fi
unset task_password
done
