"""Storyteller — Minto Pyramid layout for Lightdash dashboards.

Weight is assigned by chart structure (fully deterministic):
  1 — KPI scorecard (big_number)
  2 — Simple dimension breakdown (bar with 1 categorical dim)
  3 — Time trend (line chart)
  4 — Cross-dimensional / deep-dive (grouped_bar, heatmap, bar with 2+ dims)

Charts sharing the same weight appear on the same row.
Row width (36 cols) is split equally across all charts in a row.
Users can reorder tiles in Lightdash after creation.
"""

# ── Grid constants ─────────────────────────────────────────────────────────────
GRID_COLS = 36
_ROW_H = {1: 3, 2: 5, 3: 5, 4: 6}
_DEFAULT_H = 5


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
        return 2 if len(dims) <= 1 else 4

    return 2  # default


# ── Function: assign grid positions from weights ───────────────────────────────

def _layout(weighted_specs: list) -> list:
    sorted_specs = sorted(weighted_specs, key=lambda c: c['weight'])

    rows = []
    current_weight = None
    current_row = []
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


# ── Public entry point ─────────────────────────────────────────────────────────

def arrange_tiles(prd, chart_specs: list) -> list:
    """Classify charts by structure, layout by Minto Pyramid weights."""
    by_weight = {}
    for spec in chart_specs:
        w = _weight(spec)
        by_weight.setdefault(w, []).append(spec)

    weighted = [
        {**spec, 'weight': w}
        for w, specs in by_weight.items()
        for spec in specs
    ]

    return _layout(weighted)
