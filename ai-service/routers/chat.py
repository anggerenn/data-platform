import re
from pydantic import BaseModel
from sql_engine import execute_query, UnsafeSQLError
from fastapi import APIRouter, HTTPException
from llm import (
    is_relevant_query,
    classify_intent,
    should_clarify,
    generate_sql,
    plan_visualization,
)
from superset_client import (
    get_session, get_database_id, get_or_create_dataset,
    create_chart, create_dashboard,
)
from typing import Optional


router = APIRouter()

DASHBOARD_KEYWORDS = {"dashboard", "save", "create", "persist", "keep", "store"}


# ── Stage-1 junk guard (fast, no API call) ────────────────────────────────────
_JUNK_BLOCKLIST = re.compile(
    r'\b(fuck|shit|bitch|ass|damn|crap|bastard|dick|piss|cock|cunt|motherfuck\w*)\b',
    re.IGNORECASE
)
_PURE_NONSENSE = re.compile(r'^[^a-zA-Z]*$|^\s*[a-zA-Z]\s*$')


def _is_junk_query(query: str) -> bool:
    """
    Two-stage junk detection.
    Stage 1 (no API): profanity blocklist + pure non-alpha / single char.
    Stage 2 (LLM):    anything uncertain goes to is_relevant_query().
    """
    if _JUNK_BLOCKLIST.search(query):
        return True
    if _PURE_NONSENSE.match(query.strip()):
        return True
    return not is_relevant_query(query)


# ── History sanitization ──────────────────────────────────────────────────────
_HISTORY_POISON_PATTERNS = re.compile(
    r'(SQL executed:|could not find relevant|cannot answer|syntax error|server error|'
    r'parser error|unrecognised sql|disallowed sql|^queried|^returned \d|'
    r'^\s*[a-z]{1,3}\s*$)',
    re.IGNORECASE
)


def sanitize_history(history: Optional[list[dict]]) -> list[dict]:
    """
    Strip poisoned, empty, or flooding entries from incoming history.
    Caps at 20 entries — agents internally cap to last 6.
    """
    if not history:
        return []
    cleaned = []
    for entry in history:
        role    = entry.get("role", "")
        content = str(entry.get("content", "")).strip()
        if role not in ("user", "assistant"):
            continue
        if not content:
            continue
        if role == "user" and len(content) <= 2:
            continue
        if role == "assistant" and _HISTORY_POISON_PATTERNS.search(content):
            continue
        cleaned.append({"role": role, "content": content[:500]})
    return cleaned[-20:]


# ── SQL comment parser (fallback path if Visual agent misses chart_exclude) ───
_CHART_EXCLUDE_RE = re.compile(r'--\s*chart_exclude:\s*(.+)$', re.IGNORECASE | re.MULTILINE)


def extract_chart_exclude(sql: str) -> tuple[str, list[str]]:
    match = _CHART_EXCLUDE_RE.search(sql)
    if not match:
        return sql, []
    excluded  = [c.strip() for c in match.group(1).split(',') if c.strip()]
    clean_sql = _CHART_EXCLUDE_RE.sub('', sql).strip().rstrip(';').strip() + ';'
    clean_sql = re.sub(r';+', ';', clean_sql)
    return clean_sql, excluded


def extract_table_info(sql: str) -> tuple[str, str]:
    match = re.search(
        r'(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)',
        sql, re.IGNORECASE
    )
    if match:
        return match.group(2), match.group(1)
    match = re.search(r'(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)', sql, re.IGNORECASE)
    if match:
        return match.group(1), "main"
    return "unknown", "main"


# ── Request model ─────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    query: str
    db_name: str = "DuckDB"
    history: Optional[list[dict]] = None


# ── Shared fallback response helper ──────────────────────────────────────────
def _fallback_response(query: str, message: str) -> dict:
    return {
        "intent": "explore",
        "query": query,
        "sql": None,
        "results": [{"message": message}],
        "columns": ["message"],
        "chart_exclude_columns": [],
        "table_name": None,
    }


# ── CAPTAIN — conditional pipeline ───────────────────────────────────────────
@router.post("/chat")
def chat(body: ChatRequest):
    try:
        query = body.query.strip()

        # ── Step 1: Relevance gate ─────────────────────────────────────────
        # Fast heuristics first, LLM fallback if uncertain.
        # Stops pipeline immediately for junk — no wasted SQL or Clarify calls.
        if _is_junk_query(query.lower()):
            return _fallback_response(query, "Could not find relevant data for that question.")

        # ── Step 2: Intent ────────────────────────────────────────────────
        # Only call LLM classifier if dashboard keywords present — saves a call
        # for the 95% of queries that are plain explore.
        query_lower = query.lower()
        has_dashboard_keywords = any(kw in query_lower for kw in DASHBOARD_KEYWORDS)
        intent = classify_intent(query) if has_dashboard_keywords else "explore"

        # ── Step 3: Sanitize history ──────────────────────────────────────
        clean_history = sanitize_history(body.history)

        # ── Step 4: Clarify ───────────────────────────────────────────────
        # Runs BEFORE SQL — if scope is ambiguous, return the question immediately.
        # Pipeline stops here; user reply comes back as the next query with updated history.
        clarification = should_clarify(query, clean_history)
        if clarification:
            return {
                "intent": "clarify",
                "query": query,
                "sql": None,
                "results": [{"message": clarification}],
                "chart_exclude_columns": [],
                "table_name": None,
            }

        # ── Step 5: SQL generation ────────────────────────────────────────
        raw_sql = generate_sql(query, history=clean_history)

        # Strip any -- chart_exclude comment before execution
        # (SQL agent shouldn't produce these anymore, but kept as safety net)
        sql, sql_comment_excludes = extract_chart_exclude(raw_sql)

        # ── Step 6: Execute ───────────────────────────────────────────────
        try:
            results = execute_query(sql)
        except UnsafeSQLError as e:
            raise HTTPException(status_code=400, detail=str(e))

        columns    = list(results[0].keys()) if results else []
        table_name, schema = extract_table_info(sql)

        # ── Step 7: Visual planning ───────────────────────────────────────
        # Only run if result has columns worth charting (skip for fallback rows,
        # single-column results, or pure-text results).
        has_numeric = any(
            isinstance(v, (int, float))
            for row in results[:1]
            for v in row.values()
        )
        if has_numeric and len(columns) > 1:
            visual_excludes = plan_visualization(query, columns)
        else:
            visual_excludes = []

        # Merge: visual agent takes priority, SQL comment is fallback
        chart_exclude_columns = visual_excludes or sql_comment_excludes

        # ── Step 8: Dashboard branch ──────────────────────────────────────
        if intent == "dashboard":
            session     = get_session()
            database_id = get_database_id(session, body.db_name)
            dataset_id  = get_or_create_dataset(session, table_name, schema, database_id, sql=sql)
            chart_id    = create_chart(session, query[:50], dataset_id)
            dashboard   = create_dashboard(
                session, query[:50], [chart_id], chart_names=[query[:50]]
            )
            return {
                "intent": "dashboard",
                "query": query,
                "sql": sql,
                "results": results,
                "chart_exclude_columns": chart_exclude_columns,
                "table_name": f"{schema}.{table_name}",
                **dashboard,
            }

        # ── Step 8: Explore branch ────────────────────────────────────────
        return {
            "intent": "explore",
            "query": query,
            "sql": sql,
            "results": results,
            "chart_exclude_columns": chart_exclude_columns,
            "table_name": f"{schema}.{table_name}",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))