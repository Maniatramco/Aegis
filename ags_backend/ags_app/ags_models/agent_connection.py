"""Native Agent dispatch with bounded transport and validated tool responses."""
from .connection import ModelConnection
from .validation import ConnectionError
from .parameters import validate_parameters
from .provider_registry import provider
from ..ags_agent import agent_context, token_usage


def complete(cfg, messages, tools, on_token=None):
    connection = ModelConnection(cfg)
    adapter = provider(connection.c)
    budget = cfg.get('max_output_tokens') or 768
    extra = validate_parameters(cfg.get('extra_parameters', {}), connection.c['protocol'], 'chat', connection.c)
    wire = agent_context.fit(messages, cfg, budget,
        lambda inputs: adapter.agent_payload(connection, inputs, tools, budget, extra, bool(cfg.get('_agent_require_tool'))),
        'tool_selection' if cfg.get('_agent_require_tool') else 'answer')
    usage_call = token_usage.attempt()
    try:
        result, usage = adapter.agent_complete(connection, wire)
        token_usage.record(usage, connection.c['protocol'], usage_call)
        text, calls = result.get('text'), result.get('calls')
        if not isinstance(text, str) or not isinstance(calls, list) or len(calls) > 128:
            raise ConnectionError('The Agent provider returned an invalid response.')
        ids = set()
        for call in calls:
            if not isinstance(call, dict) or not isinstance(call.get('id'), str) or not call['id'] or call['id'] in ids or not isinstance(call.get('name'), str) or not call['name'] or not isinstance(call.get('arguments'), dict):
                raise ConnectionError('The Agent provider returned invalid tool arguments.')
            ids.add(call['id'])
        if cfg.get('_agent_require_tool') and not calls:
            raise ConnectionError('This Chat model did not return the required tool call. Choose a model with function calling support.')
        # Native adapters return complete validated responses. Publish once;
        # keep the existing SSE event contract without inventing token streaming.
        if on_token and text and not calls:
            on_token(text)
        return result
    except ConnectionError:
        raise
    except ImportError as exc:
        raise ConnectionError('Install ags_backend/requirements-models.txt for native cloud protocols.') from exc
    except Exception as exc:
        raise ConnectionError('Agent request failed. Check model tool-calling support, credentials, permissions, and quota.') from exc
