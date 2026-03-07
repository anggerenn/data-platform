"""Unit tests for pure functions in vanna/agents/housekeeper.py."""
from unittest.mock import patch, MagicMock
import pytest

from agents.housekeeper import (
    _normalise_field,
    _keywords,
    _jaccard,
    _slugify,
    check,
)
from agents.planner import PRD


# ── _normalise_field ──────────────────────────────────────────────────────────

def test_normalise_strips_model_prefix_and_agg_suffix():
    assert _normalise_field('daily_sales_total_revenue_sum') == 'total revenue'


def test_normalise_strips_agg_suffix_only():
    # Only 2-part prefix stripped; 3+ part prefixes leave the middle
    result = _normalise_field('revenue_sum')
    assert 'sum' not in result


def test_normalise_replaces_underscores():
    result = _normalise_field('daily_sales_order_count')
    assert '_' not in result


# ── _keywords ─────────────────────────────────────────────────────────────────

def test_keywords_filters_stopwords():
    kws = _keywords('show me the total revenue by city')
    assert 'the' not in kws
    assert 'by' not in kws
    assert 'show' not in kws


def test_keywords_filters_short_words():
    kws = _keywords('revenue of a city')
    assert 'of' not in kws
    assert 'a' not in kws


def test_keywords_returns_meaningful_words():
    kws = _keywords('revenue city category')
    assert 'revenue' in kws
    assert 'city' in kws
    assert 'category' in kws


# ── _jaccard ──────────────────────────────────────────────────────────────────

def test_jaccard_zero_on_no_overlap():
    assert _jaccard({'revenue', 'city'}, {'orders', 'customers'}) == 0.0


def test_jaccard_one_on_identical():
    s = {'revenue', 'city', 'category'}
    assert _jaccard(s, s) == 1.0


def test_jaccard_partial_overlap():
    score = _jaccard({'revenue', 'city', 'category'}, {'revenue', 'city', 'orders'})
    assert 0 < score < 1


def test_jaccard_empty_set_returns_zero():
    assert _jaccard(set(), {'revenue'}) == 0.0
    assert _jaccard({'revenue'}, set()) == 0.0


# ── _slugify ──────────────────────────────────────────────────────────────────

def test_slugify_spaces_to_underscores():
    assert _slugify('City Revenue Performance') == 'city_revenue_performance'


def test_slugify_strips_leading_trailing_underscores():
    assert not _slugify('  dashboard  ').startswith('_')


# ── check() — verdict routing ─────────────────────────────────────────────────

def _make_prd(**kwargs):
    defaults = dict(
        title='Revenue by City',
        problem_statement='We lack visibility into city-level revenue trends.',
        objective='Track city revenue',
        audience='Sales managers',
        metrics=['total revenue', 'city'],
        action_items=[],
    )
    defaults.update(kwargs)
    return PRD(**defaults)


def test_check_returns_none_when_no_fingerprints():
    with patch('agents.housekeeper._build_fingerprints', return_value=[]):
        result = check(_make_prd())
    assert result.verdict == 'none'


def test_check_full_on_high_overlap():
    fp = [{'name': 'Revenue Dashboard', 'url': 'http://ld/1', 'keywords': {'revenue', 'city', 'track'}}]
    with patch('agents.housekeeper._build_fingerprints', return_value=fp):
        prd = _make_prd(metrics=['revenue', 'city', 'track'])
        result = check(prd)
    assert result.verdict == 'full'
    assert result.matched_dashboard_name == 'Revenue Dashboard'


def test_check_none_on_low_overlap():
    fp = [{'name': 'Churn Dashboard', 'url': 'http://ld/2', 'keywords': {'churn', 'subscription', 'cancellation'}}]
    with patch('agents.housekeeper._build_fingerprints', return_value=fp):
        result = check(_make_prd(metrics=['revenue', 'city']))
    assert result.verdict == 'none'
