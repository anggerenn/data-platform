# Data Platform Monorepo

## Stack
- **dlt**: Data ingestion
- **dbt**: Transformations
- **DuckDB**: Analytics database
- **Lightdash**: BI & dashboards
- **Prefect**: Orchestration

## Structure
- `/dbt` - dbt models and profiles
- `/lightdash` - Dashboard YAML definitions
- `/prefect` - Orchestration flows
- `/docker` - Docker configuration
- `/scripts` - Database init scripts

## Local Development
1. Copy `.env.example` to `.env` and fill in values
2. Run `docker compose -f docker/docker-compose.yml up -d`
3. Access Prefect UI at `http://localhost:4200`

> Note: Lightdash is not available locally due to ARM compatibility issues on Apple Silicon. Use VPS deployment to access Lightdash.

## Environment Variables
| Variable | Description |
|---|---|
| `POSTGRES_PASSWORD` | Postgres password for Prefect and Lightdash |
| `ANALYTICS_DB_PATH` | Path to DuckDB file |
| `ANALYTICS_PIPELINES_DIR` | Path to dlt pipeline state directory |
| `LIGHTDASH_SECRET` | Random secret for Lightdash (generate with `openssl rand -hex 32`) |

## Deployment to Coolify (VPS)
1. Push repo to GitHub
2. In Coolify, create new project
3. Choose Docker Compose and point to `docker/docker-compose.yml`
4. Set environment variables from the table above
5. Ensure `/data` directory exists on VPS: `mkdir -p /data`
6. Deploy!