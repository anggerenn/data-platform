from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from llm import generate_sql
from sql_engine import execute_query

router = APIRouter()

class AskRequest(BaseModel):
    question: str

@router.post("/ask")
def ask(body: AskRequest):
    try:
        sql = generate_sql(body.question)
        results = execute_query(sql)
        return {
            "question": body.question,
            "sql": sql,
            "results": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))