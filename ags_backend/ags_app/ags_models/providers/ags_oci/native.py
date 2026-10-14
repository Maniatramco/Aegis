from ...validation import ConnectionError
from .agent import payload as agent_payload, complete as agent_complete
def client(connection):
    try:
        import oci
    except ImportError:
        raise ConnectionError('Install ags_backend/requirements-models.txt for native cloud protocols.')
    mode = connection.c['auth_mode']
    cfg = {'region': connection.c['region']}
    kwargs = {}
    if mode == 'oci_credentials':
        cfg.update({k: connection.secret[k] for k in ('tenancy', 'user', 'fingerprint', 'key_content')})
        if connection.secret.get('pass_phrase'):
            cfg['pass_phrase'] = connection.secret['pass_phrase']
    elif mode == 'config_profile':
        cfg = oci.config.from_file(profile_name=connection.c.get('profile', 'DEFAULT')) | cfg
    else:
        kwargs['signer'] = oci.auth.signers.get_resource_principals_signer()
    client = oci.generative_ai_inference.GenerativeAiInferenceClient(cfg, service_endpoint=connection.c['endpoint'],
        timeout=(min(10, connection.timeout), connection.timeout), retry_strategy=oci.retry.NoneRetryStrategy(), **kwargs)
    client.base_client.session.trust_env = False
    client.base_client.session.max_redirects = 0
    return client


def serving_mode(connection, models):
    return models.DedicatedServingMode(endpoint_id=connection.model) if connection.model.startswith('ocid1.generativeaiendpoint.') else models.OnDemandServingMode(model_id=connection.model)


def generate(connection, instruction, text, schema, output_tokens, extra):
    from oci.generative_ai_inference import models
    if connection.c.get('chat_format') == 'cohere':
        request = models.CohereChatRequest(preamble_override=instruction, message=text, max_tokens=output_tokens, is_stream=False, **extra)
    else:
        request = models.GenericChatRequest(messages=[models.SystemMessage(content=[models.TextContent(text=instruction)]), models.UserMessage(content=[models.TextContent(text=text)])], max_tokens=output_tokens, is_stream=False, **extra)
    data = connection.oci_client().chat(models.ChatDetails(compartment_id=connection.c['compartment_id'], serving_mode=connection.oci_serving_mode(models), chat_request=request)).data.chat_response
    if connection.c.get('chat_format') == 'cohere':
        if getattr(data, 'finish_reason', None) not in ('COMPLETE', 'STOP'):
            raise ConnectionError('Model returned an incomplete or refused response.')
        result = data.text
    else:
        choice = data.choices[0]
        if getattr(choice, 'finish_reason', None) not in ('stop', 'STOP'):
            raise ConnectionError('Model returned an incomplete or refused response.')
        result = '\n'.join(x.text for x in choice.message.content if getattr(x, 'text', None))
    return result


def embed(connection, texts, query, dim, extra):
    from oci.generative_ai_inference import models
    request = models.EmbedTextDetails(compartment_id=connection.c['compartment_id'], serving_mode=connection.oci_serving_mode(models), inputs=texts, input_type='SEARCH_QUERY' if query else 'SEARCH_DOCUMENT', truncate='NONE', **({'output_dimensions': dim} if dim else {}))
    vectors = connection.oci_client().embed_text(request).data.embeddings
    return vectors
