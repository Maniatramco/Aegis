#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo 'Install Docker Engine/Desktop first.' >&2; exit 1; }
docker info >/dev/null
docker run --rm --user "$(id -u):$(id -g)" --mount "type=bind,source=$PWD,target=/workspace" \
  python:3.12-slim python /workspace/scripts/setup_oracle.py
docker compose --env-file .env.oracle -f compose.oracle.yaml config --quiet
docker compose --env-file .env.oracle -f compose.oracle.yaml up --build -d --wait --wait-timeout 1200
if [ "$(sed -n 's/^MODEL_PROVIDER=//p' .env.oracle)" = ollama ]; then
  for key in AEGIS_MODEL EMBEDDING_MODEL; do
    model=$(sed -n "s/^${key}=//p" .env.oracle)
    test -n "$model"
    docker compose --env-file .env.oracle -f compose.oracle.yaml exec -T ollama ollama pull "$model"
  done
fi
printf '%s\n' 'Oracle containers are ready. Open http://localhost:3003 (or your configured port).'
printf '%s\n' 'Use first-account setup in the app, or the operator account-provisioning command in docs/ORACLE.md.'
