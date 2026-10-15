"""Per-call context packing. Full conversation and tool traces remain in storage.

Never truncate the current request or silently discard required evidence. The
budget uses the same conservative byte estimate as the provider preflight,
against the final provider wire representation, including tool contracts.
"""
import copy
import json
from contextlib import contextmanager
from contextvars import ContextVar
from .. import providers
from .. import runtime_config

_observer=ContextVar('agent_context_observer',default=None)
READS={'list_documents','list_datasets','list_prompts','get_dataset_status',
    'get_dataset_onboarding_status','get_model_configuration','get_application_info',
    'get_workflow_status','read_prompt','find_extractions','read_extraction_results','search_documents','search_knowledge'}


@contextmanager
def observe(callback):
    token=_observer.set(callback)
    try:yield
    finally:_observer.reset(token)


def clean(message):
    return {k:copy.deepcopy(v) for k,v in message.items() if not k.startswith('_context')}


def _deduplicate(messages):
    """Replace exact repeated successful read pairs with their latest result.

    Different pages/projections are distinct reads. Mutations, errors and
    multi-call groups are never deduplicated. Canonical trace is untouched.
    """
    seen={};remove=set();count=0
    for i in range(len(messages)-1,-1,-1):
        message=messages[i];calls=message.get('tool_calls') or []
        if message['role']!='assistant' or len(calls)!=1 or i+1>=len(messages):continue
        call=calls[0];function=call['function'];result=messages[i+1]
        if function['name'] not in READS or result['role']!='tool' or result.get('tool_call_id')!=call['id']:continue
        try:value=json.loads(result['content'])
        except (TypeError,ValueError):continue
        if not isinstance(value,dict) or value.get('error'):continue
        key=(function['name'],json.dumps(function['arguments'],sort_keys=True,separators=(',',':')))
        if key in seen:remove.update((i,i+1));count+=1
        else:seen[key]=i
    return [m for i,m in enumerate(messages) if i not in remove],count


def fit(messages,cfg,output_tokens,serialize,stage):
    """Exclude chat history, then remove optional examples until the wire fits.

    `_context` tags are assigned only by server code. A user cannot authorize
    removing evidence or make text into a system message by supplying tags.
    """
    limit=cfg.get('context_limit') or runtime_config.get('AEGIS_DEFAULT_MODEL_CONTEXT_TOKENS')
    headroom=runtime_config.get('AEGIS_CONTEXT_HEADROOM_TOKENS')
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=2097152:
        raise providers.ProviderError('Invalid model context limit. Check Model Registration.')
    if isinstance(output_tokens,bool) or not isinstance(output_tokens,int) or output_tokens<1:
        raise providers.ProviderError('Invalid model answer budget. Check Model Registration.')
    # User preference: chat text is never a knowledge source. Remove server-
    # marked past turns even when there is plenty of remaining context space.
    history_units={m.get('_context',{}).get('unit') for m in messages if m.get('_context',{}).get('kind')=='history'}
    current=[m for m in messages if m.get('_context',{}).get('kind')!='history']
    packed,duplicates=_deduplicate(copy.deepcopy(current))
    groups=[]
    for kind in ('history','example'):
        for m in packed:
            marker=m.get('_context',{})
            key=(kind,marker.get('unit'))
            if marker.get('kind')==kind and key not in groups:groups.append(key)
    removed={'history':len(history_units),'example':0}
    def measure():
        wire=serialize([clean(m) for m in packed])
        wire_bytes=len(json.dumps(wire,ensure_ascii=False).encode('utf-8'))
        return wire,wire_bytes,(wire_bytes+1)//2+output_tokens+headroom
    wire,wire_bytes,total=measure()
    for kind,unit in groups:
        if total<=limit:break
        packed=[m for m in packed if m.get('_context',{}).get('kind')!=kind or m.get('_context',{}).get('unit')!=unit]
        removed[kind]+=1
        wire,wire_bytes,total=measure()
    audit={'stage':stage,'context_limit':limit,'estimated_input_tokens':(wire_bytes+1)//2,
        'reserved_output_tokens':output_tokens,'safety_tokens':headroom,'estimated_total_tokens':total,
        'history_turns_dropped':removed['history'],'example_pairs_dropped':removed['example'],
        'duplicate_reads_removed':duplicates,'dispatch_allowed':total<=limit}
    callback=_observer.get()
    if callback:callback(audit)
    if total>limit:
        raise providers.ProviderError('The required question or evidence exceeds this model’s context budget. '
            'Choose a smaller document scope or ask for specific fields. Your saved chat, files and results are preserved.')
    return wire
