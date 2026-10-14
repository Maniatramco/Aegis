"""Vertex Gemini function calling with lossless signed assistant parts."""
import copy
import json
from .... import core
from ...validation import ConnectionError


def payload(connection, messages, tools, budget, extra, required):
    systems = []
    contents = []
    names = {}
    for message in messages:
        role = message['role']
        if role == 'system':
            systems.append({'text': message['content']})
            continue
        state = message.get('_provider_state') or {}
        if role == 'assistant' and state.get('protocol') == 'vertex':
            parts = copy.deepcopy(state['parts'])
            for call, part in zip(message.get('tool_calls') or [], [p for p in parts if 'functionCall' in p]):
                names[call['id']] = part['functionCall']['name']
        elif role == 'tool':
            name = names.get(message['tool_call_id']) or message.get('tool_name')
            if not name:
                raise ConnectionError('Agent tool result has no matching function call.')
            parts = [{'functionResponse': {'name': name, 'response': {'result': message['content']}}}]
        else:
            parts = [{'text': message['content']}] if message.get('content') else []
            for call in message.get('tool_calls') or []:
                names[call['id']] = call['function']['name']
                parts.append({'functionCall': {'name': call['function']['name'], 'args': call['function']['arguments']}})
        if not parts:
            raise ConnectionError('Agent conversation contains an empty message.')
        native_role = 'model' if role == 'assistant' else 'user'
        if contents and contents[-1]['role'] == native_role:
            contents[-1]['parts'].extend(parts)
        else:
            contents.append({'role': native_role, 'parts': parts})
    request = {'systemInstruction': {'parts': systems}, 'contents': contents, 'generationConfig': {'maxOutputTokens': budget, **extra}}
    if tools:
        request['tools'] = [{'functionDeclarations': [{'name': t['function']['name'], 'description': t['function'].get('description', ''), 'parametersJsonSchema': t['function']['parameters']} for t in tools]}]
        request['toolConfig'] = {'functionCallingConfig': {'mode': 'ANY' if required else 'AUTO'}}
    return request


def complete(connection, request):
    response = connection.post(connection.vertex_path('generateContent'), request, connection.vertex_headers())
    candidate = response['candidates'][0]
    if candidate.get('finishReason') != 'STOP':
        raise ConnectionError('The Agent model returned an incomplete or refused response.')
    parts = candidate['content']['parts']
    calls = [{'id': 'call_' + core.uid(), 'name': part['functionCall']['name'], 'arguments': part['functionCall'].get('args', {})} for part in parts if 'functionCall' in part]
    result = {'text': ''.join(part['text'] for part in parts if 'text' in part and not part.get('thought')), 'calls': calls,
              '_provider_state': {'protocol': 'vertex', 'parts': parts}}
    return result, response
