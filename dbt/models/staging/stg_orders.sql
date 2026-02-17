{{ config(materialized='view') }}

SELECT
    order_id,
    customer_id,
    order_date,
    category,
    city,
    amount,
    quantity,
    amount * quantity as line_total
FROM {{ source('raw', 'orders') }}
WHERE amount > 0