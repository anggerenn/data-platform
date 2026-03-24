# Project Progress

## Session 10 — E2E Local Test + DPM Bug Fix (2026-03-24)

### E2E smoke test — full stack verified
- Rebuilt vanna container from latest code (was 17 days stale, pre-fix)
- Ran all 39 unit tests (test_app_utils, test_housekeeper, test_routes) inside container: **39/39 pass**
  - Note: `test_vec.py` skipped — BM25 was reverted to ChromaDB; `vec.py` no longer exists
- Ran full smoke test (`vanna/smoke_test.py`): **7/7 pass**
  - Chat: explore × 3, semantic × 2, clarify × 1
  - Dashboard: DPM 5-turn clarification → PRD → 4 charts → YAML written → URL returned

### Bug found and fixed: DPM returns `status=complete` with `prd=null`
- **Root cause:** `DPMResponse.prd` is `Optional[PRD] = None`, so pydantic accepts `null` even when `status=complete`. LLM occasionally omits the PRD object but marks itself done.
- **Symptom:** `/dashboard/build` returned HTTP 400 "No completed PRD in session" — the session's `prd` key was `None`
- **Fix:** Added `model_validator(mode='after')` to `DPMResponse` in `vanna/agents/planner.py` that raises `ValueError` when `status=complete` and `prd is None`. pydantic-ai catches the validation failure and retries the LLM call with the error as feedback — guarantees a populated PRD before the build proceeds.
- Committed: `fix(planner): enforce PRD presence when DPM status is complete`

---

## Session 9 — P2 Fixes (2026-03-24)

### Fix: `meta.grain` declared on all dbt models
- `dbt/models/marts/schema.yml`: added `grain: [order_date, category, city]` and `relationships` (→ stg_orders) to `daily_sales` meta
- `dbt/models/staging/schema.yml`: added `grain: [order_id]` to `stg_orders` meta
- `dbt/validate_schema.py`: canonical models now fail validation if `meta.grain` is missing, with a clear error message
- `vanna/agents/builder.py`:
  - `_scan_models` now extracts `grain` from each model's meta
  - `_CUSTOMER_GRAIN` set and `_needs_customer_grain()` removed
  - `find_best_model` rewritten: takes explicit `dimensions` + `metrics` params; checks grain-superset coverage before falling back to keyword scoring — a PRD with `dimensions: ['customer_id']` correctly routes to `stg_orders` because `daily_sales.grain` doesn't contain `customer_id`
  - `run_data_modeler` passes `prd.dimensions` and `prd.metrics` separately

### Fix: Flask route tests (`tests/test_routes.py`)
- 17 tests covering `/chat/stream`, `/dashboard/build`, `/export`, `/feedback`
- Test isolation: only stubs `dotenv` (not installed locally) and `agents.lightdash` (Python 3.10+ union syntax incompatible with local 3.9) — real agent modules load naturally so `test_housekeeper.py` is unaffected
- 15 pass locally; 2 pandas CSV tests skip (will pass in Docker where pandas is installed)

### Fix: Housekeeper API call batching (`vanna/agents/housekeeper.py`)
- Added `_chart_meta_cache: dict[str, set]` — module-level cache, survives across `check()` calls in the same process; cache hits avoid repeat HTTP calls for charts appearing in multiple dashboards
- Added `_fetch_chart_keywords(chart_uuid, internal, headers)` — cache-aware single-chart fetcher
- Restructured `_fetch_api_fingerprints()` into 4 phases:
  1. Fetch all dashboard tile lists sequentially (1 call per dashboard — unavoidable)
  2. Collect unique chart UUIDs across all dashboards
  3. Fetch all uncached chart UUIDs in parallel via `ThreadPoolExecutor(max_workers=8)`
  4. Build fingerprints from cache — zero additional HTTP calls
- Reduces worst-case calls from O(dashboards × charts) sequential to O(dashboards) + O(unique_charts) parallel

---

## Session 8 — P0 Bug Fixes (2026-03-24)

### Fix: `asyncio.run()` removed from housekeeper (`housekeeper.py`)
- `_llm_disambiguate` changed from `async def` + `await _agent.run()` to plain `def` + `_agent.run_sync()`
- `asyncio.run()` call in `check()` removed — no event loop created, no deadlock risk
- Unused `import asyncio` removed

