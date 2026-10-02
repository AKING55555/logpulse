-- ==============================================================================
-- LogPulse Analytics Queries
-- ==============================================================================
-- These queries are designed for real-time telemetry analytics and operational
-- dashboards. Each query filters on `service` and `ts` to leverage partition
-- pruning and the composite index `idx_service_ts (service, ts)`.
-- ==============================================================================

USE logpulse;

-- ------------------------------------------------------------------------------
-- Query 1: Error rate per 5-minute window for the last 24 hours of data
-- ------------------------------------------------------------------------------
-- Calculates total requests, error counts, and error percentage bucketed into
-- 5-minute intervals. Filters on `service` and `ts`.
-- ------------------------------------------------------------------------------
SELECT
    service,
    FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(ts) / 300) * 300) AS window_start,
    COUNT(*) AS total_events,
    SUM(CASE WHEN level = 'ERROR' THEN 1 ELSE 0 END) AS error_events,
    ROUND(SUM(CASE WHEN level = 'ERROR' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS error_rate_pct
FROM events
WHERE service = 'payment-service'
  AND ts >= '2026-10-02 00:00:00'
  AND ts < '2026-10-03 00:00:00'
GROUP BY service, window_start
ORDER BY window_start ASC;

-- ------------------------------------------------------------------------------
-- Query 2: p95 Latency per service using Window Functions
-- ------------------------------------------------------------------------------
-- MySQL 8 does not provide PERCENTILE_CONT(). We compute p95 latency using a CTE
-- with ROW_NUMBER() and COUNT(*) OVER (PARTITION BY service), selecting the row
-- where rn = CEIL(0.95 * cnt).
-- ------------------------------------------------------------------------------
WITH ranked_events AS (
    SELECT
        service,
        latency_ms,
        ROW_NUMBER() OVER (PARTITION BY service ORDER BY latency_ms) AS rn,
        COUNT(*) OVER (PARTITION BY service) AS cnt
    FROM events
    WHERE service = 'order-service'
      AND ts >= '2026-09-26 00:00:00'
      AND ts < '2026-10-03 00:00:00'
)
SELECT
    service,
    latency_ms AS p95_latency_ms
FROM ranked_events
WHERE rn = CEIL(0.95 * cnt);

-- ------------------------------------------------------------------------------
-- Query 3: Top 10 Slowest Endpoints per service
-- ------------------------------------------------------------------------------
-- Aggregates average and max latency per endpoint within a service, then ranks
-- endpoints using DENSE_RANK() within the CTE.
-- ------------------------------------------------------------------------------
WITH endpoint_stats AS (
    SELECT
        service,
        endpoint,
        COUNT(*) AS call_count,
        ROUND(AVG(latency_ms), 2) AS avg_latency_ms,
        MAX(latency_ms) AS max_latency_ms
    FROM events
    WHERE service = 'auth-service'
      AND ts >= '2026-09-26 00:00:00'
      AND ts < '2026-10-03 00:00:00'
    GROUP BY service, endpoint
),
ranked_endpoints AS (
    SELECT
        service,
        endpoint,
        call_count,
        avg_latency_ms,
        max_latency_ms,
        DENSE_RANK() OVER (PARTITION BY service ORDER BY avg_latency_ms DESC) AS rnk
    FROM endpoint_stats
)
SELECT
    service,
    endpoint,
    call_count,
    avg_latency_ms,
    max_latency_ms,
    rnk AS latency_rank
FROM ranked_endpoints
WHERE rnk <= 10
ORDER BY avg_latency_ms DESC;

-- ------------------------------------------------------------------------------
-- Query 4: Point Lookup: Simple Service & Timestamp Range
-- ------------------------------------------------------------------------------
SELECT
    id, trace_id, service, level, ts, latency_ms, endpoint
FROM events
WHERE service = 'inventory-service'
  AND ts >= '2026-10-01 12:00:00'
  AND ts < '2026-10-01 14:00:00'
LIMIT 100;

-- ------------------------------------------------------------------------------
-- Query 5: Filtered Error Lookup with Range
-- ------------------------------------------------------------------------------
SELECT
    id, trace_id, service, level, ts, latency_ms, endpoint, message
FROM events
WHERE service = 'notification-service'
  AND ts >= '2026-10-01 00:00:00'
  AND ts < '2026-10-02 00:00:00'
  AND level = 'ERROR'
LIMIT 100;

-- ------------------------------------------------------------------------------
-- Query 6: Error Count per Hour for One Service over 7 Days
-- ------------------------------------------------------------------------------
-- Aggregates errors bucketed by 1-hour intervals across the full 7-day dataset.
-- ------------------------------------------------------------------------------
SELECT
    service,
    DATE_FORMAT(ts, '%Y-%m-%d %H:00:00') AS hour_bucket,
    COUNT(*) AS error_count
FROM events
WHERE service = 'payment-service'
  AND ts >= '2026-09-26 00:00:00'
  AND ts < '2026-10-03 00:00:00'
  AND level = 'ERROR'
GROUP BY service, hour_bucket
ORDER BY hour_bucket ASC;

-- ------------------------------------------------------------------------------
-- Query 7: All Events for One Service in a 1-Hour Window
-- ------------------------------------------------------------------------------
-- Retrieves all log event attributes for a single service in a focused 1-hour window.
-- ------------------------------------------------------------------------------
SELECT
    id,
    trace_id,
    service,
    host,
    level,
    ts,
    latency_ms,
    endpoint,
    message
FROM events
WHERE service = 'payment-service'
  AND ts >= '2026-10-02 14:00:00'
  AND ts < '2026-10-02 15:00:00';

-- ------------------------------------------------------------------------------
-- Query 8: Alert Query — Error Rate for One Service over Last 5 Minutes
-- ------------------------------------------------------------------------------
-- Evaluates error rate percentage for payment-service across the trailing 5-minute
-- window relative to the dataset ceiling (2026-10-02 23:59:59.925).
-- ------------------------------------------------------------------------------
SELECT
    service,
    COUNT(*) AS total_events,
    SUM(CASE WHEN level = 'ERROR' THEN 1 ELSE 0 END) AS error_events,
    ROUND(SUM(CASE WHEN level = 'ERROR' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS error_rate_pct
FROM events
WHERE service = 'payment-service'
  AND ts >= '2026-10-02 23:55:00'
GROUP BY service;
