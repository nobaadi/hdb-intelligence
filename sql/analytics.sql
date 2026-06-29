-- HDB Resale Intelligence -- Analytical Queries
-- Run against the SQLite database (hdb.db) after ETL has populated the transactions table.
--
-- Schema: transactions
--   id, month (YYYY-MM), town, flat_type, block, street_name, storey_range,
--   floor_area_sqm, flat_model, lease_commence_date, remaining_lease,
--   resale_price, price_per_sqm


-- ============================================================
-- 1. Month-over-month price change per town
--    Window: LAG to compare each month against the previous one
-- ============================================================

WITH monthly_avg AS (
    SELECT
        town,
        month,
        ROUND(AVG(resale_price), 0)  AS avg_price,
        COUNT(*)                      AS volume
    FROM transactions
    GROUP BY town, month
),
mom AS (
    SELECT
        town,
        month,
        avg_price,
        volume,
        LAG(avg_price) OVER (
            PARTITION BY town
            ORDER BY month
        ) AS prev_month_price
    FROM monthly_avg
)
SELECT
    town,
    month,
    avg_price,
    prev_month_price,
    ROUND(avg_price - prev_month_price, 0)              AS mom_delta,
    ROUND(
        (avg_price - prev_month_price) * 100.0
        / NULLIF(prev_month_price, 0),
        2
    )                                                   AS mom_pct_change,
    CASE
        WHEN avg_price > prev_month_price THEN 'rising'
        WHEN avg_price < prev_month_price THEN 'falling'
        ELSE 'flat'
    END                                                 AS direction
FROM mom
WHERE prev_month_price IS NOT NULL
ORDER BY town, month;


-- ============================================================
-- 2. Town ranking by average resale price
--    Window: RANK, DENSE_RANK, PERCENT_RANK, NTILE(4)
-- ============================================================

WITH town_stats AS (
    SELECT
        town,
        ROUND(AVG(resale_price), 0)  AS avg_price,
        ROUND(AVG(price_per_sqm), 2) AS avg_psm,
        COUNT(*)                      AS volume
    FROM transactions
    GROUP BY town
)
SELECT
    town,
    avg_price,
    avg_psm,
    volume,
    RANK()         OVER (ORDER BY avg_price DESC)       AS price_rank,
    DENSE_RANK()   OVER (ORDER BY avg_price DESC)       AS dense_rank,
    ROUND(
        PERCENT_RANK() OVER (ORDER BY avg_price),
        4
    )                                                   AS percentile,
    NTILE(4)       OVER (ORDER BY avg_price DESC)       AS price_quartile
FROM town_stats
ORDER BY avg_price DESC;


-- ============================================================
-- 3. Rolling 3-month average price trend (national)
--    Window: AVG with ROWS BETWEEN frame
-- ============================================================

WITH monthly_national AS (
    SELECT
        month,
        ROUND(AVG(resale_price), 0)  AS avg_price,
        COUNT(*)                      AS volume
    FROM transactions
    GROUP BY month
)
SELECT
    month,
    avg_price,
    ROUND(
        AVG(avg_price) OVER (
            ORDER BY month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        0
    )                                                   AS rolling_3m_avg,
    ROUND(
        AVG(avg_price) OVER (
            ORDER BY month
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ),
        0
    )                                                   AS cumulative_avg,
    volume
FROM monthly_national
ORDER BY month;


-- ============================================================
-- 4. Storey premium analysis
--    Cumulative price share with SUM() OVER
-- ============================================================

WITH storey_stats AS (
    SELECT
        storey_range,
        ROUND(AVG(resale_price), 0)  AS avg_price,
        COUNT(*)                      AS volume,
        SUM(COUNT(*)) OVER ()         AS total_volume
    FROM transactions
    WHERE storey_range IS NOT NULL
    GROUP BY storey_range
)
SELECT
    storey_range,
    avg_price,
    volume,
    ROUND(volume * 100.0 / total_volume, 2)             AS pct_of_volume,
    ROUND(
        SUM(avg_price) OVER (
            ORDER BY avg_price
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ),
        0
    )                                                   AS cumulative_price_sum,
    avg_price - FIRST_VALUE(avg_price) OVER (
        ORDER BY avg_price
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )                                                   AS premium_vs_lowest
FROM storey_stats
ORDER BY avg_price;


-- ============================================================
-- 5. Year-on-year price change by flat type
--    CTE chain: annual averages, then YoY delta with LAG
-- ============================================================

WITH annual AS (
    SELECT
        SUBSTR(month, 1, 4) AS year,
        flat_type,
        ROUND(AVG(resale_price), 0) AS avg_price,
        COUNT(*)                    AS volume
    FROM transactions
    GROUP BY year, flat_type
),
with_lag AS (
    SELECT
        year,
        flat_type,
        avg_price,
        volume,
        LAG(avg_price) OVER (
            PARTITION BY flat_type
            ORDER BY year
        ) AS prev_year_price
    FROM annual
)
SELECT
    year,
    flat_type,
    avg_price,
    volume,
    prev_year_price,
    ROUND(avg_price - prev_year_price, 0)               AS yoy_delta,
    ROUND(
        (avg_price - prev_year_price) * 100.0
        / NULLIF(prev_year_price, 0),
        2
    )                                                   AS yoy_pct_change
FROM with_lag
WHERE prev_year_price IS NOT NULL
ORDER BY year DESC, flat_type;


-- ============================================================
-- 6. Price distribution quartiles by town
--    Window: NTILE to segment transactions into price bands
-- ============================================================

WITH quartiled AS (
    SELECT
        town,
        flat_type,
        resale_price,
        NTILE(4) OVER (
            PARTITION BY town
            ORDER BY resale_price
        ) AS price_quartile
    FROM transactions
)
SELECT
    town,
    price_quartile,
    COUNT(*)                            AS transactions,
    ROUND(MIN(resale_price), 0)         AS q_min,
    ROUND(AVG(resale_price), 0)         AS q_avg,
    ROUND(MAX(resale_price), 0)         AS q_max
FROM quartiled
GROUP BY town, price_quartile
ORDER BY town, price_quartile;


-- ============================================================
-- 7. Identify towns where recent prices diverge from their
--    long-run average (potential overvaluation signal)
--    CTE chain: long-run avg, recent avg, divergence scoring
-- ============================================================

WITH long_run AS (
    SELECT
        town,
        ROUND(AVG(resale_price), 0)  AS longrun_avg
    FROM transactions
    GROUP BY town
),
recent AS (
    SELECT
        town,
        ROUND(AVG(resale_price), 0)  AS recent_avg
    FROM transactions
    WHERE month >= (
        SELECT SUBSTR(MAX(month), 1, 4) || '-01'
        FROM transactions
    )
    GROUP BY town
),
divergence AS (
    SELECT
        r.town,
        l.longrun_avg,
        r.recent_avg,
        r.recent_avg - l.longrun_avg                    AS abs_divergence,
        ROUND(
            (r.recent_avg - l.longrun_avg) * 100.0
            / NULLIF(l.longrun_avg, 0),
            2
        )                                               AS pct_divergence
    FROM recent r
    JOIN long_run l USING (town)
)
SELECT
    town,
    longrun_avg,
    recent_avg,
    abs_divergence,
    pct_divergence,
    CASE
        WHEN pct_divergence > 10  THEN 'significantly above average'
        WHEN pct_divergence > 3   THEN 'above average'
        WHEN pct_divergence < -10 THEN 'significantly below average'
        WHEN pct_divergence < -3  THEN 'below average'
        ELSE 'near average'
    END                                                 AS signal
FROM divergence
ORDER BY pct_divergence DESC;
