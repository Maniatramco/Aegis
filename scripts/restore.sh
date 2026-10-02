#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
if [ "$#" -ne 2 ] || [ "$2" != '--confirm-overwrite' ]; then
  echo 'Usage: scripts/restore.sh BACKUP_DIRECTORY --confirm-overwrite' >&2
  echo 'Restores into the active Compose deployment. Existing control records/files are replaced.' >&2
  exit 2
fi
source="$(cd "$1" && pwd)"
test -f "$source/control.dump"
test -f "$source/storage.tar.gz"
docker compose exec -T api python -c 'from app.core import settings; assert settings().get("storage_provider", "local") == "local", "Local restore cannot replace an OCI storage deployment. Switch to a fresh local target first."'
docker compose stop web api worker
echo 'Writers stopped. Restoring; they remain stopped if any command fails.'
docker compose exec -T db sh -c 'pg_restore --clean --if-exists --no-owner --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$source/control.dump"
docker compose run --rm --no-deps -T --entrypoint python api -c '
import sys, tarfile, shutil
from pathlib import Path
root = Path("/data")
for p in root.iterdir():
    shutil.rmtree(p) if p.is_dir() else p.unlink()
with tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz") as archive:
    archive.extractall("/", filter="data")
' < "$source/storage.tar.gz"
echo 'Restored. Use the matching original .env/master key, then docker compose start api worker web.'
echo 'Reindex all documents through the UI to rebuild Qdrant before asking questions.'
