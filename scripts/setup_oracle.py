"""Generate a fresh private Oracle configuration; also runs in a helper container."""
import argparse
import base64
import os
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]


def prepare(root, env_file='.env.oracle', secret_dir='secrets/oracle', port=3003):
    root = Path(root).resolve()
    config = (root / env_file).resolve()
    directory = (root / secret_dir).resolve()
    if root not in config.parents or root not in directory.parents:
        raise ValueError('Configuration and secrets must be inside the project directory.')
    if not 1 <= port <= 65535:
        raise ValueError('Choose a port between 1 and 65535.')
    paths = [directory / 'admin-password', directory / 'app-password', directory / 'test-password']
    relative = directory.relative_to(root).as_posix()
    if '\n' in relative or '\r' in relative or '$' in relative or '"' in relative:
        raise ValueError('Choose a simple path for the secret directory.')
    if config.exists():
        if not all(path.is_file() for path in paths):
            raise ValueError('Existing configuration has missing password files. Restore them; credentials were not regenerated.')
        # Secret files are mounted into Linux shells; CRLF leaves a literal CR
        # in command substitution. Normalize terminators without rotating keys.
        for path in paths:
            value = path.read_bytes()
            normalized = value.replace(b'\r\n', b'\n')
            if normalized != value:
                mode = path.stat().st_mode & 0o777
                try:
                    os.chmod(path, mode | 0o200)
                    path.write_bytes(normalized)
                finally:
                    os.chmod(path, mode)
        return False
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('The secret directory is not empty. Choose a new directory or restore its matching configuration.')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    for path in paths:
        with path.open('x', encoding='utf-8', newline='\n') as handle:
            # Compose binds secret files without remapping their owner. The
            # private parent directory blocks other host users; readable leaf
            # files let the non-root API/Oracle users read their mounted secret.
            os.chmod(path, 0o600 if os.name == 'nt' else 0o444)
            handle.write('Ag1_' + secrets.token_hex(24) + '\n')
    source = (root / '.env.oracle.example').read_text(encoding='utf-8')
    source = source.replace('CHANGE_ME_MASTER_KEY', base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
    source = source.replace('CHANGE_ME_BOOTSTRAP_TOKEN', secrets.token_urlsafe(32))
    source = source.replace('AEGIS_PORT=3003', f'AEGIS_PORT={port}')
    source = source.replace('http://localhost:3003', f'http://localhost:{port}')
    source = source.replace('AEGIS_ORACLE_SECRET_DIR=./secrets/oracle', f'AEGIS_ORACLE_SECRET_DIR="./{relative}"')
    with config.open('x', encoding='utf-8', newline='\n') as handle:
        os.chmod(config, 0o600)
        handle.write(source)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', default='.env.oracle')
    parser.add_argument('--secret-dir', default='secrets/oracle')
    parser.add_argument('--port', type=int, default=3003)
    args = parser.parse_args()
    try:
        changed = prepare(ROOT, args.env_file, args.secret_dir, args.port)
        print('Created private Oracle configuration.' if changed else 'Using existing Oracle configuration; credentials were preserved.')
    except (ValueError, OSError) as error:
        parser.exit(1, f'Oracle setup could not complete: {error}\n')


if __name__ == '__main__':
    main()
