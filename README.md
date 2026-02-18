# Data Platform Monorepo

## Stack
- **dlt**: Data ingestion
- **dbt**: Transformations
- **DuckDB**: Analytics database
- **Metabase**: BI & dashboards
- **Prefect**: Orchestration

## Structure
- `/dbt` - dbt models and profiles
- `/prefect` - Orchestration flows
- `/docker` - Docker configuration
- `/scripts` - Database init scripts

## Pipeline Flow
```
dlt (ingest) → dbt (transform) → Metabase (visualize)
```

## Local Development
1. Copy `.env.example` to `.env` and fill in values
2. Run `docker compose -f docker/docker-compose.yml up -d`
3. Access Prefect UI at `http://localhost:4200`
4. Access Metabase at `http://localhost:3000`

## Environment Variables
| Variable | Description |
|---|---|
| `POSTGRES_PASSWORD` | Postgres password for Prefect and Metabase |
| `ANALYTICS_DB_PATH` | Path to DuckDB file |
| `ANALYTICS_PIPELINES_DIR` | Path to dlt pipeline state directory |

## Deployment to Coolify (VPS)
1. Push repo to GitHub
2. In Coolify, create new project
3. Choose Docker Compose and point to `docker/docker-compose.yml`
4. Set environment variables from the table above
5. Set domains in Coolify UI:
   - `prefect-server` → `prefect.yourdomain.com`
   - `metabase` → `metabase.yourdomain.com`
6. Deploy!

## Connecting Metabase to DuckDB
1. Open Metabase UI → Admin → Databases → Add Database
2. Select **DuckDB** from the database type dropdown
3. Set path to `/data/analytics.duckdb`
4. Test connection and Save