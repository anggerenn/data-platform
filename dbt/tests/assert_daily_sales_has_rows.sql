-- Singular test: fails (returns a row) if daily_sales is empty.
-- dbt treats any returned rows as test failures.
SELECT 1
FROM {{ ref('daily_sales') }}
HAVING COUNT(*) = 0