### Fix: Docker socket failure surfaced (`lightdash.py`, `app.py`)
- `update_readme_tile` return type changed from `bool` to `tuple[bool, Optional[str]]`
- Inner `except Exception: pass` on Docker deploy → `except docker.errors.DockerException as e` — returns `(True, "YAML updated but deploy failed: ...")` so YAML write success is preserved but deploy failure is visible
- `app.py` caller updated to unpack tuple and store `readme_deploy_error` in API response when set

### Fix: hardcoded `localhost` defaults removed
- `vn.py`: `ANALYTICS_DB_HOST` now requires explicit env var (no default) — VPS host is `analytics-db`, not `localhost`
- `app.py`: `LIGHTDASH_PUBLIC_URL` now requires explicit env var
- `housekeeper.py`: `LIGHTDASH_PUBLIC_URL` now requires explicit env var
- `LIGHTDASH_INTERNAL_URL` default (`http://lightdash:8080`) left intact — correct for Docker network

### Fix: missing env vars in `.env.example`
- Added `GEMINI_API_KEY`, `LIGHTDASH_INTERNAL_URL`, `HOST_DBT_PATH`, `DOCKER_NETWORK_NAME` with comments explaining local vs VPS values
- All four were referenced in code but absent from the example — a VPS deployer would have no hint to set them

### Fix: `needs_new_model` stub (`app.py`)
- Was: `return jsonify({"needs_new_model": True, "error": "No existing model covers these metrics."})` — dead end for the user
- Now: calls `vn.generate_sql()` using the PRD objective + metrics as the question, returns `suggested_sql` with a clear message instructing the user to add it as a new dbt model and retry
- Gracefully falls back to `suggested_sql: null` if SQL generation fails

### Verified done: `merge_guides()` already correct (`instructor.py`)
- `_merge()` already combines both existing PRD + new PRD in the prompt before calling LLM
- `update_readme_tile()` reads existing YAML and overwrites the markdown tile correctly
- Gap note from Session 7 was stale — fix was applied in Session 6; tasklist updated

### Fix: `answer_semantic` returns question unchanged (`router.py`)
- Tool was `return question` — echoed the input, giving the agent no useful context
- Fixed: calls `vn.get_related_documentation(question)` (ChromaDB retrieval, no LLM), returns top-5 schema docs as context
- Agent LLM now has grounded schema context to write a real answer

### Fix: `sql_cache` missing on non-streaming `/chat` path (`app.py`)
- `AgentDeps(vanna=vn)` → `AgentDeps(vanna=vn, sql_cache=_sql_cache)` on line 210
- Streaming path (`/chat/stream`) already had this; non-streaming path was silently bypassing the cache on every call

---

## Session 7 — Gap Analysis (2026-03-24)

### Architecture review + Wren AI comparison
Full codebase scan to identify broken wiring, missing implementations, silent failures, and deploy blockers. Researched Wren AI architecture (MDL, SQL correction loop, instructions registry). No code changed — all findings documented in tasklist.md.

### Design decision — Instruction registry
Root cause of wrong SQL: LLM picks between `revenue`, `amount`, `line_total` with no explicit rule. Solution: static YAML instruction registry loaded into Vanna's system prompt at startup.
- `vanna/instructions/global.yml` — layer priority rule: marts → staging → raw
- `vanna/instructions/layers/marts.yml` — term → SQL mappings for canonical metrics layer
- `vanna/instructions/layers/raw.yml` — term → SQL mappings per raw source (grows as more sources land)
- Team-based dynamic overrides (load from Lightdash user API) — deferred until Lightdash auth is wired

### P0 gaps found (broken right now)
- `answer_semantic` tool in `router.py` echoes the question unchanged — no LLM answer generated
- `merge_guides()` in `instructor.py` generates a new guide from scratch on every call — existing README narrative is lost
- `sql_cache` not passed to `AgentDeps` on non-streaming `/chat` path in `app.py` — caching is inconsistent
- `needs_new_model: True` case in `app.py` is a stub — any PRD requiring a new dbt model is completely blocked

### P1 gaps found (silent failures on VPS)
- `localhost` hardcoded as default in `vn.py`, `app.py`, `housekeeper.py` — works locally, breaks on VPS
- Docker socket failure in `lightdash.py` caught by bare `except Exception` — user sees nothing
- `GEMINI_API_KEY`, `HOST_DBT_PATH`, `DOCKER_NETWORK_NAME` missing from `.env.example`
- `asyncio.run()` in `housekeeper.py` — deadlock risk if called from async context

