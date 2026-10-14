"""Public provider choices backed by the fixed execution protocol registry."""
from .provider_registry import AUTH_MODES

PROVIDERS = (
    ('ollama', 'Local · Ollama', 'ollama', 'http://127.0.0.1:11435'),
    ('openai', 'OpenAI', 'openai-compatible', 'https://api.openai.com/v1'),
    ('gemini', 'Google · Gemini API', 'openai-compatible', 'https://generativelanguage.googleapis.com/v1beta/openai'),
    ('azure-openai', 'Azure · OpenAI v1', 'azure-openai', ''),
    ('bedrock', 'AWS · Bedrock', 'bedrock', 'https://bedrock-runtime.us-east-1.amazonaws.com'),
    ('vertex', 'Google Cloud · Vertex AI', 'vertex', 'https://us-central1-aiplatform.googleapis.com'),
    ('oci', 'Oracle Cloud · Generative AI', 'oci', 'https://inference.generativeai.us-chicago-1.oci.oraclecloud.com'),
    ('openai-compatible', 'Other · OpenAI-compatible API', 'openai-compatible', ''),
)


def choices():
    return [{'id': id, 'name': name, 'protocol': protocol, 'endpoint': endpoint,
             'region': {'bedrock': 'us-east-1', 'vertex': 'us-central1', 'oci': 'us-chicago-1'}.get(protocol, ''),
             'auth_modes': list(AUTH_MODES[protocol]), 'categories': ['chat', 'extraction', 'embedding']}
            for id, name, protocol, endpoint in PROVIDERS]
