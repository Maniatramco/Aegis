"""Database connection and type compatibility; no credentials are logged."""
import os
from pathlib import Path
from sqlalchemy import Float, String
from sqlalchemy.engine import URL, make_url
from sqlalchemy.dialects.oracle import BINARY_DOUBLE
from sqlalchemy.types import TypeDecorator


def database_url(storage_root, environ=None):
    env = os.environ if environ is None else environ
    if env.get('DATABASE_URL'):
        return make_url(env['DATABASE_URL'])
    provider = env.get('DATABASE_PROVIDER', 'sqlite')
    if provider == 'oracle':
        password = env.get('ORACLE_PASSWORD')
        if env.get('ORACLE_PASSWORD_FILE'):
            try:
                password = Path(env['ORACLE_PASSWORD_FILE']).read_text(encoding='utf-8').strip()
            except OSError:
                raise ValueError('Cannot read the configured Oracle password file.') from None
        if not env.get('ORACLE_HOST') or not env.get('ORACLE_USER') or not password:
            raise ValueError('Oracle requires ORACLE_HOST, ORACLE_USER and ORACLE_PASSWORD.')
        try:
            port = int(env.get('ORACLE_PORT', '1521'))
            if not 1 <= port <= 65535:
                raise ValueError()
        except ValueError:
            raise ValueError('ORACLE_PORT must be a valid TCP port.') from None
        return URL.create('oracle+oracledb', username=env['ORACLE_USER'],
                          password=password, host=env['ORACLE_HOST'],
                          port=port, query={'service_name': env.get('ORACLE_SERVICE_NAME', 'FREEPDB1')})
    if provider != 'sqlite':
        raise ValueError('Set DATABASE_URL for this database provider.')
    return URL.create('sqlite', database=str(storage_root / 'control.db'))


def engine_options(url):
    options = {'pool_pre_ping': True}
    if make_url(url).get_backend_name() == 'sqlite':
        options['connect_args'] = {'check_same_thread': False}
    return options


class StoredString(TypeDecorator):
    """Preserve empty strings despite Oracle treating '' as NULL.

    Only columns that allow an empty application value use this type. A reserved
    control marker encodes empty strings; literal markers are escaped reversibly.
    SQLite/PostgreSQL values and schemas remain ordinary VARCHAR strings.
    """
    impl = String
    cache_ok = True
    marker = '\x01'

    def load_dialect_impl(self, dialect):
        # Reserve one extra character for escaping without truncating a value.
        length = self.impl.length
        return dialect.type_descriptor(String(length + 1 if dialect.name == 'oracle' and length else length))

    def process_bind_param(self, value, dialect):
        if dialect.name == 'oracle' and value is not None:
            if value == '' or value.startswith(self.marker):
                return self.marker + value
        return value

    def process_result_value(self, value, dialect):
        if dialect.name == 'oracle' and value and value.startswith(self.marker):
            return value[1:]
        return value


def timestamp_type():
    # Eight-byte FP values preserve fractional epoch seconds and job leases.
    return Float().with_variant(BINARY_DOUBLE(), 'oracle')