### P2 gaps found (fragile)
- No `meta.grain` declared on any dbt model — builder.py falls back to `_needs_customer_grain()` keyword heuristic
- Designer hardcodes `'deepseek-chat'` instead of reading `VANNA_MODEL` env var
- Zero Flask route tests or agent pipeline integration tests
- `_scan_models()` re-parses all schema YAMLs on every dashboard build
- Housekeeper makes cascading sequential Lightdash API calls (no batching or caching)

---

## Session 6 — Completed Work (2026-03-10)

### Bug fixes
- **CSV export only 20 rows** — two root causes fixed:
  - `app.js`: switched from form POST to `fetch+blob` (form encoding corrupted SQL with %, & etc.)
  - `app.py`: strip trailing `LIMIT N` from SQL in `/export` before re-executing (DeepSeek may add one)
- **Data Modeler misses staging table for customer grain** — `builder.py`:
  - Added `_CUSTOMER_GRAIN` keyword set and `_needs_customer_grain()` function
  - If PRD metrics mention customer_id, leaderboard, per customer etc., restrict model candidates to models with `customer_id` column — prevents `daily_sales` (canonical, no customer_id) from winning over `stg_orders`

### Enhancements
- **Instructor README regeneration on `partial_uncovered`**:
  - `instructor.merge_guides()`: merges existing + new PRD into a combined guide
  - `lightdash.update_readme_tile()`: updates the README.md tab markdown tile in the existing dashboard YAML and triggers redeploy
  - `app.py`: wires both on `partial_uncovered` before proceeding with new build
  - README becomes a living doc reflecting all use cases for that dashboard
- **Housekeeper structural comparison** (field-level + model-level):
  - `_chart_field_keywords()`: loads metric/dimension field IDs from chart YAMLs per dashboard, merges into Jaccard fingerprint
  - `check()` now accepts `model_name`; same dbt model → score floored at `_PARTIAL_THRESHOLD`
  - `app.py`: reordered to run data modeler before housekeeper so model_name is available
  - PRD JSON fingerprints now store `model` field
- **DPM metrics vs dimensions distinction**:
  - `PRD.dimensions: list[str] = []` — new field for grouping fields (city, category, date)
  - DPM instructions updated: separate question 4 into metrics (aggregations) vs dimensions (grouping)
  - `builder.py`: `run_data_modeler` uses `metrics + dimensions` for coverage scoring
  - `lightdash.py`: `_plan_charts` receives dimensions and merges keywords into chart selection
  - `instructor.py`: guide prompt includes dimensions for richer tips
  - `app.js`: PRD card shows Dimensions section when present

---



## Current State (2026-03-07, session 4)

### Stack
- **Ingestion:** dlt → Prefect → ClickHouse (`default.raw___orders`)
- **Transformation:** dbt → `transformed_staging.stg_orders` (view) + `transformed_marts.daily_sales` (table)
- **OLAP:** ClickHouse with `bi_readonly` user for Lightdash + Vanna
- **BI:** Lightdash (pinned `0.2473.1`) with automated first-boot deploy
- **AI Service:** Vanna (pydantic.ai orchestrator) on port 8084 with floating chat widget

---

## Next Steps (priority order)

1. **Test suite** — pytest unit tests, dbt tests, smoke tests, GitHub Actions CI
2. **Deploy to VPS via Coolify** — push changes, redeploy all services

---

## Session 3 — Completed Work (2026-03-06)

### Semantic layer + auto-training
- Enriched `dbt/models/marts/schema.yml` with full dimension/metric metadata (labels, descriptions, groups, round)
- Added 3 derived metrics: `average_order_value`, `revenue_per_customer`, `units_per_order` (type: number, sql with `${ref}` expressions)
- `vanna/train_from_schema.py` — hash-based incremental trainer:
  - Generates Q&A pairs (104 pairs from 8 metrics × 3 dimensions)
  - Generates documentation strings (metric/dimension business context)
  - Reads PRD JSON files → documentation strings (semantic fingerprints for housekeeper)
  - Hash state stored at `/data/vanna-retrain-state.json` — skips unchanged files
  - Returns stats dict: `{qa_added, qa_skipped, docs_added, docs_skipped}`

