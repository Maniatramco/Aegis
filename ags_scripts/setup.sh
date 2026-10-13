#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
if [ -e .env ]; then
  printf '%s\n' '.env already exists; leaving your configuration untouched.'
  exit 0
fi
umask 077
python3 - <<'PY'
import base64, secrets
from pathlib import Path
text = Path('.env.example').read_text()
for name, value in {
    'CHANGE_ME_MASTER_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    'CHANGE_ME_SESSION_SECRET': secrets.token_urlsafe(48),
    'CHANGE_ME_DATABASE_PASSWORD': secrets.token_hex(24),
    'CHANGE_ME_BOOTSTRAP_TOKEN': secrets.token_urlsafe(32),
}.items():
    text = text.replace(name, value)
Path('.env').write_text(text)
Path('.env').chmod(0o600)
print('Created .env with unique local secrets. Keep it private and back it up separately.')
PY
