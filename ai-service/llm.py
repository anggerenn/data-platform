from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from schema_context import load_schema_context
from typing import Optional

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


# ─────────────────────────────────────────────────────────────────────────────
# SHARED HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _chat(system: str, user: str, temperature: float = 0) -> str:
    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


def _chat_with_history(system: str, history: list[dict], question: str, temperature: float = 0) -> str:
    messages = [{"role": "system", "content": system}]
    for turn in history:
        role    = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})
    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 1 — RELEVANCE
# Single job: is this a genuine analytics question?
# Called by Captain before anything else — cheapest possible gate.
# ─────────────────────────────────────────────────────────────────────────────

_RELEVANCE_PROMPT = (
    "You are a relevance filter for a data analytics assistant. "
    "Decide if the user's message is a genuine data or analytics question answerable with SQL. "
    "Return 'relevant' for questions about data, metrics, trends, filters, or follow-up analytics. "
    "Return 'irrelevant' for random characters, nonsense, profanity, or off-topic conversation. "
    "When in doubt, return 'relevant'. "
    "Reply with exactly one word: relevant or irrelevant."
)

def is_relevant_query(message: str) -> bool:
    """Returns False only when DeepSeek is confident the message is not a data question."""
    result = _chat(_RELEVANCE_PROMPT, message)
    return "irrelevant" not in result.lower()


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 2 — INTENT
# Single job: explore or dashboard?
# ─────────────────────────────────────────────────────────────────────────────

_INTENT_PROMPT = (
    "You are an intent classifier for a data analytics assistant. "
    "Classify the user's message as 'dashboard' or 'explore'. "
    "Return 'dashboard' only if the user explicitly wants to save, create, or persist a dashboard. "
    "Return 'explore' for everything else. "
    "Reply with exactly one word: dashboard or explore."
)

def classify_intent(message: str) -> str:
    result = _chat(_INTENT_PROMPT, message)
    return "dashboard" if "dashboard" in result.lower() else "explore"


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 3 — CLARIFY
# Single job: is the filter/scope ambiguous given history?
# Runs BEFORE SQL so it can stop the pipeline early.
# Only asks about data scope — never about chart preferences or formatting.
# ─────────────────────────────────────────────────────────────────────────────

_CLARIFY_PROMPT = """You are a context checker for a data analytics assistant.

Your only job: decide if the new question has AMBIGUOUS filter or scope carryover from the conversation history.

Rules:
- Return a clarification question ONLY if:
  (a) The previous query had a specific filter (city, date range, category, customer, etc.), AND
  (b) The new question is about a different metric or topic, AND
  (c) The user did NOT use reference words like: that, same, those, also, filter that, break that down, for the same
- If any of those reference words are present, do NOT clarify — the user wants to carry context forward
- If the new question is self-contained and unambiguous, do NOT clarify
- If there is no meaningful history, do NOT clarify
- Your question must be short, specific, and about data scope only — never about charts, columns, or formatting
- Good example: "Are you still filtering for New York, or should this cover all cities?"
- Bad example: "Should I exclude any columns from the chart?" — never ask this

Return format:
- If clarification is needed: return only the question text, nothing else
- If no clarification needed: return exactly the word NONE
"""

def should_clarify(question: str, history: list[dict]) -> Optional[str]:
    """
    Returns a clarification question string if scope is ambiguous, else None.
    Captain calls this before SQL agent — if it returns a question, pipeline stops.
    """
    if not history:
        return None

    # Build a compact history summary for the clarify agent
    history_text = "\n".join(
        f"[{t['role'].upper()}]: {t['content']}"
        for t in history[-6:]
        if t.get("role") in ("user", "assistant") and t.get("content")
    )

    prompt = f"Conversation history:\n{history_text}\n\nNew question: {question}"
    result = _chat(_CLARIFY_PROMPT, prompt).strip()

    if result.upper() == "NONE" or not result:
        return None
    return result


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 4 — SQL
# Single job: convert question to a single valid DuckDB SELECT query.
# No chart logic, no clarification logic, no intent logic — just SQL.
# ─────────────────────────────────────────────────────────────────────────────

