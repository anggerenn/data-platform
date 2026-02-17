# Data Platform Monorepo

## Stack
- **dlt**: Data ingestion
- **dbt**: Transformations
- **DuckDB**: Analytics database
- **Evidence**: BI & dashboards (static site, rebuilt on each pipeline run)
- **Prefect**: Orchestration

## Structure
- `/dbt` - dbt models and profiles
- `/evidence` - Evidence dashboards and sources
- `/prefect` - Orchestration flows
- `/docker` - Docker configuration

## Pipeline Flow
```
dlt (ingest) → dbt (transform) → Evidence (build) → nginx (serve)
```

## Local Development
1. Copy `.env.example` to `.env` and fill in values
2. Run `docker compose -f docker/docker-compose.yml up -d`
3. Access Prefect UI at `http://localhost:4200`

> Note: Evidence dashboard is only available after the pipeline runs at least once.

## Environment Variables
| Variable | Description |
|---|---|
| `POSTGRES_PASSWORD` | Postgres password for Prefect backend |
| `ANALYTICS_DB_PATH` | Path to DuckDB file |
| `ANALYTICS_PIPELINES_DIR` | Path to dlt pipeline state directory |

## Deployment to Coolify (VPS)
1. Push repo to GitHub
2. In Coolify, create new project
3. Choose Docker Compose and point to `docker/docker-compose.yml`
4. Set environment variables from the table above
5. Set domains in Coolify UI:
   - `prefect-server` → `prefect.yourdomain.com`
   - `nginx` → `evidence.yourdomain.com`
6. Deploy!