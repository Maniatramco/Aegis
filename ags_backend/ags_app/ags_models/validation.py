"""Model protocol adapters shared by connection tests and dataset execution.

Connection metadata is public; credentials are loaded only inside a pinned
execution context. No provider automatically falls back to another protocol.
"""
import ipaddress
import json
import math
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urlsplit

from .. import core
from .provider_registry import PROTOCOLS, AUTH_MODES


class ConnectionError(RuntimeError):
    pass


_temporary_credentials = ContextVar('model_test_credentials', default=None)


@contextmanager
def temporary_credentials(secret):
    """Use probe credentials in this call only, without saving them in settings."""
    token = _temporary_credentials.set(dict(secret))
    try:
        yield
    finally:
        _temporary_credentials.reset(token)




def validate_endpoint(endpoint, protocol):
    """Known service hosts, plus explicitly allowed corporate gateway hosts."""
    try:
        parsed = urlsplit(endpoint)
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError()
        host = parsed.hostname.lower()
        port = parsed.port
    except ValueError:
        raise ConnectionError('Enter a base endpoint URL without credentials, query parameters, or a fragment.')
    if protocol == 'ollama':
        internal = {h.strip().lower() for h in os.getenv('AEGIS_OLLAMA_ENDPOINT_HOSTS', '').split(',') if h.strip()}
        if parsed.scheme != 'http' or host not in ({'127.0.0.1', 'localhost', '::1'} | internal) or port not in (11434, 11435) or parsed.path.strip('/'):
            raise ConnectionError('Ollama requires a loopback or server-approved container endpoint on port 11434 or 11435.')
        return endpoint.rstrip('/')
    if parsed.scheme != 'https' or port not in (None, 443):
        raise ConnectionError('Remote model endpoints require HTTPS on port 443.')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ConnectionError('Use the service DNS hostname, not an IP address.')
    if protocol == 'anthropic':
        if host != 'api.anthropic.com' or parsed.path.rstrip('/') != '/v1':
            raise ConnectionError('Direct Claude requires https://api.anthropic.com/v1 as its base endpoint.')
        return 'https://api.anthropic.com/v1'
    allowed = {h.strip().lower() for h in os.getenv('AEGIS_MODEL_ENDPOINT_HOSTS', '').split(',') if h.strip()}
    known = {
        'openai-compatible': host in ('api.openai.com', 'generativelanguage.googleapis.com') or host.endswith('.openai.azure.com') or host.endswith('.generativeai.oci.oraclecloud.com'),
        'azure-openai': host.endswith('.openai.azure.com') or host.endswith('.services.ai.azure.com'),
        'bedrock': bool(re.fullmatch(r'bedrock-runtime\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?', host)),
        'vertex': host == 'aiplatform.googleapis.com' or bool(re.fullmatch(r'[a-z0-9-]+-aiplatform\.googleapis\.com', host)),
        'oci': bool(re.fullmatch(r'inference\.generativeai\.[a-z0-9-]+\.oci\.oraclecloud\.com', host)),
    }
    if not known.get(protocol) and host not in allowed:
        raise ConnectionError('Endpoint host is not approved. Add a custom gateway hostname to AEGIS_MODEL_ENDPOINT_HOSTS on the server first.')
    if protocol in ('bedrock', 'vertex', 'oci') and parsed.path.strip('/'):
        raise ConnectionError('For this protocol enter the service base URL, without an operation path.')
    if protocol == 'azure-openai' and parsed.path.rstrip('/') != '/openai/v1':
        raise ConnectionError('Use the Azure v1 base endpoint ending in /openai/v1/.')
    return endpoint.rstrip('/')


