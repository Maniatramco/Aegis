from ...validation import ConnectionError
import json
from urllib.parse import quote
from .agent import payload as agent_payload, complete as agent_complete

def headers(connection):
    if connection.c['auth_mode'] == 'bearer_token':
        return {}
    try:
        import google.auth
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        import requests
        scopes = ['https://www.googleapis.com/auth/cloud-platform']
        cred = service_account.Credentials.from_service_account_info(json.loads(connection.secret['service_account']), scopes=scopes) if connection.c['auth_mode'] == 'service_account' else google.auth.default(scopes=scopes)[0]
        session = requests.Session(); session.trust_env = False; session.max_redirects = 0
        request = Request(session=session)
        def bounded_request(*args, **kwargs):
            kwargs['timeout'] = min(30, connection.timeout)
            return request(*args, **kwargs)
        try:
            cred.refresh(bounded_request)
        finally:
            session.close()
        return {'Authorization': 'Bearer ' + cred.token}
    except ImportError:
        raise ConnectionError('Install ags_backend/requirements-models.txt for native cloud protocols.')
    except Exception as exc:
        raise ConnectionError('Server identity or service account authentication failed.') from exc


def path(connection, operation):
    return '/v1/projects/' + quote(connection.c['project_id'], safe='') + '/locations/' + connection.c['region'] + '/publishers/google/models/' + quote(connection.model, safe='') + ':' + operation


def generate(connection, instruction, text, schema, output_tokens, extra):
    data = connection.post(connection.vertex_path('generateContent'), {'systemInstruction': {'parts': [{'text': instruction}]}, 'contents': [{'role': 'user', 'parts': [{'text': text}]}], 'generationConfig': {'maxOutputTokens': output_tokens, **extra, **({'responseMimeType': 'application/json'} if schema else {})}}, connection.vertex_headers())
    candidate = data['candidates'][0]
    if candidate.get('finishReason') != 'STOP':
        raise ConnectionError('Model returned an incomplete or refused response.')
    result = '\n'.join(x['text'] for x in candidate['content']['parts'] if 'text' in x and not x.get('thought'))
    return result


def embed(connection, texts, query, dim, extra):
    vectors = []
    # Some publisher models accept a single input per predict call.
    for text in texts:
        data = connection.post(connection.vertex_path('predict'), {'instances': [{'content': text, 'task_type': 'RETRIEVAL_QUERY' if query else 'RETRIEVAL_DOCUMENT'}], 'parameters': {'autoTruncate': False, **({'outputDimensionality': dim} if dim else {})}}, connection.vertex_headers())
        vectors.append(data['predictions'][0]['embeddings']['values'])
    return vectors
