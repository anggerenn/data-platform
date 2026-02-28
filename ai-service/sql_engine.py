import duckdb
import math
from config import ANALYTICS_DB_PATH

def clean_results(records: list[dict]) -> list[dict]:
    """Replace non-JSON-compliant float values with None."""
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
    Executes a SQL query against DuckDB and returns results as a list of dicts.
    """
    con = duckdb.connect(ANALYTICS_DB_PATH, read_only=True)
    try:
        result = con.execute(sql).fetchdf()
        return clean_results(result.to_dict(orient="records"))
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