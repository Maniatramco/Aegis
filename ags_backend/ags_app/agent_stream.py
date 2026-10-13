"""Incremental model text; never expose JSON/tool arguments as answer tokens."""
import json
import httpx
from . import core, providers, ollama_provider


def answer_prefix(raw):
    """Read root JSON fields only, including a safely decoded partial answer."""
    decoder=json.JSONDecoder();position=0;calls=None;answer=''
    raw=raw.lstrip()
    if not raw.startswith('{'):return ''
    position=1
    while position<len(raw):
        while position<len(raw) and raw[position] in ' \r\n\t,':position+=1
        try:
            key,end=decoder.raw_decode(raw,position)
            position=end
            while position<len(raw) and raw[position].isspace():position+=1
            if position>=len(raw) or raw[position]!=':':break
            position+=1
            while position<len(raw) and raw[position].isspace():position+=1
            start=position
            try:value,position=decoder.raw_decode(raw,start)
            except ValueError:
                if key!='answer' or start>=len(raw) or raw[start]!='"':break
                end=start+1
                while end<len(raw):
                    char=raw[end]
                    if char=='"':break
                    if char=='\\':
                        if end+1>=len(raw):break
                        count=6 if raw[end+1]=='u' else 2
                        if end+count>len(raw):break
                        end+=count
                    else:end+=1
                try:answer=json.loads(raw[start:end]+'"')
                except ValueError:break
                if answer and 0xD800<=ord(answer[-1])<=0xDBFF:answer=answer[:-1]
                break
            if key=='tool_calls':calls=value
            elif key=='answer' and isinstance(value,str):answer=value
        except ValueError:break
    return answer if calls==[] else ''


def qwen_request(payload,timeout,on_token):
    # HTTP engine failures happen before tokens. Never replay a partial stream.
    try:return ollama_provider.retry_runner(lambda remaining:_qwen_request(payload,remaining,on_token),timeout)
    except ollama_provider.OllamaError as exc:raise providers.ProviderError(str(exc)) from exc


def _qwen_request(payload,timeout,on_token):
    on_token('')  # A cancelled request must not start a recovery inference.
    raw='';published='';terminal=None
    try:
        with httpx.Client(timeout=timeout,trust_env=False,follow_redirects=False) as client:
            with client.stream('POST',ollama_provider.base_url()+'/api/chat',json=dict(payload,stream=True)) as response:
                if response.status_code>=300:
                    response.read()
                    ollama_provider.response_error(response)
                for line in response.iter_lines():
                    on_token('')  # Cancellation check, including tool/control tokens.
                    if not line:continue
                    event=json.loads(line)
                    if not isinstance(event,dict) or event.get('error'):raise providers.ProviderError('Local model returned invalid streaming data.')
                    piece=event.get('message',{}).get('content','')
                    if not isinstance(piece,str):raise providers.ProviderError('Local model returned invalid streaming text.')
                    raw+=piece;prefix=answer_prefix(raw)
                    if prefix.startswith(published) and len(prefix)>len(published):
                        on_token(prefix[len(published):]);published=prefix
                    if event.get('done'):terminal=event;break
        if not terminal or terminal.get('done_reason')=='length':raise providers.ProviderError('The agent answer was incomplete. Retry or increase the model output budget.')
        return dict(terminal,message={'content':raw})
    except (httpx.HTTPError,ValueError) as exc:raise providers.ProviderError('The model stream disconnected, timed out, or returned invalid data.') from exc


def visible_content(raw):
    # Some local models put private reasoning in content instead of `thinking`.
    text=raw.lstrip()
    if '<think>'.startswith(text):return ''
    if text.startswith('<think>'):
        if '</think>' not in text:return ''
        text=text.split('</think>',1)[1].lstrip()
    return text


def native_request(protocol,payload,cfg,on_token):
    headers={};raw='';published='';calls={};terminal=None
    if protocol=='ollama':endpoint=ollama_provider.base_url()+'/api/chat'
    elif cfg['model_provider']=='registered':
        from .model_connections import ModelConnection,ConnectionError
        try:connection=ModelConnection(cfg)
        except ConnectionError as exc:raise providers.ProviderError(str(exc)) from exc
        endpoint=connection.c['endpoint']+'/chat/completions'
        if connection.c['auth_mode'] in ('api_key','bearer_token'):
            headers['Authorization']='Bearer '+connection.secret['api_key' if connection.c['auth_mode']=='api_key' else 'token']
    else:
        key=core.api_key()
        if not key:raise providers.ProviderError('Configure an OpenAI API key before using this provider.')
        endpoint='https://api.openai.com/v1/chat/completions';headers['Authorization']='Bearer '+key
    try:
        with httpx.Client(timeout=cfg['timeout'],trust_env=False,follow_redirects=False) as client:
            with client.stream('POST',endpoint,json=dict(payload,stream=True),headers=headers) as response:
                if response.status_code>=300:raise providers.ProviderError('Model streaming request failed (HTTP '+str(response.status_code)+'). Check model access and configuration.')
                for line in response.iter_lines():
                    on_token('')  # Cancellation check, including tool/control tokens.
                    if not line:continue
                    if protocol!='ollama':
                        if not line.startswith('data:'):continue
                        line=line[5:].strip()
                        if line=='[DONE]':break
                    event=json.loads(line)
                    if not isinstance(event,dict) or event.get('error'):raise providers.ProviderError('The provider returned invalid streaming data.')
                    if protocol=='ollama':
                        delta=event.get('message') or {}
                        for call in delta.get('tool_calls') or []:calls[len(calls)]=call
                        if event.get('done'):terminal=event
                    else:
                        choices=event.get('choices') or []
                        if not choices:continue
                        choice=choices[0];delta=choice.get('delta') or {}
                        if choice.get('finish_reason'):terminal=choice
                        for part in delta.get('tool_calls') or []:
                            call=calls.setdefault(part['index'],{'id':'','type':'function','function':{'name':'','arguments':''}})
                            if part.get('id'):call['id']=part['id']
                            function=part.get('function') or {}
                            call['function']['name']+=function.get('name') or ''
                            call['function']['arguments']+=function.get('arguments') or ''
                    piece=delta.get('content') or ''
                    if not isinstance(piece,str):raise providers.ProviderError('The provider returned invalid streaming text.')
                    raw+=piece;prefix=visible_content(raw)
                    if prefix.startswith(published) and len(prefix)>len(published):
                        on_token(prefix[len(published):]);published=prefix
                    if protocol=='ollama' and terminal:break
        if not terminal:raise providers.ProviderError('The model stream ended before the answer completed. Retry the question.')
        message={'content':raw,'tool_calls':list(calls.values())}
        if protocol=='ollama':return dict(terminal,message=message)
        return {'choices':[dict(terminal,message=message)]}
    except (httpx.HTTPError,ValueError,KeyError,TypeError) as exc:raise providers.ProviderError('The model stream disconnected, timed out, or returned invalid data.') from exc
