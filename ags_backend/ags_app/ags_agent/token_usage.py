"""Provider-reported generation usage, isolated to one Agent answer turn."""
from contextlib import contextmanager
from contextvars import ContextVar

_calls = ContextVar('agent_token_usage', default=None)


@contextmanager
def collect():
    calls = []
    token = _calls.set(calls)
    try:
        yield calls
    finally:
        _calls.reset(token)


def count(value):
    return value if type(value) is int and value >= 0 else None


def attempt():
    calls = _calls.get()
    if calls is None:
        return None
    call = {'input_tokens': None, 'output_tokens': None}
    calls.append(call)
    return call


def record(response, protocol, call=None):
    calls = _calls.get()
    if calls is None:
        return
    data = response if isinstance(response, dict) else {}
    if protocol == 'ollama':
        input_tokens = count(data.get('prompt_eval_count'))
        output_tokens = count(data.get('eval_count'))
    elif protocol == 'bedrock':
        usage = data.get('usage') or {}
        usage = usage if isinstance(usage, dict) else {}
        input_tokens = count(usage.get('inputTokens'))
        output_tokens = count(usage.get('outputTokens'))
    elif protocol == 'vertex':
        usage = data.get('usageMetadata') or {}
        usage = usage if isinstance(usage, dict) else {}
        input_tokens = count(usage.get('promptTokenCount'))
        output_tokens = count(usage.get('candidatesTokenCount'))
        thoughts = count(usage.get('thoughtsTokenCount', 0))
        output_tokens = output_tokens + thoughts if output_tokens is not None and thoughts is not None else None
    else:
        usage = data.get('usage') or {}
        usage = usage if isinstance(usage, dict) else {}
        input_tokens = count(usage.get('prompt_tokens', usage.get('input_tokens')))
        output_tokens = count(usage.get('completion_tokens', usage.get('output_tokens')))
    if call is None:
        calls.append({'input_tokens': input_tokens, 'output_tokens': output_tokens})
    else:
        call.update(input_tokens=input_tokens, output_tokens=output_tokens)


def summary(calls):
    def total(key):
        values = [call[key] for call in calls if call[key] is not None]
        return sum(values) if values else (0 if not calls else None)
    reported = sum(call['input_tokens'] is not None and call['output_tokens'] is not None for call in calls)
    return {'scope': 'answer_turn', 'input_tokens': total('input_tokens'),
            'output_tokens': total('output_tokens'), 'model_calls': len(calls),
            'reported_calls': reported, 'complete': reported == len(calls),
            'source': 'provider' if calls else 'no_model_calls'}
