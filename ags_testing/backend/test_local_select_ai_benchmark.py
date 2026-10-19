"""Ensure benchmark references and scoring distinguish real count/row errors."""
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('select_ai_accuracy_benchmark',
    Path(__file__).resolve().parents[1] / 'qa' / 'benchmark_local_select_ai.py')
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def test_reference_fixture_totals_are_independently_known():
    a,b = benchmark.variants()
    for rows,docs,size in [(a,13,23936),(b,16,25712)]:
        assert benchmark.reference(rows,'SELECT COUNT(*) FROM LOCAL_DATASETS') == [[7]]
        assert benchmark.reference(rows,'SELECT COUNT(*) FROM LOCAL_DOCUMENTS') == [[docs]]
        assert benchmark.reference(rows,'SELECT COUNT(*) FROM LOCAL_EXTRACTIONS') == [[9]]
        assert benchmark.reference(rows,'SELECT SUM(SIZE_BYTES) FROM LOCAL_DOCUMENTS') == [[size]]


def test_reference_preserves_duplicate_dataset_identity_and_zero_counts():
    a,_ = benchmark.variants()
    sql = 'SELECT s.DATASET_NAME,COUNT(d.DOCUMENT_ID)' + benchmark.DS_DOC + benchmark.GROUP_DS
    rows = benchmark.reference(a,sql)
    assert sorted(row[1] for row in rows if row[0]=='Invoice Operations') == [2,4]
    assert sum(row[1] == 0 for row in rows) == 2


def test_scoring_rejects_duplicate_collapse_fanout_and_null_substitution():
    match = benchmark.result_match
    assert not match([['Invoice Operations',6]],[['Invoice Operations',4],['Invoice Operations',2]])[0]
    assert not match([['Invoice Operations',12,12]],[['Invoice Operations',4,3]])[0]
    assert not match([['Empty Sandbox',0]],[['Empty Sandbox',None]])[0]
    assert not match([[12]],[[13]])[0]


def test_scoring_allows_presentation_changes_without_dropping_duplicate_rows():
    assert benchmark.result_match([[4,'INVOICE OPERATIONS','extra']],[['Invoice Operations',4]])[0]
    assert not benchmark.result_match([['Same']],[['Same'],['Same']])[0]
    assert benchmark.result_match([['Same'],['Same']],[['Same'],['Same']])[0]


def test_explicit_sort_order_and_numeric_types_remain_significant():
    assert benchmark.result_match([[2],[1]],[[1],[2]])[0]
    assert not benchmark.result_match([[2],[1]],[[1],[2]],ordered=True)[0]
    assert not benchmark.result_match([['13']],[[13]])[0]
    assert benchmark.result_match([[13.0]],[[13]])[0]


def test_counterfactual_changes_counts_missing_stewards_and_review_distribution():
    a,b = benchmark.variants()
    assert benchmark.reference(a,'SELECT COUNT(*) FROM LOCAL_DATASETS WHERE STEWARD IS NULL') == [[3]]
    assert benchmark.reference(b,'SELECT COUNT(*) FROM LOCAL_DATASETS WHERE STEWARD IS NULL') == [[2]]
    assert benchmark.reference(a,"SELECT COUNT(*) FROM LOCAL_DOCUMENTS WHERE STATUS='failed'") == [[2]]
    assert benchmark.reference(b,"SELECT COUNT(*) FROM LOCAL_DOCUMENTS WHERE STATUS='failed'") == [[4]]
    sql = 'SELECT COUNT(*) FROM LOCAL_DOCUMENTS'
    assert benchmark.reference(benchmark.scoped(a,['bench_fin_a','bench_contract']),sql) == [[5]]
    assert benchmark.reference(benchmark.scoped(b,['bench_fin_b','bench_public']),sql) == [[9]]
