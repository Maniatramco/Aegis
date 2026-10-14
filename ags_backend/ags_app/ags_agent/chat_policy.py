"""Small typed catalog shortcuts and evidence-only answer rendering."""
import json
import re


def prompt_route(text):
    value=text.strip()
    # This shortcut only resolves the named catalog domain. Processing and
    # compound content requests keep normal agent routing and confirmation.
    if not re.search(r'\b(prompts?|templates?)\b',value,re.I):return None
    if re.search(r'\b(extract|extraction|upload|onboard|create|save|change|update|delete|remove|run)\b',value,re.I):return None
    if re.search(r'\b(documents?|pdfs?|candidates?|skills|resumes?)\b',value,re.I):return None
    count=bool(re.search(r'\b(how many|count|number of)\b',value,re.I))
    listing=count or bool(re.search(r'\b(list|which|available|files|templates|prompts)\b',value,re.I))
    content=bool(re.search(r'\b(mentioned|inside|contents?|instructions?|schema|fields|says?|details)\b',value,re.I))
    if not (listing or content or re.search(r'\b(show|read|display|bring)\b',value,re.I)):return None
    source='metadata' if listing and not content else 'prompt'
    return {'intent':'answer','source':source,'operation':'none','fields':[], 'filters':[],
        'document_names':[],'answer_kind':'count' if count else 'list' if source=='metadata' else 'other',
        'result_scope':'selected_scope','scope_reference':'current_selection',
        'initial_reads':['list_prompts'] if source=='metadata' else [],'metadata_answer':'none',
        'supplementary_sources':[],'request_evidence':value[:500]}


def brief_summary(text):
    return bool(re.fullmatch(r'(?:can you\s+)?(?:please\s+|pls\s+)?(?:summari[sz]e|summary)(?:\s+(?:this|that|it|those results|the results))?[.!?]*',text.strip(),re.I))


def named_results(text,points):
    """Match explicit saved identities against authorized publication labels."""
    requested={m.casefold() for m in re.findall(r'\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b',text,re.I)}
    names=set()
    for p in points:
        root=p['entity_id'].split(':',1)[0]
        if root.casefold() in requested:names.add(root);continue
        title=p.get('title') or ''
        if title and re.search(r'(?<!\w)'+re.escape(title)+r'(?!\w)',text,re.I):names.add(title)
    return sorted(names)


def explicit_list_conditions(text,records,available):
    """Only the literal 'with A and B in their field' membership contract.

    A field must exist as a string array in published results. General semantic
    associations, expertise and arbitrary user text never become predicates.
    """
    for field in available:
        label=field.replace('_',' ')
        match=re.search(r'\bwith\s+(.+?)\s+in\s+(?:their\s+|the\s+|its\s+)?'+re.escape(label)+r'[.!?]*\s*$',text,re.I)
        if not match:continue
        values=[r.get('value',{}).get('fields',{}).get(field) for r in records if isinstance(r.get('value'),dict)]
        if not any(isinstance(v,list) and v and all(isinstance(item,str) for item in v) for v in values):continue
        terms=[x.strip(' \"\'') for x in re.split(r'\s+and\s+|,',match[1],flags=re.I)]
        if not 1<=len(terms)<=3 or any(not term or len(term)>100 for term in terms):continue
        return field,[{'field':field,'operator':'contains','value':term} for term in terms]
    return None,[]


def missing_paths(value,path=''):
    if value is None:return [path]
    if isinstance(value,dict):return [p for k,v in value.items() for p in missing_paths(v,(path+'.' if path else '')+k)]
    if isinstance(value,list):return [p for i,v in enumerate(value) for p in missing_paths(v,f'{path}[{i}]')]
    return []


def display(value):
    if value is None:return 'Not extracted'
    if isinstance(value,list) and not value:return 'None recorded'
    if isinstance(value,(dict,list)):return json.dumps(value,ensure_ascii=False,separators=(', ',': '))
    return str(value)