_SQL_PROMPT = """You are a SQL generation expert for DuckDB. Convert the user's question into a single valid DuckDB SELECT query.

Schema:
{schema}

Rules:
- Return ONLY a single SQL query — no explanations, no markdown, no backticks, no multiple statements
- Use fully qualified table names (schema.table) exactly as shown — strip [CANONICAL] and [STAGING] labels
- Only use tables and columns from the schema above
- Prefer [CANONICAL] tables for business questions; use [STAGING] only if user asks for raw data
- No INSERT, UPDATE, DELETE, DROP statements
- Cast VARCHAR dates: TRY_CAST(column AS DATE)
- Date format: strftime('%Y-%m', TRY_CAST(column AS DATE))
- Year/month filter: YEAR(TRY_CAST(column AS DATE)) or MONTH(TRY_CAST(column AS DATE))
- String filters: always ILIKE (case-insensitive), e.g. WHERE city ILIKE 'new york'
- Partial matches: WHERE city ILIKE '%york%'

Window function rules:
- LAG() and LEAD() must operate on pre-aggregated data — never on raw rows
- Always aggregate in a CTE first, then apply window functions in the outer SELECT:
    WITH agg AS (
        SELECT strftime('%Y-%m', TRY_CAST(date_col AS DATE)) AS month,
               SUM(value) AS total
        FROM schema.table GROUP BY 1
    )
    SELECT month, total,
           LAG(total) OVER (ORDER BY month) AS prev,
           (total - LAG(total) OVER (ORDER BY month))
             / LAG(total) OVER (ORDER BY month) * 100 AS growth_pct
    FROM agg ORDER BY month
- Count parentheses — opening and closing must match exactly

If the question cannot be answered from the schema, return exactly:
SELECT 'I could not find relevant data for that question.' AS message
"""

def clean_sql(sql: str) -> str:
    sql = sql.strip()
    if sql.startswith("```"):
        sql = sql.split("\n", 1)[-1]
        sql = sql.rsplit("```", 1)[0]
    return sql.strip()

def generate_sql(question: str, history: Optional[list[dict]] = None) -> str:
    schema   = load_schema_context()
    system   = _SQL_PROMPT.format(schema=schema)
    history  = history or []
    raw      = _chat_with_history(system, history[-6:], question)
    return clean_sql(raw)


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 5 — VISUAL
# Single job: given column names + a sample row, decide which columns to
# exclude from the chart. Returns a list of column names to exclude.
# Called only when results have numeric columns — skipped otherwise.
# ─────────────────────────────────────────────────────────────────────────────

_VISUAL_PROMPT = """You are a chart configuration assistant.

Given a user's question, the result column names, and the user's explicit chart preferences,
decide which columns (if any) should be excluded from the chart visualization.

Rules:
- Only exclude a column if the user EXPLICITLY said they don't want it in the chart
  (e.g. "exclude rank", "don't visualize month", "hide city from chart")
- Do NOT exclude columns based on your own judgement — only act on explicit user instructions
- If the user said nothing about chart exclusions, return an empty list
- Return ONLY a JSON array of column name strings to exclude, e.g. ["rank"] or ["month", "city"] or []
- No explanation, no markdown, just the JSON array
"""

def plan_visualization(question: str, columns: list[str]) -> list[str]:
    """
    Returns a list of column names to exclude from the chart.
    Only called when the result has numeric columns worth charting.
    """
    user_msg = (
        f"User question: {question}\n"
        f"Result columns: {', '.join(columns)}\n"
        "Which columns (if any) did the user explicitly ask to exclude from the chart?"
    )
    result = _chat(_VISUAL_PROMPT, user_msg)
    result = result.strip()

    # Parse JSON array — fall back to empty list on any parse error
    import json, re
    match = re.search(r'\[.*?\]', result, re.DOTALL)
    if match:
        try:
            excluded = json.loads(match.group())
            if isinstance(excluded, list):
                return [str(c) for c in excluded]
        except (json.JSONDecodeError, ValueError):
            pass
    return []


if __name__ == "__main__":
    print("=== Agent smoke tests ===\n")

    print("1. Relevance:")
    print("  'asdfgh'         →", is_relevant_query("asdfgh"))
    print("  'top 5 cities'   →", is_relevant_query("top 5 cities"))

    print("\n2. Intent:")
    print("  'show revenue'           →", classify_intent("show revenue"))
    print("  'create a dashboard'     →", classify_intent("create a dashboard"))

    print("\n3. SQL:")
    print(generate_sql("What are the top 5 cities by total revenue?"))

    print("\n4. Visual:")
    print("  'rank customers, exclude rank from chart', [customer_id, total, rank] →",
          plan_visualization("rank customers, exclude rank from chart",
                             ["customer_id", "total_order_value", "rank"]))
    print("  'show monthly revenue', [month, revenue] →",
          plan_visualization("show monthly revenue", ["month", "revenue"]))