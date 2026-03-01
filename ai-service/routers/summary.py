from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import httpx

router = APIRouter()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

SUMMARY_SYSTEM_PROMPT = """You are a session summarizer for a data analytics assistant.
You will be given the conversation history of a data exploration session.
Your job is to produce a concise, structured markdown summary that a user can paste at the start of their NEXT session to restore full context.

The summary must follow this exact structure:

## Session Summary

**Explored:** [1-2 sentence description of what the user was investigating]

**Tables Used:**
- `schema.table_name` — [brief description of what data it holds, inferred from the conversation]

**Key Filters & Entities:**
- [list of specific filters, date ranges, customer names, product categories, or other constraints that appeared in queries]

**Last Query:**
```sql
[the most recent SQL query executed, verbatim]
```

**Open Questions / Next Steps:**
- [any questions the user was still working towards, or logical next steps based on the conversation]

---
*Paste this block at the start of your next session to restore context.*

Rules:
- Be specific — include actual table names, column names, date ranges, values from the conversation
- If no SQL was found in the history, omit the Last Query section
- Keep the entire summary under 400 words
- Output ONLY the markdown block, no preamble or explanation
"""


class SummaryRequest(BaseModel):
    history: list[dict]  # [{role: 'user'|'assistant', content: str}]


@router.post("/summary")
async def generate_summary(body: SummaryRequest):
    if not body.history:
        raise HTTPException(status_code=400, detail="history is required and must not be empty")

    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DEEPSEEK_API_KEY not configured")

    # Build the messages array: system prompt + full history as a single user turn
    history_text = "\n\n".join(
        f"[{msg['role'].upper()}]: {msg['content']}"
        for msg in body.history
        if msg.get("role") and msg.get("content")
    )

    messages = [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": f"Here is the full conversation history:\n\n{history_text}\n\nGenerate the session summary now."},
    ]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": messages,
                    "max_tokens": 600,
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            data = response.json()
            summary_md = data["choices"][0]["message"]["content"].strip()
            return {"summary": summary_md}

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"DeepSeek API error: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))