import re
import duckdb
import math
from config import ANALYTICS_DB_PATH

# ─── SQL GUARD ────────────────────────────────────────────────────────────────
# Blocked statement types — matched against the first meaningful token in the SQL.
# This is a hard stop BEFORE execution, independent of DuckDB's read_only flag.
_BLOCKED_STATEMENTS = re.compile(
    r'^\s*(DELETE|DROP|INSERT|UPDATE|CREATE|ALTER|TRUNCATE|REPLACE|MERGE|CALL|EXEC|GRANT|REVOKE|ATTACH|DETACH|COPY|EXPORT|IMPORT)\b',
    re.IGNORECASE
)

# Only these statement types are permitted at the top level
_ALLOWED_STATEMENTS = re.compile(
    r'^\s*(SELECT|WITH)\b',
    re.IGNORECASE
)

class UnsafeSQLError(ValueError):
    """Raised when generated SQL contains a disallowed statement."""
    pass


def _strip_sql_comments(sql: str) -> str:
    """Remove leading SQL comments (-- line and /* block */ comments)."""
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    sql = re.sub(r'--[^\n]*', '', sql)
    return sql.strip()


def validate_sql(sql: str) -> None:
    """
    Raises UnsafeSQLError if the SQL is not a plain SELECT/WITH query.
    Checks both an allowlist (must start with SELECT or WITH) and a
    blocklist (explicit destructive keywords) for defence in depth.
    """
    stripped = _strip_sql_comments(sql)

    if not stripped:
        raise UnsafeSQLError("Empty SQL query.")

    if _BLOCKED_STATEMENTS.match(stripped):
        # Extract the first token for a clear error message
        first_token = stripped.split()[0].upper()
        raise UnsafeSQLError(
            f"Disallowed SQL statement: {first_token}. Only SELECT queries are permitted."
        )

    if not _ALLOWED_STATEMENTS.match(stripped):
        first_token = stripped.split()[0].upper() if stripped.split() else "UNKNOWN"
        raise UnsafeSQLError(
            f"Unrecognised SQL statement type: {first_token}. Only SELECT queries are permitted."
        )


def clean_results(records: list[dict]) -> list[dict]:
    """Replace non-JSON-compliant float values (NaN, Inf) with None."""
    cleaned = []
    for row in records:
        clean_row = {}
        for k, v in row.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                clean_row[k] = None
            else:
                clean_row[k] = v
        cleaned.append(clean_row)
    return cleaned


def execute_query(sql: str) -> list[dict]:
    """
    Validates and executes a SQL query against DuckDB.
    - Raises UnsafeSQLError for non-SELECT statements (caught upstream in chat.py).
    - Returns a structured fallback row on DuckDB execution errors so the widget
      renders a friendly message instead of a 500.
    """
    validate_sql(sql)

    con = duckdb.connect(ANALYTICS_DB_PATH, read_only=True)
    try:
        result = con.execute(sql).fetchdf()
        return clean_results(result.to_dict(orient="records"))
    except duckdb.Error as e:
        # Return a fallback row — same shape as the LLM fallback so isFallbackResult()
        # in the widget handles it correctly and renders as a plain text message.
        return [{"message": f"The query could not be executed: {e}"}]
    finally:
        con.close()


if __name__ == "__main__":
    from llm import generate_sql
    import json

    question = "What are the top 5 cities by total revenue?"
    sql = generate_sql(question)
    print(f"SQL: {sql}\n")
    results = execute_query(sql)
    print(json.dumps(results, indent=2, default=str))