def validate_connection(connection, category, model):
    c = dict(connection)
    protocol = c.get('protocol')
    if protocol not in PROTOCOLS:
        raise ConnectionError('Choose a supported connection protocol.')
    if protocol != 'anthropic':
        c.pop('workspace_id', None)
    if c.get('auth_mode') not in AUTH_MODES[protocol]:
        raise ConnectionError('This authentication method is not supported by the selected protocol.')
    c['endpoint'] = validate_endpoint(c.get('endpoint', ''), protocol)
    if not model.strip() or len(model) > 200 or any(ord(char) < 32 for char in model):
        raise ConnectionError('Enter a valid model or deployment ID.')
    if protocol == 'anthropic':
        if category != 'chat':
            raise ConnectionError('Direct Claude supports Chat registrations only. Keep a separate Embedding and Extraction model.')
        if c.get('workspace_id') and not re.fullmatch(r'wrkspc_[A-Za-z0-9_-]{1,120}', c['workspace_id']):
            raise ConnectionError('Enter a valid Anthropic workspace ID beginning with wrkspc_, or leave it empty for a workspace-scoped key.')
    if protocol == 'ollama':
        from .providers.ags_local.ollama import local_model_name, OllamaError
        try:
            local_model_name(model)
        except OllamaError as exc:
            raise ConnectionError(str(exc)) from exc
    if protocol in ('bedrock', 'vertex', 'oci') and not re.fullmatch(r'[a-z0-9-]{2,64}', c.get('region', '')):
        raise ConnectionError('Enter the service region or location.')
    if protocol == 'bedrock':
        host = urlsplit(c['endpoint']).hostname
        if host.startswith('bedrock-runtime.') and host.split('.')[1] != c['region']:
            raise ConnectionError('Endpoint region must match the configured region.')
        if category == 'embedding' and c.get('embedding_format') not in ('titan', 'cohere-v3', 'cohere-v4'):
            raise ConnectionError('Choose the native embedding request format: Titan, Cohere v3, or Cohere v4.')
    if protocol == 'vertex':
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}', c.get('project_id', '')):
            raise ConnectionError('Enter a valid project ID.')
        host = urlsplit(c['endpoint']).hostname
        expected = 'aiplatform.googleapis.com' if c['region'] == 'global' else c['region'] + '-aiplatform.googleapis.com'
        if host.endswith('googleapis.com') and host != expected:
            raise ConnectionError('Endpoint location must match the configured location.')
        if '/' in model or ':' in model:
            raise ConnectionError('For Vertex enter the publisher model ID, without a resource path or operation suffix.')
    if protocol == 'oci':
        if not re.fullmatch(r'ocid1\.compartment\.[A-Za-z0-9._-]+', c.get('compartment_id', '')):
            raise ConnectionError('Enter the OCI compartment OCID.')
        if urlsplit(c['endpoint']).hostname != 'inference.generativeai.' + c['region'] + '.oci.oraclecloud.com':
            raise ConnectionError('OCI inference endpoint must match the selected region.')
        if category != 'embedding' and c.get('chat_format') not in ('generic', 'cohere'):
            raise ConnectionError('Choose the native chat request format: Generic or Cohere.')
    return c


def validate_credentials(c, credentials):
    mode = c['auth_mode']
    required = {
        'api_key': ('api_key',), 'bearer_token': ('token',),
        'aws_keys': ('access_key_id', 'secret_access_key'),
        'service_account': ('service_account',),
        'oci_credentials': ('tenancy', 'user', 'fingerprint', 'key_content'),
    }.get(mode, ())
    if any(not isinstance(credentials.get(key), str) or not credentials[key].strip() for key in required):
        raise ConnectionError('Supply all credentials required by the selected authentication method.')
    if mode == 'service_account':
        try:
            value = json.loads(credentials['service_account'])
            if value.get('type') != 'service_account' or not value.get('private_key') or not value.get('client_email') or value.get('token_uri') != 'https://oauth2.googleapis.com/token':
                raise ValueError()
        except (ValueError, AttributeError):
            raise ConnectionError('Enter a valid service account JSON document using the Google OAuth token endpoint.')
    if mode == 'config_profile' and not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', c.get('profile', 'DEFAULT')):
        raise ConnectionError('Enter a valid server credential profile name.')


def credentials():
    override = _temporary_credentials.get()
    if override is not None:
        return dict(override)
    raw = core.execution_secret('connection')
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        raise ConnectionError('Saved credentials cannot be read. Register a new credential version.')
