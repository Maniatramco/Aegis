"""Native Claude chat and tool calls using pinned registration credentials."""
import copy
from jsonschema import validate, ValidationError
from ...validation import ConnectionError


def agent_payload(connection, messages, tools, budget, extra, required):
    system, wire = [], []
    for message in messages:
        role = message['role']
        if role == 'system':
            if message.get('content'):
                system.append({'type': 'text', 'text': message['content']})
            continue
        state = message.get('_provider_state') or {}
        if role == 'assistant' and state.get('protocol') == 'anthropic':
            # Preserve opaque thinking signatures only in private checkpoints.
            content = copy.deepcopy(state['content'])
        elif role == 'tool':
            role = 'user'
            content = [{'type': 'tool_result', 'tool_use_id': message['tool_call_id'], 'content': message['content']}]
        elif role in ('assistant', 'user'):
            content = [{'type': 'text', 'text': message['content']}] if message.get('content') else []
            for call in message.get('tool_calls') or []:
                content.append({'type': 'tool_use', 'id': call['id'], 'name': call['function']['name'], 'input': call['function']['arguments']})
        else:
            raise ConnectionError('Claude conversation contains an unsupported message role.')
        if not content:
            raise ConnectionError('Claude conversation contains an empty message.')
        if wire and wire[-1]['role'] == role:
            wire[-1]['content'].extend(content)
        else:
            wire.append({'role': role, 'content': content})
    if required:
        if not tools:
            raise ConnectionError('This Agent stage requires an available tool.')
        system.append({'type': 'text', 'text': 'For this step, call an available tool using its input schema. Do not substitute a text answer for the required tool call.'})
    request = {'model': connection.model, 'max_tokens': budget, 'system': system, 'messages': wire, **extra}
    if tools:
        request['tools'] = [{'name': t['function']['name'], 'description': t['function'].get('description', ''), 'input_schema': t['function']['parameters']} for t in tools]
        # Forced tool choice is unavailable on some Claude models. The shared
        # Agent facade still enforces required calls and the probe checks them.
        request['tool_choice'] = {'type': 'auto'}
    return request


def agent_complete(connection, request):
    data = connection.post('/messages', request)
    if not isinstance(data, dict) or data.get('stop_reason') not in ('end_turn', 'tool_use') or (data.get('stop_details') or {}).get('type') == 'refusal':
        raise ConnectionError('Claude returned an incomplete or refused response.')
    content = data.get('content')
    if data.get('role') != 'assistant' or not isinstance(content, list) or not content:
        raise ConnectionError('Claude returned an invalid response.')
    schemas = {tool['name']: tool['input_schema'] for tool in request.get('tools', [])}
    text, calls, ids = [], [], set()
    for part in content:
        kind = part.get('type') if isinstance(part, dict) else None
        if kind == 'text' and isinstance(part.get('text'), str):
            text.append(part['text'])
        elif kind == 'tool_use':
            id, name, arguments = part.get('id'), part.get('name'), part.get('input')
            if not isinstance(id, str) or not id or id in ids or not isinstance(name, str) or name not in schemas or not isinstance(arguments, dict):
                raise ConnectionError('Claude returned invalid tool arguments.')
            try:
                validate(arguments, schemas[name])
            except ValidationError as exc:
                raise ConnectionError('Claude tool arguments did not match the requested schema.') from exc
            calls.append({'id': id, 'name': name, 'arguments': arguments})
            ids.add(id)
        elif kind not in ('thinking', 'redacted_thinking'):
            raise ConnectionError('Claude returned an unsupported response block.')
    if bool(calls) != (data['stop_reason'] == 'tool_use') or (not calls and not ''.join(text).strip()):
        raise ConnectionError('Claude returned an empty or inconsistent response.')
    return {'text': ''.join(text), 'calls': calls, '_provider_state': {'protocol': 'anthropic', 'content': copy.deepcopy(content)}}, data


def generate(connection, instruction, text, schema, output_tokens, extra):
    if schema:
        raise ConnectionError('Direct Claude supports Chat only; use the configured Extraction model for structured extraction.')
    request = agent_payload(connection, [{'role': 'system', 'content': instruction}, {'role': 'user', 'content': text}], [], output_tokens, extra, False)
    result, _ = agent_complete(connection, request)
    return result['text']


def embed(connection, texts, query, dim, extra):
    raise ConnectionError('Direct Claude does not provide embeddings. Use the configured Embedding model.')
