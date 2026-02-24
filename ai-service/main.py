from fastapi import FastAPI
from routers import ask, dashboard

app = FastAPI(title="Agentic BI - AI Service", version="0.1.0")

app.include_router(ask.router)
app.include_router(dashboard.router)

@app.get("/health")
def health():
    return {"status": "ok"}