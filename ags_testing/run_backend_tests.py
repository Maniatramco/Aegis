"""Run pytest with disposable local state; never inherit live cloud settings."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ('AEGIS_', 'ORACLE_', 'OCI_', 'OPENAI_', 'AZURE_', 'AWS_', 'GOOGLE_',
            'EMBEDDING_', 'MODEL_', 'QDRANT_', 'DATABASE_')
PRIVATE_SETTINGS = {'MASTER_KEY', 'DATA_DIR', 'ALLOWED_ORIGINS', 'API_INTERNAL_URL', 'PYTHONPATH'}

def main():
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(PREFIXES) and key not in PRIVATE_SETTINGS}
    with tempfile.TemporaryDirectory(prefix='aegis-tests-') as directory:
        state = Path(directory)
        env.update({
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
            'PYTHONPATH': str(ROOT / 'ags_backend'), 'AEGIS_STORAGE_ROOT': str(state),
            'DATA_DIR': str(state), 'DATABASE_PROVIDER': 'sqlite',
            'DATABASE_URL': 'sqlite:///' + (state / 'test.db').as_posix(),
            'AEGIS_ALLOW_MOCK': 'true', 'MODEL_PROVIDER': 'mock',
            'EMBEDDING_PROVIDER': 'mock', 'SEARCH_PROVIDER': 'local', 'STORAGE_PROVIDER': 'local',
        })
        command = [sys.executable, '-B', '-m', 'pytest', '-c', str(ROOT / 'ags_testing/pytest.ini'),
                   '-q', '-p', 'no:cacheprovider', '--basetemp', str(state / 'pytest'), *sys.argv[1:]]
        return subprocess.call(command, cwd=ROOT / 'ags_testing', env=env)

if __name__ == '__main__':
    raise SystemExit(main())
