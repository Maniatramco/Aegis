"""Preserve raw results and separately record canonical-evidence adjudication."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
directory=root/'docs/testing/results/agent-accuracy-2026-10-12'
def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
before=load(root/'docs/testing/results/agent-context-2026-10-12/real-model-benchmark.json')
current=load(directory/'current-core.json')
extended=load(directory/'current-extended-raw.json')
assert len(extended['cases'])==12 and extended.get('completed_at')
previous={c['id']:c for c in before['cases']};now={c['id']:c for c in current['cases']}
common=sorted(set(previous)&set(now))
assert len(common)==10 and before['fixtures']==current['fixtures']
assert all(previous[id].get('question')==now[id].get('question') for id in common)
def score(passed,total):return {'passed':passed,'total':total,'percentage':round(100*passed/total,2)}
prior=score(sum(previous[id]['passed'] for id in common),len(common))
after=score(sum(now[id]['passed'] for id in common),len(common))
reviews={
    'semantic_prompt': {'answer_accuracy':False,'tool_accuracy':False,
        'reason':'Mapped prompt exists in the selected dataset, but the model chose accessible_datasets scope for prompt content. Search correctly rejected that scope; the intended request was not answered.'},
    'missing_saved_bob': {'answer_accuracy':False,'tool_accuracy':False,
        'reason':'Bob has an original file but no saved extraction. The selector omitted the requested person predicate and returned Alice\u2019s city; reading a result from the right family is insufficient.'},
    'missing_invoice_field': {'answer_accuracy':False,'tool_accuracy':False,
        'reason':'The substring-only refusal checker matched \u201cNo file\u201d, but Alice Example is a saved person name, not a literal filename. No canonical field read occurred; the answer did not establish that the requested field was missing.'},
}
for case in extended['cases']:
    case['raw_checks']=dict(case['checks'])
    case['adjudication']=reviews.get(case['id'],{'reason':'Fixture values, scope and observed source/tool reads support the predeclared success checks.'})
    for key,value in case['adjudication'].items():
        if key!='reason':case['checks'][key]=value
    case['passed']=all(case['checks'].values())
extended['raw_summary']=extended['summary']
extended['summary']={key:score(sum(c['checks'][key] for c in extended['cases']),12) for key in ('answer_accuracy','tool_accuracy')}
extended['summary']['end_to_end']=score(sum(c['passed'] for c in extended['cases']),12)
extended['grading_review']='All twelve answers/trajectories reviewed against canonical fixtures; raw scores preserved. Tool accuracy includes arguments/scope, not just function family. No requests retried and no product changes made.'
(directory/'current-extended-reviewed.json').write_text(json.dumps(extended,indent=2)+'\n',encoding='utf-8')
comparison={'recent_baseline':{'path':'docs/testing/results/agent-context-2026-10-12/real-model-benchmark.json','model':before.get('model'),'started_at':before['started_at']},
    'current_model':current['model'],'same_fixture_hashes':True,'common_case_ids':common,
    'matched_cases':{'before':prior,'after':after,'percentage_point_change':round(after['percentage']-prior['percentage'],2),
        'relative_percentage_change':round(100*(after['percentage']-prior['percentage'])/prior['percentage'],2)},
    'new_extended_cases':extended['summary'],
    'overall_current_task_success':score(current['passed_cases']+sum(c['passed'] for c in extended['cases']),22),
    'limitations':['Historical comparison, not a side-by-side rerun of the old executable. Same fixture hashes/questions and Qwen3:4b weights; registrations/context-output settings differ.',
        'No pre-change score exists for the new twelve cases. They cannot establish a percentage improvement from unified search.',
        'One deterministic run per case on synthetic fixtures; this is not a general accuracy estimate or a latency SLO.'],
    'product_changed_during_measurement':False}
(directory/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n',encoding='utf-8')
print(json.dumps(comparison,indent=2))
