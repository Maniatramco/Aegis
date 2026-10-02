#!/usr/bin/env sh
# Stop app writers while taking a consistent control database + storage snapshot.
set -eu
cd "$(dirname "$0")/.."
destination="${1:-backups/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$destination"
chmod 700 "$destination"
destination="$(cd "$destination" && pwd)"
docker compose exec -T api python -c 'from app.core import settings; assert settings().get("storage_provider", "local") == "local", "This backup script supports local storage only. Snapshot OCI objects separately."'
docker compose stop web api worker
trap 'docker compose start api worker web >/dev/null' EXIT INT TERM
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$destination/control.dump"
docker compose run --rm --no-deps -T --entrypoint python api -c 'import tarfile; t=tarfile.open(fileobj=__import__("sys").stdout.buffer,mode="w|gz"); t.add("/data",arcname="data",filter=lambda item: None if item.name == "data/model-cache" or item.name.startswith("data/model-cache/") else item); t.close()' > "$destination/storage.tar.gz"
printf '%s\n' 'Rebuild Qdrant indexes after restore. Keep the original .env/master key separately.' > "$destination/README.txt"
printf 'Backup created: %s\n' "$destination"
