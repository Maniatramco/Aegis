"""Run database integration tests against the isolated AEGIS_TEST schema."""
import os
import sys
from pathlib import Path
import pytest
from app.database import database_url


if __name__ == '__main__':
    if '--real-models' in sys.argv:
        from oracle_model_check import run
        run()
        raise SystemExit(0)
    url = database_url(Path('/tmp/aegis-oracle-test'))
    if url.get_backend_name() != 'oracle' or url.username != 'AEGIS_TEST':
        raise SystemExit('Use the dedicated AEGIS_TEST schema, not application credentials.')
    # Kept inside this process, never emitted to logs or command-line arguments.
    os.environ['AEGIS_TEST_ORACLE_URL'] = url.render_as_string(hide_password=False)
    raise SystemExit(pytest.main(['backend/tests/test_oracle_database.py', '-q']))
