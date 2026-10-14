from ...validation import ConnectionError
def generate(connection, instruction, text, schema, output_tokens, extra):
    payload = {'model': connection.model, 'messages': [{'role': 'system', 'content': instruction}, {'role': 'user', 'content': text}], 'max_completion_tokens': output_tokens, **extra}
    if schema and connection.c.get('structured_output', True):
        payload['response_format'] = {'type': 'json_schema', 'json_schema': {'name': 'extraction', 'schema': schema, 'strict': True}}
    data = connection.post('/chat/completions', payload)
    choice = data['choices'][0]
    if choice.get('finish_reason') not in ('stop',):
        raise ConnectionError('Model returned an incomplete or refused response.')
    result = choice['message']['content']
    return result


def embed(connection, texts, query, dim, extra, restore_zero_index=False):
    data = connection.post('/embeddings', {'model': connection.model, 'input': texts, **extra, **({'dimensions': dim} if dim else {})})
    rows = data['data']
    # Google's protobuf JSON omits the default index value (zero).
    # Only restore that default for its fixed Gemini API host;
    # duplicate/missing later indices still fail the order check.
    if restore_zero_index:
        rows = [{"index": 0, **row} for row in rows]
    rows = sorted(rows, key=lambda x: x['index'])
    if [x['index'] for x in rows] != list(range(len(texts))):
        raise ConnectionError('Model returned an invalid embedding order.')
    vectors = [x['embedding'] for x in rows]
    return vectors
