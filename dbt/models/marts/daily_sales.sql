SELECT
    order_date,
    category,
    city,
    COUNT(distinct order_id) as order_count,
    COUNT(distinct customer_id) as customer_count,
    SUM(quantity) as units_sold,
    SUM(amount) as revenue,
    SUM(amount * quantity) as total_revenue
FROM {{ ref('stg_orders') }}
GROUP BY 1,2,3
ORDER BY order_date DESC