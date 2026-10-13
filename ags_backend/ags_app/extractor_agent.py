"""Durable LangGraph extractor: knowledge -> retrieve -> generate -> validate -> Parquet."""
import hashlib
import json
import time
from typing import TypedDict
from jsonschema import validate
from langgraph.graph import StateGraph, START, END
from langsmith import tracing_context
from . import core, providers, workflow, extraction_retrieval, parquet_results
from .agent_checkpoints import ExternalCheckpointSaver


class State(TypedDict):
    selected: list[dict]
    diagnostics: dict
    records: dict
    result: dict
    evidence: list[dict]
    output: dict


def run(jid, record, data, snapshot, documents, sources, check):
    indexes = {d.id: core.store.json('documents/' + d.id + '/index.json') for d in documents}
    data['index_versions'] = {key: {k: value.get(k) for k in
        ('index_generation', 'fingerprint', 'embedding_digest', 'indexed_at', 'dimensions')} for key, value in indexes.items()}
    signature = hashlib.sha256(json.dumps({'schema': data['schema'], 'prompt_version': data['template_version'],
        'indexes': data['index_versions'], 'execution': snapshot, 'pipeline': 1}, sort_keys=True).encode()).hexdigest()
    signature_ref = 'jobs/' + jid + '/extractor-signature.json'
    saver = ExternalCheckpointSaver(jid)
    try:
        if core.store.json(signature_ref)['signature'] != signature:
            saver.delete_thread(jid)
    except FileNotFoundError: pass
    core.store.put_json(signature_ref, {'signature': signature})

    def stage(name, status='running'):
        check(); workflow.transition(jid, name, status)

    def retrieve(state):
        stage('retrieving')
        groups = (data.get('merge') or {}).get('sources', []) if data.get('merge_records') else []
        selected = []; diagnostics = {}
        if groups:
            for source in groups:
                scoped = [c for c in sources if c.get('source_key') == source['key']] if data['merge'].get('document_id') else [c for c in sources if c['document_id'] == source['document_id']]
                chunks, detail = extraction_retrieval.retrieve(data['record_schema'], documents, snapshot, scoped, progress=lambda name: stage(name))
                selected.extend(dict(c, record_key=source['key']) for c in chunks); diagnostics[source['key']] = detail
        else:
            selected, diagnostics = extraction_retrieval.retrieve(data['schema'], documents, snapshot, sources, progress=lambda name: stage(name))
        stage('retrieving', 'completed'); stage('reranking', 'completed')
        return {'selected': selected, 'diagnostics': diagnostics}

    def generate(state):
        stage('generate'); records = dict(state.get('records', {})); evidence = []
        def context(items):
            return '\n\n'.join(f'Document: {c.get("source_filename", c["document_name"])}; chunk {c["id"]}; page {c["page"]}\n{c["text"]}' for c in items)
        if data.get('merge_records') and data.get('merge'):
            manifest = data['merge']['sources']
            # Persist individual completed records outside the graph node too:
            # process death inside a multi-document node never loses prior work.
            checkpoint_ref = 'jobs/' + jid + '/records-' + signature + '.json'
            try: records.update(core.store.json(checkpoint_ref))
            except FileNotFoundError: pass
            output = []
            for n, source in enumerate(manifest):
                check(); key = source['key']; items = [c for c in state['selected'] if c.get('record_key') == key]
                if key not in records:
                    value, quotes = providers.extract_with_evidence(context(items), data['record_schema'], items)
                    validate(value, data['record_schema']); records[key] = {'fields': value, 'evidence': quotes}
                    core.store.put_json(checkpoint_ref, records)
                output.append({'source_filename': source['name'], 'source_key': key, 'fields': records[key]['fields']})
                evidence.extend(q | {'field': f'/records/{n}/fields' + q['field'], 'source_key': key, 'source_filename': source['name']} for q in records[key]['evidence'])
                data['record_progress'] = {'completed': n + 1, 'total': len(manifest), 'current_filename': source['name']}
                core.store.put_json(record.ref, data)
            result = {'records': output}
        else:
            result, evidence = providers.extract_with_evidence(context(state['selected']), data['schema'], state['selected'])
        stage('generate', 'completed')
        return {'result': result, 'evidence': evidence, 'records': records}

    def validate_result(state):
        stage('validate'); validate(state['result'], data['schema'])
        parquet_results.encoded(state['result']); stage('validate', 'completed')
        return {}

    def persist(state):
        stage('writing_output')
        output = parquet_results.persist(record.id, record.version, data | {'result': state['result'], 'evidence': state['evidence']})
        stage('writing_output', 'completed'); return {'output': output}

    graph = StateGraph(State)
    for name, node in [('retrieving', retrieve), ('generate', generate), ('validate', validate_result), ('writing_output', persist)]: graph.add_node(name, node)
    graph.add_edge(START, 'retrieving'); graph.add_edge('retrieving', 'generate')
    graph.add_edge('generate', 'validate'); graph.add_edge('validate', 'writing_output'); graph.add_edge('writing_output', END)
    compiled = graph.compile(checkpointer=saver)
    config = {'configurable': {'thread_id': jid}, 'recursion_limit': 12}
    with tracing_context(enabled=False):
        previous = compiled.get_state(config)
        if previous.values and not previous.next:
            state = previous.values
        else:
            state = compiled.invoke(None if previous.values else {'records': {}}, config)
    # Verify persisted output even when replaying a completed graph after a crash.
    saved = parquet_results.load(data | state['output'])
    if parquet_results.encoded(saved['result']) != parquet_results.encoded(state['result']):
        raise ValueError('Recovered output differs from its validated checkpoint')
    data.update(result=state['result'], evidence=state['evidence'], retrieval=state['diagnostics'], **state['output'])
    return data
