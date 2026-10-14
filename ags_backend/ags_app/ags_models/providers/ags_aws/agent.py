"""Bedrock Converse tool calls; provider wire state stays in private checkpoints."""
import copy
from ...validation import ConnectionError


def payload(connection, messages, tools, budget, extra, required):
    system = []
    wire = []
    for message in messages:
        role = message['role']
        if role == 'system':
            system.append({'text': message['content']})
            continue
        state = message.get('_provider_state') or {}
        if role == 'assistant' and state.get('protocol') == 'bedrock':
            content = copy.deepcopy(state['content'])
        elif role == 'tool':
            role = 'user'
            content = [{'toolResult': {'toolUseId': message['tool_call_id'], 'content': [{'text': message['content']}]}}]
        else:
            content = [{'text': message['content']}] if message.get('content') else []
            for call in message.get('tool_calls') or []:
                content.append({'toolUse': {'toolUseId': call['id'], 'name': call['function']['name'], 'input': call['function']['arguments']}})
        if not content:
            raise ConnectionError('Agent conversation contains an empty message.')
        if wire and wire[-1]['role'] == role:
            wire[-1]['content'].extend(content)
        else:
            wire.append({'role': role, 'content': content})
    request = {'modelId': connection.model, 'system': system, 'messages': wire, 'inferenceConfig': {'maxTokens': budget, **extra}}
    if tools:
        request['toolConfig'] = {'tools': [{'toolSpec': {'name': t['function']['name'], 'description': t['function'].get('description', ''), 'inputSchema': {'json': t['function']['parameters']}}} for t in tools]}
        # All Converse tool models accept auto; forced "any" is model-specific.
        # The shared facade still requires and validates the requested tool call.
        request['toolConfig']['toolChoice'] = {'auto': {}}
    return request


def complete(connection, request):
    response = connection.bedrock().converse(**request)
    if response.get('stopReason') not in ('end_turn', 'tool_use'):
        raise ConnectionError('The Agent model returned an incomplete or refused response.')
    content = response['output']['message']['content']
    calls = [{'id': part['toolUse']['toolUseId'], 'name': part['toolUse']['name'], 'arguments': part['toolUse']['input']} for part in content if 'toolUse' in part]
    result = {'text': ''.join(part['text'] for part in content if 'text' in part), 'calls': calls,
              '_provider_state': {'protocol': 'bedrock', 'content': content}}
    return result, response