def result_answer(records):
    sections=[]
    for r in records:
        data=r.get('data',{});fields=data.get('fields') if isinstance(data,dict) else None
        if not isinstance(fields,dict):continue
        name=fields.get('full_name') or fields.get('name') or r.get('title','Saved result')
        heading=f'{name} — saved extraction, version {r.get("version",1)} [{r["citation_index"]}]'
        lines=[heading]+[f'- {k.replace("_"," ")}: {display(v)}' for k,v in fields.items()]
        missing=missing_paths(fields)
        if missing:lines.append('Missing values: '+', '.join(missing)+'.')
        lines.append('Review status: '+str(r.get('review_status') or 'unreviewed')+'.')
        sections.append('\n'.join(lines))
    return '\n\n'.join(sections)


def prompt_answer(records):
    if len(records)!=1:
        return 'Choose a prompt template or name one to see its instructions and schema.' if records else 'No prompt template is published in this dataset.'
    r=records[0];data=r['data'];schema=data.get('schema') or {}
    parts=[f'{data.get("filename") or r["title"]} — version {r["version"]} [{r["citation_index"]}]']
    instructions='\n'.join(dict.fromkeys(x for x in (data.get('instructions'),schema.get('description')) if x))
    parts.append('Instructions: '+(instructions or 'No instructions recorded.'))
    properties=schema.get('properties') or {}
    parts.append('Fields: '+', '.join(properties)+'.' if properties else 'No schema fields recorded.')
    for key,definition in properties.items():
        if isinstance(definition,dict) and definition.get('description'):parts.append(f'- {key}: {definition["description"]}')
    return '\n\n'.join(parts)


def normalize_citations(answer,records):
    """Normalize recognizable citation syntax; never invent source references."""
    answer=re.sub(r'\[citation_index\s*[:=]\s*(\d+)\]',
        lambda m:f'[{m[1]}]',answer or '',flags=re.I)
    return re.sub(r'\[(\d+(?:\s*,\s*\d+)+)\]',
        lambda m:' '.join(f'[{n.strip()}]' for n in m[1].split(',')),answer).strip()


def answer_problem(answer,records,expected_count=None):
    """Check provenance syntax and explicit contradictions, not full entailment."""
    valid={r['citation_index'] for r in records}
    cited={int(n) for n in re.findall(r'\[(\d+)\]',answer)}
    if not re.sub(r'\[\d+\]','',answer).strip():return 'empty_answer'
    if not cited:return 'missing_citations'
    if cited-valid:return 'unknown_citations'
    if expected_count is not None and str(expected_count) not in re.findall(r'\b\d+\b',re.sub(r'\[\d+\]','',answer)):
        return 'incorrect_exact_count'
    nulls=any(missing_paths(r.get('data',{}).get('fields',{})) for r in records if isinstance(r.get('data'),dict))
    if nulls and re.search(r'\b(no missing(?: values| fields)?|all fields (?:are )?(?:present|complete|populated)|complete contact information)\b',answer,re.I):
        return 'unsupported_completeness'
    return None


def checked_answer(answer,records):
    # Preserve the existing strict contract for callers outside Unified Chat.
    valid={r['citation_index'] for r in records}
    cited={int(n) for n in re.findall(r'\[(\d+)\]',answer)}
    if not answer.strip() or not cited or cited-valid:return False
    nulls=any(missing_paths(r.get('data',{}).get('fields',{})) for r in records if isinstance(r.get('data'),dict))
    if nulls and re.search(r'\b(no missing(?: values| fields)?|all fields (?:are )?(?:present|complete|populated)|complete contact information)\b',answer,re.I):return False
    return True


def validation_message(reason):
    descriptions={'empty_answer':'The model returned an empty answer.',
        'missing_citations':'The model did not attach source references to its answer.',
        'unknown_citations':'The model referenced sources outside the retrieved evidence.',
        'unsupported_completeness':'The model claimed completeness despite missing saved values.',
        'incorrect_exact_count':'The model did not preserve the verified catalog count.'}
    return descriptions.get(reason,'The answer could not be validated.')+' One repair attempt also failed. Retry the question; your data is unchanged.'
