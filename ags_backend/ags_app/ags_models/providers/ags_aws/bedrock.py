from ...validation import ConnectionError
import json
from .agent import payload as agent_payload, complete as agent_complete

def client(connection):
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise ConnectionError('Install ags_backend/requirements-models.txt for native cloud protocols.')
    kwargs = {}
    if connection.c['auth_mode'] == 'aws_keys':
        kwargs = {'aws_access_key_id': connection.secret['access_key_id'], 'aws_secret_access_key': connection.secret['secret_access_key']}
        if connection.secret.get('session_token'):
            kwargs['aws_session_token'] = connection.secret['session_token']
    return boto3.client('bedrock-runtime', region_name=connection.c['region'], endpoint_url=connection.c['endpoint'],
        config=Config(connect_timeout=min(10, connection.timeout), read_timeout=connection.timeout, retries={'total_max_attempts': 1}, proxies={}), **kwargs)


def generate(connection, instruction, text, schema, output_tokens, extra):
    data = connection.bedrock().converse(modelId=connection.model, system=[{'text': instruction}], messages=[{'role': 'user', 'content': [{'text': text}]}], inferenceConfig={'maxTokens': output_tokens, **extra})
    if data.get('stopReason') != 'end_turn':
        raise ConnectionError('Model returned an incomplete or refused response.')
    result = '\n'.join(x['text'] for x in data['output']['message']['content'] if 'text' in x)
    return result


def embed(connection, texts, query, dim, extra):
    client = connection.bedrock()
    fmt = connection.c['embedding_format']
    if fmt == 'titan':
        vectors = []
        for text in texts:
            payload = {'inputText': text, **extra, **({'dimensions': dim} if dim else {})}
            data = json.loads(client.invoke_model(modelId=connection.model, body=json.dumps(payload), contentType='application/json', accept='application/json')['body'].read())
            vectors.append(data['embedding'])
    else:
        payload = {'texts': texts, 'input_type': 'search_query' if query else 'search_document', 'truncate': 'NONE'}
        if fmt == 'cohere-v4':
            payload['embedding_types'] = ['float']
            if dim:
                payload['output_dimension'] = dim
        data = json.loads(client.invoke_model(modelId=connection.model, body=json.dumps(payload), contentType='application/json', accept='application/json')['body'].read())
        vectors = data['embeddings']['float'] if isinstance(data['embeddings'], dict) else data['embeddings']
    return vectors
