#!/bin/bash
# Creates the bi_readonly user for Lightdash and Vanna (SELECT-only access).
# pg_read_all_data (PostgreSQL 14+) grants SELECT on all tables in all schemas.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE USER bi_readonly WITH PASSWORD '${ANALYTICS_DB_READONLY_PASSWORD:-changeme_readonly}';
  GRANT CONNECT ON DATABASE analytics TO bi_readonly;
  GRANT pg_read_all_data TO bi_readonly;
EOSQL