### Schema validation
- `dbt/validate_schema.py` — validates canonical models on every PR/push:
  - Required fields: label, description, groups, round
  - Approved group names (enforced list)
  - Derived metric sql references resolve to real metric keys
- `.github/workflows/validate-schema.yml` — triggers on `dbt/models/**` changes
- `prefect/flows/vanna_retrain.py` — `validate_schema` task runs before retrain (runtime guard)

### Prefect flows refactored
- `prefect/flows/vanna_retrain.py` — new dedicated file with `validate_schema` + `retrain_vanna_schema` tasks
- `prefect/flows/main_pipeline.py` — cleaned up: imports from dedicated files, pipeline: `dlt → dbt → validate_schema → retrain_vanna_schema`

### Housekeeper improvements
- `check(prd, vn=None)` — now accepts vn for semantic disambiguation
- ChromaDB semantic search replaces LLM in ambiguous zone (0.5–0.7 Jaccard): `_chromadb_disambiguate()` queries `vn.get_related_documentation()` against stored PRD docs
- LLM retained as fallback only
- PRD docs in ChromaDB enable semantic duplicate detection (catches "regional revenue" = "city performance")

### GitHub Actions
- `.github/workflows/validate-schema.yml` — validate semantic layer on PR
- `.github/workflows/deploy-lightdash.yml` — `lightdash upload` on push to main when `dbt/lightdash/**` changes

### Lightdash deploy split
- GitHub Actions handles git→Lightdash (upload on merge) — immediate
- Prefect sync handles Lightdash→git (download UI changes every 15 min) — unchanged
- Entrypoint script keeps upload as fallback for fresh container starts

### Latency improvements
- **SSE streaming** — `/chat/stream` endpoint (thread+queue async→sync bridge)
  - Status event sent immediately ("Thinking…")
  - Text tokens stream into chat bubble word by word as LLM generates
  - Chart + table rendered on final result event
  - Frontend updated to use SSE (`fetch` with `ReadableStream`)
- **SQL cache** — `_sql_cache` in `app.py`, checked in `explore_data` tool before `vn.generate_sql()` call
  - Saves ~1-2s on repeated questions (skips DeepSeek SQL generation)
  - In-memory, resets on restart, shared across both endpoints

### RAM
- Lightdash: `NODE_OPTIONS=--max-old-space-size=640` — nudges V8 GC without hard kill
- No `mem_limit` set (Lightdash was at 830MB in docker stats — hard cap would OOM kill it)
- Vanna at 335MB — almost entirely ChromaDB ONNX model → target of zvec migration

---

## Session 4 — Completed Work (2026-03-07)

### BM25 migration complete
- `vanna/vec.py` — `BM25Store` with persistent JSON + BM25Okapi retrieval
- `vanna/vn.py` — `VannaLite` replacing full vanna+ChromaDB stack
- `docker/Dockerfile.vanna` — `rank-bm25` + `pandas` replace vanna package (no ONNX)
- Bug fixed in `vec.py:get_similar_question_sql` — dict sort tiebreaker using index
- RAM: **120MB** (down from 335MB — 215MB saved, ONNX model eliminated)
- Smoke test passed: "total revenue by category" → correct SQL + bar chart

### Test suite complete
- `tests/conftest.py` — sys.path + vn module stub (prevents ClickHouse at import)
- `tests/test_vec.py` — 8 tests: BM25Store add/retrieve, persistence, tiebreaker regression
- `tests/test_app_utils.py` — 7 tests: `_trim_to_user_turn`, `_strip_explore_rows` edge cases
- `tests/test_housekeeper.py` — 15 tests: `_normalise_field`, `_keywords`, `_jaccard`, `_slugify`, `check()` with mocked fingerprints
- **30/30 passing** inside vanna Docker container
- `dbt/tests/assert_daily_sales_has_rows.sql` — singular test (row count > 0)
- `dbt/models/marts/schema.yml` — added `accepted_values` for category
- `dbt/models/staging/schema.yml` — added `unique` + `not_null` for `order_id`
- `.github/workflows/pytest.yml` — runs on push/PR touching `vanna/**` or `tests/**`
- Also fixed: BM25 `score > 0` filter drops all results in small corpora (negative IDF) — removed filter

---

## Session 5 — Completed Work (2026-03-08)

