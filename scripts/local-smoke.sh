#!/usr/bin/env sh
# Development integration check, uses isolated SQLite/file search and explicit mock providers.
# Docker/PostgreSQL/Qdrant and browser interactions are verified separately in CI.
set -eu
cd "$(dirname "$0")/.."
./scripts/setup.sh
set -a
. ./.env
set +a
export AEGIS_STORAGE_ROOT="$(mktemp -d /tmp/aegis-smoke.XXXXXX)"
export MODEL_PROVIDER=mock EMBEDDING_PROVIDER=mock SEARCH_PROVIDER=local AEGIS_ALLOW_MOCK=true
export PYTHONPATH="$PWD/backend"
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 > "$AEGIS_STORAGE_ROOT/api.log" 2>&1 & apid=$!
.venv/bin/python -m app.worker > "$AEGIS_STORAGE_ROOT/worker.log" 2>&1 & workerpid=$!
(cd frontend && API_INTERNAL_URL=http://127.0.0.1:8000 npm run dev -- --port 3000) > "$AEGIS_STORAGE_ROOT/web.log" 2>&1 & webpid=$!
trap 'kill "$apid" "$workerpid" "$webpid" 2>/dev/null || true' EXIT INT TERM
for i in $(seq 1 90); do
  if curl -sSf http://127.0.0.1:3000/api/auth/status >/dev/null 2>&1; then break; fi
  sleep 1
done
if ! AEGIS_SMOKE_NO_DOCKER=true .venv/bin/python scripts/smoke.py; then
  cat "$AEGIS_STORAGE_ROOT/api.log" "$AEGIS_STORAGE_ROOT/worker.log" "$AEGIS_STORAGE_ROOT/web.log"
  exit 1
fi
