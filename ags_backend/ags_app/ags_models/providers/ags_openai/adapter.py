import copy
from urllib.parse import urlsplit
from jsonschema import validate, ValidationError
from ...validation import ConnectionError


def strict_routes(connection):
    return connection is None or connection.get('protocol') == 'azure-openai' or urlsplit(connection.get('endpoint', '')).hostname == 'api.openai.com'


def strict_schema(schema):
    """Represent optional fields as nullable wire values, never local defaults."""
    result = copy.deepcopy(schema)
    if 'const' in result:
        result['enum'] = [result.pop('const')]
    if 'enum' in result and 'type' not in result:
        kinds = {type(v) for v in result['enum']}
        types = {str: 'string', bool: 'boolean', int: 'integer', float: 'number', type(None): 'null', list: 'array', dict: 'object'}
        if len(kinds) == 1:
            result['type'] = types[next(iter(kinds))]
    # Retain unsupported generation constraints in canonical local validation.
    result.pop('uniqueItems', None)
    if result.get('type') == 'object':
        required = set(schema.get('required', []))
        properties = {}
        for name, value in schema.get('properties', {}).items():
            normalized = strict_schema(value)
            properties[name] = normalized if name in required else {'anyOf': [normalized, {'type': 'null'}]}
        result.update(properties=properties, required=list(properties), additionalProperties=False)
    elif result.get('type') == 'array' and 'items' in result:
        result['items'] = strict_schema(result['items'])
    for keyword in ('anyOf', 'oneOf'):
        if keyword in result:
            result['anyOf'] = [strict_schema(value) for value in result.pop(keyword)]
    return result


def canonical_arguments(value, schema):
    if isinstance(value, dict) and schema.get('type') == 'object':
        required = set(schema.get('required', []))
        properties = schema.get('properties', {})
        return {key: canonical_arguments(item, properties.get(key, {}))
                for key, item in value.items() if key not in properties or item is not None or key in required}
    if isinstance(value, list) and 'items' in schema:
        return [canonical_arguments(item, schema['items']) for item in value]
    return value


def agent_tools(tools, connection=None):
    """Expose each route alternative as an object-shaped OpenAI function.

    Keep the canonical oneOf schema intact for local route validation. OpenAI
    rejects a union at the root of function parameters, including in non-strict
    Chat Completions requests.
    """
    result = []
    for tool in tools:
        function = tool['function']
        branches = function['parameters'].get('oneOf')
        if not branches:
            result.append(copy.deepcopy(tool))
            continue
        for index, branch in enumerate(branches):
            if branch.get('type') != 'object':
                raise ConnectionError('OpenAI function alternatives must be object schemas.')
            value = copy.deepcopy(tool)
            value['function']['name'] = function['name'] + '__branch_' + str(index)
            value['function']['parameters'] = copy.deepcopy(branch)
            # Function calling models consistently honor enum discriminators;
            # retain the equivalent const constraints in the canonical schema.
            for prop in value['function']['parameters'].get('properties', {}).values():
                if 'const' in prop:
                    prop['enum'] = [prop.pop('const')]
            if strict_routes(connection):
                f = value['function']
                f['parameters'] = strict_schema(branch)
                f['strict'] = True
                discriminators = {key: prop.get('enum', [prop.get('const')]) for key, prop in branch.get('properties', {}).items()
                                  if key in ('agent', 'query', 'source', 'operation') and ('enum' in prop or 'const' in prop)}
                f['description'] = f.get('description', '') + ' ' + branch.get('description', '') + ' Route alternative: ' + str(discriminators)
            result.append(value)
    names = [tool['function']['name'] for tool in result]
    if len(names) != len(set(names)):
        raise ConnectionError('OpenAI function names must be unique.')
    return result


def agent_calls(calls, tools, connection=None):
    """Restore canonical tool names only after validating the chosen branch."""
    declarations = {}
    for tool in tools:
        function = tool['function']
        schema = function['parameters']
        branches = schema.get('oneOf')
        if branches:
            for index, branch in enumerate(branches):
                declarations[function['name'] + '__branch_' + str(index)] = (function['name'], branch, schema)
        else:
            declarations[function['name']] = (function['name'], schema, schema)
    result = []
    for call in calls:
        if call['name'] not in declarations:
            raise ConnectionError('OpenAI returned an undeclared function.')
        name, branch, schema = declarations[call['name']]
        arguments = canonical_arguments(call['arguments'], branch) if schema.get('oneOf') and strict_routes(connection) else call['arguments']
        try:
            validate(arguments, branch)
            validate(arguments, schema)
        except ValidationError:
            raise ConnectionError('OpenAI returned invalid function arguments. Retry the request.') from None
        result.append(dict(call, name=name, arguments=arguments))
    return result
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
