import duckdb
from config import ANALYTICS_DB_PATH

def execute_query(sql: str) -> list[dict]:
    """
    Executes a SQL query against DuckDB and returns results as a list of dicts.
    """
    con = duckdb.connect(ANALYTICS_DB_PATH, read_only=True)
    try:
        result = con.execute(sql).fetchdf()
        return result.to_dict(orient="records")
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