### PostgreSQL migration complete (ClickHouse removed)
- Replaced `clickhouse` service with `analytics-db` (postgres:15, separate from Prefect's postgres)
- `docker/analytics-db-init/01-readonly-user.sh` — creates `bi_readonly` user with `pg_read_all_data` role
- `vanna/vn.py` — `clickhouse_connect` → `psycopg2`, lazy reconnect, PostgreSQL system prompt
- `docker/Dockerfile.vanna` — `clickhouse-connect` → `psycopg2-binary`
- `docker/Dockerfile.lightdash-deploy` — `dbt-clickhouse` → `dbt-postgres`
- `requirements.prefect.txt` — `dlt[clickhouse]` + `dbt-clickhouse` → `dlt[postgres]` + `dbt-postgres`
- `prefect/flows/dlt_ingestion.py` — `dlt.destinations.clickhouse(...)` → `dlt.destinations.postgres(credentials=url)`
- `dbt/profiles.yml` — clickhouse adapter → postgres adapter
- `dbt/models/staging/sources.yml` — `schema: default`, `raw___orders` → `schema: raw`, `orders` (dlt PostgreSQL naming)
- `dbt/models/staging/stg_orders.sql` — `toDate(order_date)` → `order_date::date`
- `vanna/train.py` — all SQL translated: DATE_TRUNC, LAG, CURRENT_DATE, INTERVAL '1 month', NULLIF
- `.env.example` — CLICKHOUSE_* → ANALYTICS_DB_*, added ParadeDB upgrade note
- `docker-compose.yml` — removed clickhouse, added analytics-db, updated all env var references
- Full pipeline verified: dlt → dbt PASS=2, schema validation passed, Lightdash sync complete
- Note: upgrade to ParadeDB if GROUP BY query latency >500ms at >1M rows — drop-in compatible

## Pending / Known Issues

- VPS deployment not yet done — all changes local only

---

## Completed Work (feature summary)

### Vanna chat widget
- Full-page Lightdash iframe + floating chat bubble (bottom-right, `#7262ff`)
- Popup and right side-panel modes (toggle via expand button)
- 3-intent routing via pydantic.ai: `explore_data`, `answer_semantic`, `clarify`
- Markdown rendering: headers, bold, italic, inline code, bullet/ordered lists, tables
- Plotly charts: bar, line, grouped_bar, heatmap, kpi — driven by server-side Data Visualizer Agent
- KPI scorecard for single-value results (1 row × 1 numeric col)
- SSE streaming: text tokens stream word by word, full result on completion
- SQL cache: repeated questions skip LLM SQL generation (~1-2s saved)
- Collapsible SQL block, data table with formatted numbers, row count
- CSV export button
- 👍 👎 feedback buttons (below data, after user sees results)
- Stop button (AbortController) to cancel in-flight requests
- Session limit: warning at 19, disabled at 20 exchanges

### Security
- Server-side session storage: `sessions` dict in `app.py`, keyed by UUID
- Client holds only `session_id`
- `bi_readonly` ClickHouse user: SELECT-only

### Agents
- Router (pydantic-ai): explore / semantic / clarify
- DPM/Planner: multi-turn PRD creation from exploration history
- Data Modeler: finds existing dbt model for PRD metrics
- Lightdash: generates chart + dashboard YAMLs, triggers upload
- Housekeeper: Jaccard + ChromaDB semantic disambiguation; advisory-only; full/partial_covered/partial_uncovered/none
- Storyteller: deterministic Minto Pyramid layout (KPI top, bars mid, trend full-width)
- Instructor: generates DashboardGuide (overview, use cases, tips) embedded as README.md tab
- Designer: server-side chart spec (type, x, y, group) for chat widget

### Semantic layer
- `dbt/models/marts/schema.yml` — full metric/dimension metadata with groups, descriptions
- `vanna/train_from_schema.py` — hash-based incremental trainer (Q&A pairs + docs + PRD docs)
- `dbt/validate_schema.py` — convention enforcer (CI + runtime)
- PRD persistence: `dbt/lightdash/prd/<slug>.json` after every successful build

### ClickHouse
- `order_date` cast via `toDate()` at dbt staging layer
- `lagInFrame()` instead of standard `LAG()` (ClickHouse 24.3)
- All `GROUP BY` use column expressions not aliases

### History stability
- `_trim_to_user_turn()`: fast-forwards to first `UserPromptPart` after sliding window
- `_strip_explore_rows()`: removes large data payloads from history
