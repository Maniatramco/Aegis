#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/../.."
command -v docker >/dev/null || { echo 'Install Docker Engine/Desktop first.' >&2; exit 1; }
docker info >/dev/null
docker run --rm --user "$(id -u):$(id -g)" --mount "type=bind,source=$PWD,target=/workspace" \
  python:3.12-slim python /workspace/local/ags_scripts/setup_oracle.py
# Auto probes the container, not just the host. CPU never needs GPU tooling.
hardware=${AEGIS_HARDWARE:-auto}
case "$hardware" in auto|cpu|gpu) ;; *) echo 'AEGIS_HARDWARE must be auto, cpu or gpu.' >&2; exit 1;; esac
set -- --env-file .env.oracle -f local/compose.oracle.yaml
image=$(docker compose --project-directory . "$@" config --images | sed -n '/^ollama\/ollama:/p' | head -n 1)
test -n "$image"
docker image inspect "$image" >/dev/null 2>&1 || docker pull "$image"
selected=cpu
if [ "$hardware" != cpu ]; then
  if docker run --rm --gpus all --entrypoint nvidia-smi "$image" --query-gpu=name --format=csv,noheader >/dev/null 2>&1; then
    selected=gpu
    set -- "$@" -f local/compose.gpu.yaml
  elif [ "$hardware" = gpu ]; then
    echo 'Docker cannot access an NVIDIA GPU. Use auto or cpu.' >&2; exit 1
  fi
fi
printf 'Model hardware selected: %s (actual inference checked below).\n' "$selected"
docker compose --project-directory . "$@" config --quiet
if ! docker compose --project-directory . "$@" up --build -d --wait --wait-timeout 1200; then
  if [ "$hardware" = auto ] && [ "$selected" = gpu ]; then
    echo 'GPU startup failed; retrying CPU with the same data volumes.'
    set -- --env-file .env.oracle -f local/compose.oracle.yaml
    docker compose --project-directory . "$@" up --build -d --wait --wait-timeout 1200
  else exit 1; fi
fi
if [ "$(sed -n 's/^MODEL_PROVIDER=//p' .env.oracle)" = ollama ]; then
  for key in AEGIS_MODEL EMBEDDING_MODEL AEGIS_OCR_MODEL; do
    if [ "$key" = AEGIS_OCR_MODEL ] && [ "$(sed -n 's/^AEGIS_OCR_ENABLED=//p' .env.oracle)" = false ]; then continue; fi
    model=$(sed -n "s/^${key}=//p" .env.oracle)
    if [ "$key" = AEGIS_OCR_MODEL ] && [ -z "$model" ]; then model=qwen2.5vl:3b; fi
    test -n "$model"
    docker compose --project-directory . "$@" exec -T ollama ollama pull "$model"
  done
  if ! docker compose --project-directory . "$@" exec -T api python -m ags_app.container_smoke; then
    if [ "$hardware" = auto ] && [ "$selected" = gpu ]; then
      echo 'GPU inference smoke failed; checking CPU with the same models and volumes.'
      set -- --env-file .env.oracle -f local/compose.oracle.yaml
      docker compose --project-directory . "$@" up -d --no-deps --wait --wait-timeout 300 ollama
      docker compose --project-directory . "$@" exec -T api python -m ags_app.container_smoke
    else exit 1; fi
  fi
fi
printf '%s\n' 'Oracle containers are ready. Open http://localhost:3003 (or your configured port).'
printf '%s\n' 'Use first-account setup in the app, or the operator account-provisioning command in ags_docs/ORACLE.md.'
