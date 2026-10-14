"""OCI Generic and Cohere native function calling, using the saved model profile."""
import json
from .... import core
from ...validation import ConnectionError


def payload(connection, messages, tools, budget, extra, required):
    if connection.c.get('chat_format') == 'cohere':
        return cohere_payload(messages, tools, budget, extra, required)
    wire = []
    for message in messages:
        item = {'role': message['role'].upper(), 'content': [{'type': 'TEXT', 'text': message['content']}] if message.get('content') else []}
        if message['role'] == 'tool':
            item['tool_call_id'] = message['tool_call_id']
        if message.get('tool_calls'):
            item['tool_calls'] = [{'id': c['id'], 'name': c['function']['name'], 'arguments': json.dumps(c['function']['arguments'])} for c in message['tool_calls']]
        wire.append(item)
    return {'format': 'generic', 'messages': wire, 'tools': [t['function'] for t in tools], 'required': required, 'max_tokens': budget, **extra}


def cohere_payload(messages, tools, budget, extra, required):
    systems = [m['content'] for m in messages if m['role'] == 'system']
    current = max((i for i, m in enumerate(messages) if m['role'] == 'user'), default=-1)
    if current < 0:
        raise ConnectionError('Agent conversation has no current user request.')
    history = []
    calls = {}
    results = []
    has_results = any(m['role'] == 'tool' for m in messages[current + 1:])
    for i, message in enumerate(messages):
        if message['role'] == 'system' or i == current and not has_results:
            continue
        if message['role'] == 'tool':
            if i > current:
                call = calls.get(message['tool_call_id'])
                if not call:
                    raise ConnectionError('Agent tool result has no matching function call.')
                results.append({'call': call, 'outputs': [{'result': message['content']}]})
            else:
                history.append({'role': 'USER', 'message': 'Tool observation: ' + message['content']})
            continue
        item = {'role': 'CHATBOT' if message['role'] == 'assistant' else 'USER', 'message': message.get('content') or ' '}
        if message.get('tool_calls'):
            item['tool_calls'] = []
            for call in message['tool_calls']:
                value = {'name': call['function']['name'], 'parameters': call['function']['arguments']}
                calls[call['id']] = value
                item['tool_calls'].append(value)
        history.append(item)
    return {'format': 'cohere', 'message': '' if has_results else messages[current]['content'], 'preamble_override': '\n'.join(systems),
            'chat_history': history, 'tools': [t['function'] for t in tools], 'tool_results': results,
            'required': required, 'max_tokens': budget, **extra}


def complete(connection, wire):
    import oci
    from oci.generative_ai_inference import models
    request = dict(wire)
    fmt = request.pop('format')
    required = request.pop('required')
    contracts = request.pop('tools')
    if fmt == 'cohere':
        tools = []
        for tool in contracts:
            schema = tool['parameters']
            parameters = {name: models.CohereParameterDefinition(type=value.get('type', 'string'),
                description=value.get('description', '') + '\nJSON Schema: ' + json.dumps(value),
                is_required=name in schema.get('required', [])) for name, value in schema.get('properties', {}).items()}
            tools.append(models.CohereTool(name=tool['name'], description=tool.get('description', ''), parameter_definitions=parameters))
        history = []
        for item in request.pop('chat_history'):
            values = dict(item)
            values.pop('role')
            if item['role'] == 'CHATBOT':
                values['tool_calls'] = [models.CohereToolCall(**c) for c in values.get('tool_calls', [])]
                history.append(models.CohereChatBotMessage(**values))
            else:
                history.append(models.CohereUserMessage(**values))
        results = [models.CohereToolResult(call=models.CohereToolCall(**r['call']), outputs=r['outputs']) for r in request.pop('tool_results')]
        chat = models.CohereChatRequest(**request, chat_history=history, tools=tools or None, tool_results=results or None, is_stream=False)
    else:
        messages = []
        classes = {'SYSTEM': models.SystemMessage, 'USER': models.UserMessage, 'ASSISTANT': models.AssistantMessage, 'TOOL': models.ToolMessage}
        for item in request.pop('messages'):
            values = {k: v for k, v in item.items() if k != 'role'}
            values['content'] = [models.TextContent(text=p['text']) for p in item['content']] or None
            if 'tool_calls' in values:
                values['tool_calls'] = [models.FunctionCall(**c) for c in values['tool_calls']]
            messages.append(classes[item['role']](**values))
        definitions = [models.FunctionDefinition(name=t['name'], description=t.get('description', ''), parameters=t['parameters']) for t in contracts]
        chat = models.GenericChatRequest(**request, messages=messages, tools=definitions or None, is_stream=False,
            tool_choice=(models.ToolChoiceRequired() if required else models.ToolChoiceAuto()) if contracts else None)
    response = connection.oci_client().chat(models.ChatDetails(compartment_id=connection.c['compartment_id'],
        serving_mode=connection.oci_serving_mode(models), chat_request=chat)).data.chat_response
    usage = {'usage': oci.util.to_dict(response.usage) if getattr(response, 'usage', None) else {}}
    if fmt == 'cohere':
        if response.finish_reason not in ('COMPLETE', 'STOP', 'TOOL_CALL'):
            raise ConnectionError('The Agent model returned an incomplete or refused response.')
        calls = [{'id': 'call_' + core.uid(), 'name': c.name, 'arguments': c.parameters} for c in response.tool_calls or []]
        return {'text': response.text or '', 'calls': calls}, usage
    choice = response.choices[0]
    if choice.finish_reason not in ('stop', 'STOP', 'tool_calls', 'TOOL_CALLS'):
        raise ConnectionError('The Agent model returned an incomplete or refused response.')
    message = choice.message
    calls = [{'id': c.id, 'name': c.name, 'arguments': json.loads(c.arguments)} for c in message.tool_calls or []]
    return {'text': ''.join(p.text for p in message.content or [] if getattr(p, 'text', None)), 'calls': calls}, usage
