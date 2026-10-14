"""Fixed provider dispatch; saved protocol IDs and endpoints remain stable."""
from importlib import import_module
from urllib.parse import urlsplit

REGISTRY = {
    'ollama': ('ags_local.native', ('none',)),
    'openai-compatible': ('ags_openai.adapter', ('api_key', 'bearer_token')),
    'azure-openai': ('ags_azure.adapter', ('api_key', 'bearer_token')),
    'bedrock': ('ags_aws.bedrock', ('aws_keys', 'server_identity')),
    'vertex': ('ags_gcp.vertex', ('service_account', 'server_identity', 'bearer_token')),
    'oci': ('ags_oci.native', ('oci_credentials', 'server_identity', 'config_profile')),
}
PROTOCOLS = tuple(REGISTRY)
AUTH_MODES = {name: value[1] for name, value in REGISTRY.items()}


def provider(connection):
    from .validation import ConnectionError
    protocol = connection['protocol']
    if protocol not in REGISTRY:
        raise ConnectionError('Choose a supported connection protocol.')
    module = REGISTRY[protocol][0]
    if protocol == 'openai-compatible' and urlsplit(connection['endpoint']).hostname == 'generativelanguage.googleapis.com':
        module = 'ags_gcp.gemini'
    return import_module('.providers.' + module, __package__)
