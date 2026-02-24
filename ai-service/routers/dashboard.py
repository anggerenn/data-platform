from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from llm import generate_sql
from superset_client import get_session, get_database_id, get_or_create_dataset, create_chart, create_dashboard

router = APIRouter()

class DashboardRequest(BaseModel):
    title: str
    question: str
    table_name: str
    schema: str
    db_name: str = "DuckDB"

@router.post("/create-dashboard")
def create_dashboard_endpoint(body: DashboardRequest):
    try:
        session = get_session()
        sql = generate_sql(body.question)
        database_id = get_database_id(session, body.db_name)
        dataset_id = get_or_create_dataset(session, body.table_name, body.schema, database_id, sql=sql)
        chart_id = create_chart(session, body.title, dataset_id)
        result = create_dashboard(session, body.title, [chart_id], chart_names=[body.title])
        return {
            "question": body.question,
            "sql": sql,
            "chart_id": chart_id,
            "dataset_id": dataset_id,
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))