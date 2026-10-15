"""Field-directed scoped retrieval with explicit context expansion and coverage."""
import time
import os
from . import core, providers, reranker, runtime_config


def questions(schema):
    properties = schema.get('properties', {})
    return [(key, 'Find evidence for ' + key.replace('_', ' ') + '. ' + str(value.get('description', '')))
            for key, value in properties.items()] or [('result', schema.get('description') or 'Find the requested structured fields')]


def retrieve(schema, documents, snapshot, sources, *, source_key=None, progress=None):
    testing = os.getenv('AEGIS_ALLOW_MOCK') == 'true' and snapshot['settings']['embedding_provider'] == 'mock'
    if snapshot['settings']['model_provider'] != 'mock' and not testing and not reranker.enabled():
        raise providers.ProviderError('Extraction requires a semantic reranker. Configure AEGIS_RERANKER=local and install the pinned assets, then retry.')
    started = time.monotonic(); selected = {}; coverage = {}; diagnostics = []
    top_k=runtime_config.get('AEGIS_EXTRACTION_CHUNKS_PER_FIELD')
    neighbors=runtime_config.get('AEGIS_EXTRACTION_NEIGHBOR_CHUNKS')
    eligible = {c['id']: c for c in sources if source_key is None or c.get('source_key') == source_key}
    with core.execution_context(snapshot.get('embedding_execution', snapshot)):
        for field, query in questions(schema):
            if progress: progress('retrieving')
            detail = {}
            candidates = []
            # Each original receives evidence; another document's relevance
            # cannot suppress a requested source in a combined extraction.
            for document in documents:
                if not any(c['document_id'] == document.id for c in eligible.values()): continue
                candidates.extend(providers._retrieve(query, document.owner, [document], reranker.candidate_limit(top_k)))
            candidates = [c for c in candidates if c['chunk_id'] in eligible]
            if progress: progress('reranking')
            ranked = reranker.rank(query, candidates, top_k) if reranker.enabled() else candidates[:top_k]
            coverage[field] = [c['chunk_id'] for c in ranked]
            for hit in ranked:
                chunk = eligible[hit['chunk_id']]; selected[chunk['id']] = chunk
                # Expand to adjacent chunks on this page/section to keep table
                # rows and headings intact; never substitute invented locations.
                ordered = [c for c in eligible.values() if c['document_id'] == chunk['document_id'] and c['page'] == chunk['page']]
                index = next(i for i, c in enumerate(ordered) if c['id'] == chunk['id'])
                for neighbor in ordered[max(0, index - neighbors):index + neighbors + 1]: selected[neighbor['id']] = neighbor
            diagnostics.append({'field': field, 'candidates': len(candidates), 'selected': len(ranked)})
    # Exhaustive arrays/tables require full source coverage. For short documents
    # full context also prevents a weak rank from losing an isolated scalar.
    arrays = any(value.get('type') == 'array' for value in schema.get('properties', {}).values())
    expanded = arrays or sum(len(c['text']) for c in eligible.values()) <= runtime_config.get('AEGIS_EXTRACTION_FULL_CONTEXT_CHARS')
    if expanded: selected.update(eligible)
    chunks = [c for c in eligible.values() if c['id'] in selected]
    if not chunks: raise ValueError('No indexed evidence is available for the requested fields')
    if sum(len(c['text']) for c in chunks) > runtime_config.get('AEGIS_EXTRACTION_MAX_EVIDENCE_CHARS'):
        raise ValueError('Complete requested evidence exceeds the context budget. Narrow the prompt/document scope; evidence was not truncated.')
    return chunks, {'seconds': round(time.monotonic() - started, 3), 'fields': diagnostics,
                    'coverage': coverage, 'context_expanded': expanded, 'selected_chunks': len(chunks),
                    'reranker': reranker.MODEL_ID if reranker.enabled() else 'mock-test-only',
                    'reranker_revision': reranker.REVISION if reranker.enabled() else None}
