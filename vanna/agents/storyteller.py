"""Storyteller — Minto Pyramid layout for Lightdash dashboards.

Weight is assigned by function (deterministic, based on chart structure):
  1 — KPI scorecard (big_number, no dimensions)
  2 — Simple dimension breakdown (bar with 1 categorical dim)
  3 — Time trend (line chart)
  4 — Cross-dimensional / deep-dive (grouped_bar, heatmap, bar with 2+ dims)

Charts sharing the same weight appear on the same row.
The LLM is used only for ordering within weight-2 bars (which dim goes left).
Row width (36 cols) is split equally across all charts in a row.
"""
import asyncio
import re

from pydantic import BaseModel
from pydantic_ai import Agent

from agents._model import make_model


# ── Grid constants ─────────────────────────────────────────────────────────────
GRID_COLS = 36
_ROW_H = {1: 3, 2: 5, 3: 5, 4: 6}
_DEFAULT_H = 5

_DATE_RE = re.compile(r'(date|time|day|month|week|year|period)', re.I)


# ── Function: classify chart weight from structure ─────────────────────────────

def _weight(spec: dict) -> int:
    t = spec.get('type', '')
    dims = spec.get('dimensions', [])

    if t == 'big_number':
        return 1

    if t == 'line':
        return 3

    if t in ('grouped_bar', 'heatmap', 'stacked_bar'):
        return 4

    # bar: weight by number of dimensions
    if t == 'bar':
        if len(dims) <= 1:
            return 2   # simple "Revenue by City" style
        return 4       # multi-dim bar → deep dive

    return 2  # default


# ── LLM: order weight-2 bars by PRD relevance ─────────────────────────────────

class _Ordering(BaseModel):
    ordered_names: list[str]  # weight-2 charts in preferred left→right order


_ordering_agent = Agent(
    model=make_model(),
    output_type=_Ordering,
    instructions="""Order the given bar charts left-to-right based on their relevance to the PRD objective.
The most directly relevant breakdown goes first (leftmost).
Return all names in order — do not omit any.""",
)


async def _order_bars_async(prd, bars: list[dict]) -> list[dict]:
    if len(bars) <= 1:
        return bars
    names = [b['name'] for b in bars]
    try:
        result = await _ordering_agent.run(
            f"PRD objective: {prd.objective}\nBar charts: {names}"
        )
        ordered_names = result.output.ordered_names
        name_to_spec = {b['name']: b for b in bars}
        ordered = [name_to_spec[n] for n in ordered_names if n in name_to_spec]
        # append any bars the LLM missed
        ordered += [b for b in bars if b not in ordered]
        return ordered
    except Exception:
        return bars


# ── Function: assign grid positions from weights ───────────────────────────────

def _layout(weighted_specs: list[dict]) -> list[dict]:
    sorted_specs = sorted(weighted_specs, key=lambda c: c['weight'])

    rows: list[list[dict]] = []
    current_weight = None
    current_row: list[dict] = []
    for spec in sorted_specs:
        w = spec['weight']
        if w != current_weight:
            if current_row:
                rows.append(current_row)
            current_row = [spec]
            current_weight = w
        else:
            current_row.append(spec)
    if current_row:
        rows.append(current_row)

    positioned = []
    y = 0
    for row in rows:
        n = len(row)
        row_weight = row[0]['weight']
        h = _ROW_H.get(row_weight, _DEFAULT_H)
        col_w = GRID_COLS // n
        remainder = GRID_COLS - col_w * n

        for i, spec in enumerate(row):
            w = col_w + (remainder if i == n - 1 else 0)
            positioned.append({**spec, 'x': i * col_w, 'y': y, 'w': w, 'h': h})
        y += h

    return positioned


# ── Public entry point (sync) ──────────────────────────────────────────────────

def arrange_tiles(prd, chart_specs: list[dict]) -> list[dict]:
    """Assign weights by structure, order bars by LLM, layout by function."""
    by_weight: dict[int, list[dict]] = {}
    for spec in chart_specs:
        w = _weight(spec)
        by_weight.setdefault(w, []).append(spec)

    # LLM orders weight-2 bars; everything else keeps its original order
    if 2 in by_weight and len(by_weight[2]) > 1:
        by_weight[2] = asyncio.run(_order_bars_async(prd, by_weight[2]))

    weighted = []
    for w, specs in by_weight.items():
        for spec in specs:
            weighted.append({**spec, 'weight': w})

    return _layout(weighted)
