"""Unit tests for BM25Store (vanna/vec.py)."""
import pytest
from vec import BM25Store


@pytest.fixture
def store(tmp_path):
    return BM25Store(path=str(tmp_path / 'bm25'))


def test_empty_store_returns_nothing(store):
    assert store.get_related_ddl('revenue') == []
    assert store.get_related_documentation('revenue') == []
    assert store.get_similar_question_sql('revenue') == []


def test_add_and_retrieve_ddl(store):
    store.add_ddl('CREATE TABLE daily_sales (revenue Float64)')
    results = store.get_related_ddl('daily_sales revenue')
    assert len(results) == 1
    assert 'daily_sales' in results[0]


def test_add_and_retrieve_documentation(store):
    store.add_documentation('Use total_revenue for all revenue analysis.')
    results = store.get_related_documentation('revenue analysis')
    assert len(results) == 1


def test_add_and_retrieve_question_sql(store):
    store.add_question_sql(
        'total revenue by category',
        'SELECT category, SUM(total_revenue) FROM daily_sales GROUP BY category',
    )
    results = store.get_similar_question_sql('revenue by category')
    assert len(results) == 1
    assert results[0]['question'] == 'total revenue by category'
    assert 'SUM(total_revenue)' in results[0]['sql']


def test_relevant_scores_higher_than_irrelevant(store):
    store.add_documentation('Total revenue is the primary business metric for sales analysis.')
    store.add_documentation('Customer churn rate measures subscription cancellations.')
    relevant = store.get_related_documentation('revenue sales metric', top_k=1)
    assert relevant and 'revenue' in relevant[0].lower()


def test_top_k_limits_results(store):
    for i in range(10):
        store.add_documentation(f'Revenue metric number {i} for sales analysis.')
    results = store.get_related_documentation('revenue sales', top_k=3)
    assert len(results) <= 3


def test_persistence(tmp_path):
    path = str(tmp_path / 'bm25')
    s1 = BM25Store(path)
    s1.add_documentation('Total revenue is the primary metric.')
    s1.add_question_sql('revenue by city', 'SELECT city, SUM(total_revenue) FROM daily_sales GROUP BY city')

    s2 = BM25Store(path)  # reload from same path
    results = s2.get_related_documentation('revenue metric')
    assert len(results) == 1
    sql_results = s2.get_similar_question_sql('revenue by city')
    assert len(sql_results) == 1


def test_dict_tiebreaker_no_error(store):
    """Regression: sorted(zip(scores, dicts)) raises TypeError when scores tie."""
    store.add_question_sql('q1', 'SELECT 1')
    store.add_question_sql('q2', 'SELECT 2')
    store.add_question_sql('q3', 'SELECT 3')
    # All-zero scores when no tokens match — all three entries tie → must not raise
    results = store.get_similar_question_sql('zzzzz_no_match')
    assert isinstance(results, list)
