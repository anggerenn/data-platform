"""Unit tests for _detect_date_range in vanna/agents/router.py."""
import os
import sys
from unittest.mock import MagicMock

# ── Path + stub setup (mirrors test_answer_semantic.py) ─────────────────────
_vanna_dir = os.path.join(os.path.dirname(__file__), '..', 'vanna')
if _vanna_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_vanna_dir))

for _mod in ('vn', 'agents._model', 'pydantic_ai', 'pydantic_ai.models.openai'):
    sys.modules.setdefault(_mod, MagicMock())

sys.modules['agents._model'].make_model = MagicMock(return_value=MagicMock())
sys.modules['vn'].VannaAI = MagicMock

from agents.router import _detect_date_range  # noqa: E402


# ── _detect_date_range ───────────────────────────────────────────────────────

def test_detects_iso_date_column():
    rows = [
        {"order_date": "2026-01-15", "revenue": 100},
        {"order_date": "2026-03-01", "revenue": 200},
        {"order_date": "2026-02-10", "revenue": 150},
    ]
    result = _detect_date_range(rows, ["order_date", "revenue"])

    assert result["from"] == "2026-01-15"
    assert result["to"]   == "2026-03-01"
    assert result["column"] == "order_date"


def test_returns_empty_when_no_date_column():
    rows = [{"city": "Jakarta", "revenue": 100}]
    assert _detect_date_range(rows, ["city", "revenue"]) == {}


def test_returns_empty_when_date_col_has_non_iso_values():
    rows = [{"order_date": "January 2026"}, {"order_date": "February 2026"}]
    assert _detect_date_range(rows, ["order_date"]) == {}


def test_single_row_from_equals_to():
    rows = [{"order_date": "2026-03-01", "revenue": 500}]
    result = _detect_date_range(rows, ["order_date", "revenue"])

    assert result["from"] == "2026-03-01"
    assert result["to"]   == "2026-03-01"


def test_skips_null_date_values():
    rows = [
        {"order_date": None,         "revenue": 100},
        {"order_date": "2026-02-01", "revenue": 200},
        {"order_date": "2026-03-15", "revenue": 300},
    ]
    result = _detect_date_range(rows, ["order_date", "revenue"])

    assert result["from"] == "2026-02-01"
    assert result["to"]   == "2026-03-15"


def test_picks_first_matching_date_column():
    rows = [
        {"order_date": "2026-01-01", "ship_date": "2026-01-05", "revenue": 100},
    ]
    result = _detect_date_range(rows, ["order_date", "ship_date", "revenue"])
    # First date column in column order wins
    assert result["column"] == "order_date"


def test_ignores_non_date_named_numeric_column():
    rows = [{"revenue": 100}, {"revenue": 200}]
    assert _detect_date_range(rows, ["revenue"]) == {}
