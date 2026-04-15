# Data Platform Agentic BI

Self-hosted data platform with an agentic BI layer — full pipeline from ingestion to transformation to BI, with AI agents that let stakeholders ask questions in plain English and automatically generate persistent Lightdash dashboards.

## Stack

| Layer | Tool |
|-------|------|
| Ingestion | dlt (via Prefect) |
| Orchestration | Prefect |
| Transformation | dbt core |
| Database | PostgreSQL (analytics-db) |
| BI | Lightdash |
| AI / SQL | Vanna (ChromaDB vector store + DeepSeek via OpenAI-compatible API) + pydantic-ai agents |
| Deployment | Coolify on Contabo VPS |

## Prerequisites

**Local development**

- [Docker Desktop 4.x+](https://docs.docker.com/get-docker/) (includes Compose v2) — or Docker Engine 24+ with the Compose plugin
- Git
- A [DeepSeek API key](https://platform.deepseek.com/) — used for SQL generation and all agents
- ~4 GB free RAM, ~3 GB free disk (Docker images)

> **Apple Silicon (M1/M2/M3):** the `lightdash` service is pinned to `linux/amd64` and runs under Rosetta emulation. It works, but the first image pull is slower and startup takes 30–60s longer than on x86.

> **Docker socket:** `vanna` and `prefect-worker` mount `/var/run/docker.sock` to spawn the `lightdash-deploy` container at runtime. On Linux you may need to add your user to the `docker` group. On Docker Desktop this works out of the box.

**VPS / Coolify deployment (additional)**

- A VPS with at least 4 GB RAM free (8 GB total recommended)
- [Coolify](https://coolify.io/) installed on the VPS
- A domain name with DNS A-records pointing to the VPS (one per public-facing service)

## How it works

1. **Ask a question** in the chat widget (embedded in Lightdash via nginx reverse proxy)
2. The router agent classifies intent: `explore` (SQL + chart), `semantic` (schema answer), or `clarify`
3. For `explore`: Vanna generates SQL (ChromaDB retrieval + DeepSeek) with retry/EXPLAIN validation, executes against PostgreSQL, returns results + agent-selected chart type
4. Click **Save as Dashboard** — triggers a 6-agent pipeline:
   - **DPM Agent** (`planner.py`) — clarifies objective, audience, metrics, and dimensions via multi-turn chat; produces a structured PRD
   - **Housekeeper Agent** (`housekeeper.py`) — checks if an equivalent dashboard already exists (Jaccard similarity on metric fingerprints); advisory verdict: `full / partial_covered / partial_uncovered / none`
   - **Data Modeler Agent** (`builder.py`) — grain-aware model selection; reuses existing dbt model or scaffolds a new one via Vanna SQL generation + `dbt run`
   - **Data Visualizer Agent** (`designer.py`) — selects chart types and generates Lightdash `.yml` chart + dashboard files
   - **Instructor Agent** (`instructor.py`) — generates a README guide (overview, use-case questions, tips) embedded as a markdown tile in every dashboard
   - **Lightdash deployer** (`lightdash.py`) — runs `lightdash upload` inside a container, returns the dashboard URL
5. Dashboard URL is returned to the chat widget

## Pipeline flow

```
dlt (ingest) → PostgreSQL → dbt (transform) → Lightdash (visualize)
                                                     ↑
                              agents write .yml files into dbt/lightdash/
```

## Repo structure

```
data-platform/
├── dbt/
│   ├── models/           # staging + marts dbt models + schema.yml (metrics, grain, relationships)
│   └── lightdash/        # charts, dashboards, PRDs (agent-generated)
├── docker/               # Dockerfiles + entrypoint scripts
├── nginx/                # Lightdash reverse proxy config (sub_filter injects widget.js)
├── prefect/flows/        # Orchestration flows (ingestion, dbt transform, retrain)
├── tests/                # pytest unit + smoke tests
├── vanna/
│   ├── agents/           # planner, builder, designer, lightdash, housekeeper, instructor
│   ├── static/           # Chat widget (HTML/JS/CSS)
│   ├── app.py            # Flask API (SSE streaming, session management, SQL cache)
│   ├── vn.py             # VannaAI subclass: overrides system prompt, swaps in DeepSeek, adds EXPLAIN-based SQL validation with retry
│   └── train.py          # Seed training data (run once after stack is up)
├── docker-compose.yml
├── docker-compose.override.yml  # local port bindings (auto-merged, ignored by Coolify)
└── .env.example
```

## Local development

```bash
# 1. Set up environment
cp .env.example .env
# Fill in: ANALYTICS_DB_PASSWORD, ANALYTICS_DB_READONLY_PASSWORD,
#          LIGHTDASH_SECRET, DEEPSEEK_API_KEY
# LIGHTDASH_PUBLIC_URL defaults to http://localhost:8080 — fine for local dev

# 2. Start the stack
# pipeline-init runs automatically and loads synthetic sample data:
# 100 orders + 50 customers across 4 categories (Electronics, Clothing, Food, Books)
# and 4 cities (New York, Los Angeles, Chicago, Houston) over the past 30 days.
# No external data source needed.
docker-compose up -d

# 3. Seed training data (first boot only)
docker-compose exec vanna python train.py

# 4. Deploy dbt models to Lightdash (first boot only)
docker-compose run lightdash-deploy
```

> **First boot — required manual step:**
> `lightdash-deploy` creates a Lightdash admin account and prints a Personal Access Token (PAT) to its logs:
> ```
> docker-compose logs lightdash-deploy | grep ldpat_
> ```
> Copy the `ldpat_...` token, set it in `.env`:
> ```
> LIGHTDASH_API_KEY=ldpat_xxxxxxxxxxxx
> ```
> Then restart vanna so it picks up the key:
> ```
> docker-compose restart vanna
> ```
> Without this step the dashboard builder will fail silently — vanna cannot call the Lightdash API.

**Service URLs (local):**

| Service | URL |
|---------|-----|
| Lightdash + Chat widget | http://localhost:8080 |
| Vanna API | http://localhost:8084 |
| Prefect UI | http://localhost:4200 |

## Prefect deployments

The `prefect-worker` container starts automatically and connects to `prefect-server`. On first boot, `pipeline-init` runs the ingestion + transformation pipeline directly — no deployment registration needed for that.

To trigger pipeline runs from the Prefect UI or enable the `lightdash-sync` scheduled flow (every 15 min), register the deployments:

```bash
# Run inside the worker container after the stack is up
docker-compose exec prefect-worker prefect deploy --all
```

> **If you forked this repo:** `prefect.yaml` has a `git_clone` step pointing to `https://github.com/anggerenn/data-platform.git`. Update it to your own repo URL before registering deployments — otherwise the worker will clone from the original repo when running flows.

## Environment variables

| Variable | Description |
|----------|-------------|
| `POSTGRES_PASSWORD` | Password for the Prefect and Lightdash internal PostgreSQL databases |
| `MINIO_ROOT_PASSWORD` | MinIO root password (used by Lightdash for file storage) |
| `ANALYTICS_DB_USER` | Analytics DB username (default: `analytics`) |
| `ANALYTICS_DB_PASSWORD` | Analytics DB password |
| `ANALYTICS_DB_READONLY_PASSWORD` | Read-only user password for Lightdash |
| `LIGHTDASH_SECRET` | Lightdash JWT secret |
| `LIGHTDASH_EMAIL` | Lightdash admin email |
| `LIGHTDASH_PASSWORD` | Lightdash admin password |
| `LIGHTDASH_API_KEY` | Lightdash PAT (set after first boot) |
| `LIGHTDASH_PUBLIC_URL` | Browser-facing Lightdash URL — used by the chat widget to build dashboard links. Local: `http://localhost:8080`. VPS: must match the public domain assigned to the **nginx** service in Coolify (e.g. `https://dashboard.yourdomain.com`) |
| `SERVICE_URL_PREFECT_SERVER` | Public URL of the Prefect server — used by the Prefect UI to reach the API. Must match the domain assigned to the **prefect-server** service in Coolify (e.g. `https://prefect.yourdomain.com`) |
| `DEEPSEEK_API_KEY` | DeepSeek API key (SQL generation + all agents) |
| `VANNA_MODEL` | Vanna LLM model (default: `deepseek-chat`) |
| `HOST_DBT_PATH` | Absolute host path to the `dbt/` directory — used by the Lightdash deployer when spawning a container to run `lightdash upload`. Leave unset locally (auto-detected). On Coolify, set to the host path bound to `/dbt` (e.g. `/data/pipelines/dbt`) |

## Deployment to Coolify (VPS)

1. Push repo to GitHub
2. In Coolify: new project → Docker Compose → point to `docker-compose.yml`
3. In Coolify, assign public domains to these three services:
   - **nginx** — your main entry point; this is where the Lightdash UI + chat widget lives (e.g. `dashboard.yourdomain.com`)
   - **prefect-server** — Prefect UI (e.g. `prefect.yourdomain.com`)
   - **vanna** — Vanna API, only needed if you want direct API access (e.g. `vanna.yourdomain.com`)
4. Set environment variables — the following must match the domains assigned above:
   - `LIGHTDASH_PUBLIC_URL` → same domain as the **nginx** service (e.g. `https://dashboard.yourdomain.com`)
   - `SERVICE_URL_PREFECT_SERVER` → same domain as the **prefect-server** service (e.g. `https://prefect.yourdomain.com`)
5. Deploy — on first boot:
   - Find the Lightdash PAT in `lightdash-deploy` logs: `docker logs $(docker ps -aqf name=lightdash-deploy) | grep ldpat_`
   - Set `LIGHTDASH_API_KEY` to the `ldpat_...` token in Coolify env vars
   - Restart the vanna service
6. Seed training data: exec into vanna container → `python train.py`

> **Note:** Do not add a custom Docker network in `docker-compose.yml`. Coolify's project network is sufficient — extra networks cause Traefik routing issues (see Troubleshooting).

## Troubleshooting

**Lightdash never becomes healthy / stack hangs on startup**

Lightdash takes 60–90s to initialise (longer on Apple Silicon under Rosetta). Other services that depend on it (`nginx`, `lightdash-deploy`) wait for its healthcheck to pass. Just wait — if it hasn't started after 3 minutes, check the logs:
```bash
docker-compose logs lightdash
```

**`pipeline-init` looks like it failed**

`pipeline-init` always exits 0 so it doesn't block the rest of the stack. Check whether it actually succeeded:
```bash
docker-compose logs pipeline-init
```

**Dashboard builder returns an error / "cannot call Lightdash API"**

`vanna` is missing a valid `LIGHTDASH_API_KEY`. Re-run the first-boot step:
```bash
docker-compose logs lightdash-deploy | grep ldpat_
# copy the token → set LIGHTDASH_API_KEY in .env → restart vanna
docker-compose restart vanna
```
If redeploying from scratch, clear any stale key from `.env` before the deploy — `lightdash-deploy` will generate a new one.

**Traefik 504 on Coolify (VPS)**

Caused by adding a custom Docker network to `docker-compose.yml`. Coolify's project network is sufficient — extra networks cause Traefik to non-deterministically route through the wrong one. Remove any `networks:` blocks you may have added and redeploy.

**Dashboard build times out on VPS (Traefik cuts the connection)**

Dashboard builds take 2–3 minutes. Traefik's default response timeout may be shorter. Create `/data/coolify/proxy/dynamic/vanna-timeouts.yaml` on the VPS:
```yaml
http:
  serversTransports:
    default:
      forwardingTimeouts:
        responseHeaderTimeout: 0s
        dialTimeout: 30s
        idleConnTimeout: 300s
```
Traefik picks up dynamic config automatically — no restart needed.

**nginx 502/504 after a full Coolify redeploy (VPS)**

nginx holds stale upstream connections after services are recreated with new container IDs. Restart nginx to force DNS re-resolution:
```bash
docker restart $(docker ps -qf name=nginx)
```

---

## Chat widget injection

The chat widget is not bundled into Lightdash — it is injected by the nginx reverse proxy that sits in front of it. This is why the entry point in Coolify is the **nginx** service, not Lightdash directly.

How it works (`nginx/lightdash.conf`):

1. nginx proxies all traffic to Lightdash but strips `Accept-Encoding` so responses are not gzip-compressed — a requirement for `sub_filter` to rewrite the HTML body.
2. `sub_filter` injects `<script src="/vanna-widget.js"></script>` before `</body>` on every HTML page Lightdash serves.
3. `/vanna-widget.js` is served by the vanna container (`/static/widget.js`) — it bootstraps the side panel and connects back to the vanna API at `/vanna/`.
4. `/vanna/*` requests are reverse-proxied to the vanna container with the `/vanna/` prefix stripped.

**If the chat widget is not appearing:**

- Confirm you are accessing Lightdash through nginx (port 8080 locally, or your nginx domain on VPS) — not directly on Lightdash's internal port.
- Check that both `nginx` and `vanna` containers are running: `docker-compose ps`
- Check nginx logs for upstream errors: `docker-compose logs nginx`

## Known issues

**Chat widget renders as a tiny box on the nginx-proxied Lightdash domain**

When accessing Lightdash through nginx (e.g. `https://dashboard.yourdomain.com`), the `#vanna-panel` collapses to a small box instead of filling the viewport. The widget works correctly when accessing the vanna UI directly (`https://vanna.yourdomain.com`).

Root cause is unresolved: Lightdash's global CSS overrides `position: fixed` on the panel element. Multiple fixes have been attempted (`!important`, absolute iframe positioning, inline styles) but the winning CSS rule in the nginx-proxied context has not been identified. Needs browser DevTools inspection on the proxied page to find what's overriding the panel height.

Workaround: use the vanna URL directly for chat and dashboard building.

---

## Retraining

```bash
# Clear and reseed
docker-compose exec vanna python train.py

# Incrementally retrain from schema.yml changes only
curl -X POST http://localhost:8084/retrain/schema

# Or trigger the full pipeline (ingest + transform + retrain) via Prefect
docker-compose exec prefect-worker prefect deployment run analytics-pipeline/analytics-pipeline
```