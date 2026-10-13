"""Non-destructive live-service verification; run inside the configured API container.

Only the explicitly fictional QA dataset is included in saved proof output.
"""
import json
from sqlalchemy import select
from app import core, knowledge, dataset_access, parquet_results

DATASET = '8a1a0283-a056-5b83-a68d-5d5cd0d7cc82'
EXTRACTION = 'eaefbdf5-4641-45f9-8158-187768f770f5'
with core.Session() as session:
    record = session.get(core.Record, EXTRACTION)
    actor = record.owner
token = dataset_access.request_actor.set(actor)
try:
    data = parquet_results.load(core.store.json(record.ref))
    assert record.version == 2 and data['result']['total'] == 1650
    first = knowledge.search('Blue Harbor supplier invoice number total', actor,
                             DATASET, source_types=['extraction'])
    assert any('1650' in hit['text'] for hit in first['matches'])
    assert all(hit['source_version'] == 2 for hit in first['matches'])
    snapshot, sync = knowledge.sync(actor, DATASET)
    assert sync['upserted'] == 0 and sync['failed_entities'] == 0
    from app import providers
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    with core.execution_context(snapshot):
        points, _ = providers.client().scroll(snapshot['knowledge_collection'],
            scroll_filter=Filter(must=[FieldCondition(key='dataset_id',match=MatchValue(value=DATASET))]),
            limit=100, with_payload=True, with_vectors=False)
    assert not any(p.payload['source_type']=='extraction' and p.payload['source_version']==1 for p in points)
    assert {'dataset','document','document_chunk','prompt','extraction'} <= {p.payload['source_type'] for p in points}
    conversation = dataset_access.get_record('f53a4c0b-7367-4aca-84ef-4f0b9ffa9552', actor, 'conversation')
    replies = [m for m in core.store.json(conversation.ref)['messages'] if m.get('role')=='assistant']
    semantic = next(m for m in replies if any(o['tool']=='search_knowledge' for o in m.get('tool_trace', [])))
    catalog = replies[-1]
    assert 'unified-knowledge-invoice.txt' in catalog['text'] and '1' in catalog['text']
    assert [o['tool'] for o in catalog['tool_trace']] == ['list_documents']
    assert semantic['request_route']['decision']['source'] == 'knowledge'
    skills_conversation = dataset_access.get_record('45d4e1ab-b3cd-4888-9d6a-8a736610c5d6', actor, 'conversation')
    skills = core.store.json(skills_conversation.ref)['messages'][-1]
    assert 'tool-step limit' not in skills['text'] and 'Kubernetes' in skills['text'] and 'Pytest' in skills['text']
    skill_reads = [o for o in skills['tool_trace'] if o['tool']=='read_extraction_results']
    assert len(skill_reads)==3 and all('skills' in o['arguments']['fields'] and not o['arguments']['filters'] for o in skill_reads)
    probes = []
    for source_type, question, expected in [
        ('prompt', 'Schema for supplier and invoice total fields', 'invoice_number'),
        ('document_chunk', 'Original invoice amount from Blue Harbor', '1640'),
        ('model', 'Chat agent maximum context and output tokens', '262144'),
        ('application', 'Compare edited extracted fields against original document in review', 'original')]:
        found = knowledge.search(question, actor, DATASET, source_types=[source_type])['matches']
        assert found and any(expected in h['text'] for h in found), source_type
        probes.append({'type': source_type, 'query': question,
                       'supported_expected_value': expected, 'matches': len(found)})
    proof = {'dataset_id': DATASET, 'extraction_id': EXTRACTION,
        'version': record.version, 'review_status': data['review_status'],
        'result': data['result'], 'parquet_reference': data['output_reference'],
        'sync': sync, 'dataset_point_types': sorted({p.payload['source_type'] for p in points}),
        'old_extraction_points_removed': True,
        'agent_semantic_tool': 'search_knowledge',
        'agent_semantic_answer': semantic['text'],
        'agent_exact_catalog_answer': catalog['text'],
        'agent_exact_catalog_tool': 'list_documents',
        'skills_regression': {'completed': True, 'result_reads': len(skill_reads),
                              'projected_fields': skill_reads[0]['arguments']['fields']},
        'typed_semantic_probes': probes,
        'search': [{'source_type': h['source_type'], 'version': h['source_version'],
                    'text': h['text']} for h in first['matches']]}
    print(json.dumps(proof, indent=2))
finally:
    dataset_access.request_actor.reset(token)
