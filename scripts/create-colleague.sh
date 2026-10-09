#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
read -r -p 'Colleague Aegis username: ' task_username
read -r -s -p 'Colleague Aegis password (12–200 characters): ' task_password
printf '\n'
# Input is a NUL-separated stream; neither credentials appear in process argv.
printf '%s\0%s' "$task_username" "$task_password" |
  docker run --rm -i python:3.12-slim python -c 'import sys,json; u,p=sys.stdin.buffer.read().split(b"\0",1); print(json.dumps({"username":u.decode(),"password":p.decode()}))' |
  docker compose --env-file .env.oracle -f compose.oracle.yaml exec -T api python -m app.provision_account
unset task_username task_password
