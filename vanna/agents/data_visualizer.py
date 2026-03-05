"""
Data Visualizer Agent — chart widget mode.

Given column names + a sample of rows, returns a ChartSpec that drives
Plotly rendering in the chat widget.  Returns type=None when no chart
would be useful (e.g. free-form text results, too many dimensions).

Used server-side in app.py after every explore_data result.
"""
import json
import os
from typing import Literal, Optional

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider


class ChartSpec(BaseModel):
    type: Optional[Literal['bar', 'line', 'grouped_bar', 'heatmap', 'kpi']] = None
    x: Optional[str] = None          # column name for x-axis
    y: Optional[str] = None          # primary numeric column
    y_cols: Optional[list[str]] = None   # multiple y columns (line only)
    group: Optional[str] = None      # grouping column (grouped_bar)
    title: Optional[str] = None      # short chart title


_INSTRUCTIONS = """You decide the best Plotly chart for a query result.

Rules:
- 1 row, 1 numeric col → kpi  (set y=that column name)
- date/time col + 1+ numeric cols → line  (x=date, y_cols=numeric cols)
- 1 categorical + 1 numeric col → bar  (x=cat, y=numeric)
- 1 categorical + 1 numeric + 1 more categorical (3 cols) → grouped_bar  (x=first cat, y=numeric, group=second cat)
- 2 categoricals + 1 numeric → heatmap  (x=first cat, y=second cat, value=numeric — but set x/y/group accordingly)
- more than 3 columns, all text, or no clear pattern → type=null (no chart)
- if x would have > 50 unique values and it's not a date → type=null

Return a ChartSpec. Set type=null when a chart would not add value.
Write a concise title (5 words max).
"""


def _build_model() -> OpenAIModel:
    return OpenAIModel(
        'deepseek-chat',
        provider=OpenAIProvider(
            base_url='https://api.deepseek.com',
            api_key=os.environ.get('DEEPSEEK_API_KEY', ''),
        ),
    )


_agent = Agent(
    model=_build_model(),
    output_type=ChartSpec,
    instructions=_INSTRUCTIONS,
)


async def get_chart_spec(columns: list[str], rows: list[dict]) -> ChartSpec:
    """Return a ChartSpec for the given query result. Never raises — returns no-chart on error."""
    try:
        sample = rows[:5]
        prompt = (
            f"Columns: {columns}\n"
            f"Sample rows ({min(len(rows), 5)} of {len(rows)}):\n"
            f"{json.dumps(sample, default=str)}"
        )
        result = await _agent.run(prompt)
        return result.output
    except Exception:
        return ChartSpec()
