"""Validated per-model inference settings; transport and prompt fields stay owned by Aegis."""
import copy
import json
import math


class ParameterError(ValueError):
    pass


def supported_parameters(protocol, category, connection=None):
    if category == 'embedding':
        if protocol == 'ollama': return ('keep_alive',)
        if protocol in ('openai-compatible', 'azure-openai'): return ('encoding_format',)
        if protocol == 'bedrock' and (connection or {}).get('embedding_format', 'titan') == 'titan': return ('normalize',)
        return ()
    return {
        'ollama': ('temperature', 'top_p', 'top_k', 'min_p', 'repeat_penalty', 'repeat_last_n', 'seed', 'stop', 'keep_alive'),
        'openai-compatible': ('temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'seed', 'stop', 'reasoning_effort'),
        'azure-openai': ('temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'seed', 'stop', 'reasoning_effort'),
        'bedrock': ('temperature', 'topP', 'stopSequences'),
        'vertex': ('temperature', 'topP', 'topK', 'stopSequences', 'seed', 'presencePenalty', 'frequencyPenalty'),
        'oci': ('temperature', 'top_p', 'top_k', 'frequency_penalty', 'presence_penalty', 'seed', 'stop') if (connection or {}).get('chat_format') != 'cohere' else ('temperature', 'top_p', 'top_k', 'frequency_penalty', 'presence_penalty', 'seed', 'stop_sequences'),
    }.get(protocol, ())


def validate_parameters(parameters, protocol, category, connection=None):
    if not isinstance(parameters, dict) or len(parameters) > 20:
        raise ParameterError('Extra parameters must be a JSON object with at most 20 entries.')
    allowed = supported_parameters(protocol, category, connection)
    # Do not interpolate submitted names or values into errors (could contain credentials).
    if any(key not in allowed for key in parameters):
        raise ParameterError('Unsupported extra parameter for this model. Supported keys: ' + (', '.join(allowed) or 'none; use the token and dimensions fields') + '.')
    for key, value in parameters.items():
        if key in ('stop', 'stop_sequences', 'stopSequences'):
            valid = isinstance(value, list) and len(value) <= 16 and all(isinstance(v, str) and 0 < len(v) <= 256 for v in value)
        elif key == 'keep_alive':
            import re
            valid = isinstance(value, str) and bool(re.fullmatch(r'(?:0|[0-9]{1,3}(?:ms|s|m|h))', value))
        elif key == 'normalize': valid = isinstance(value, bool)
        elif key == 'encoding_format': valid = value == 'float'
        elif key == 'reasoning_effort': valid = value in ('minimal', 'low', 'medium', 'high', 'none')
        else:
            valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            if key in ('seed', 'top_k', 'topK', 'repeat_last_n'): valid = valid and isinstance(value, int)
            if key == 'seed': valid = valid and 0 <= value <= 2147483647
            elif key in ('top_k', 'topK', 'repeat_last_n'): valid = valid and 0 <= value <= 4096
            elif key in ('top_p', 'topP', 'min_p'): valid = valid and 0 <= value <= 1
            elif key == 'repeat_penalty': valid = valid and 0 <= value <= 2
            elif key == 'temperature': valid = valid and 0 <= value <= (1 if protocol == 'bedrock' else 2)
            else: valid = valid and -2 <= value <= 2
        if not valid:
            raise ParameterError('Invalid value for extra parameter ' + key + '. Check its type and supported range.')
    return copy.deepcopy(parameters)


def check_budget(cfg, contents, embedding=False, output_tokens=None):
    limit = cfg.get('embedding_context_limit' if embedding else 'context_limit')
    if limit is None: return
    reserved = 0 if embedding else (output_tokens if output_tokens is not None else cfg.get('max_output_tokens', 4096)) + 512
    # Conservative UTF-8 estimate, not a provider-specific tokenizer. Never truncate input.
    needed = (len(json.dumps(contents, ensure_ascii=False).encode('utf-8')) + 1) // 2 + reserved
    if needed > limit:
        label = 'embedding input' if embedding else 'context'
        raise ParameterError(f'Selected content exceeds this model\'s {label} budget ({limit:,} tokens). Estimated requirement: {needed:,} tokens. Choose a smaller scope or change the token limit in Model Registration.')
