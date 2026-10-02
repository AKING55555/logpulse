# LogPulse Index Benchmark Report

_Generated: 2026-10-02 20:39 UTC_

## Environment

| Key | Value |
|:----|:------|
| MySQL version | 8.0 (Docker, host port 3307) |
| Total rows | 1,000,001 |
| Table | `logpulse.events` |
| Index added | `idx_service_ts (service, ts)` |
| Runs per query | 3 (first run may be cold cache) |
| Timing | Wall-clock via `time.perf_counter()` |

> **Cold-cache note:** The first timed run may be slower because InnoDB buffer
> pool pages are not yet loaded. The median of 3 runs is the canonical figure.

## Summary Table

| Query | Before (ms) | After (ms) | Speed-up | Rows examined (before) | Rows examined (after) | Access type (before) | Access type (after) |
|:------|------------:|-----------:|--------:|----------------------:|---------------------:|:---------------------|:--------------------|
| Q1 - Error rate per 5-min window (payment-service, last 24 h of data) | 149.7 | 153.2 | 0.98x | 142253 | 142253 | Sort | Sort |
| Q2 - p95 latency per service (order-service, full 7-day window) | 4986.9 | 5165.2 | 0.97x | 989521 | 989532 | Filter | Filter |
| Q3 - Top 10 slowest endpoints (auth-service, full 7-day window) | 1227.7 | 1281.8 | 0.96x | 989521 | 989532 | Sort | Sort |
| Q4 - Point lookup: inventory-service, 2-hour window | 8.5 | 5.7 | 1.49x | 141175 | 2340 | Filter | Index range scan |
| Q5 - Filtered ERROR lookup: notification-service, 1-day window | 15.5 | 21.0 | 0.74x | 141175 | 57096 | Filter | Filter |

## Per-Query Detail

### Q1 Error Rate 5Min

**Before**

- Run 1: 156.8 ms
- Run 2: 149.7 ms
- Run 3: 145.8 ms
- **Median: 149.7 ms**
- Rows examined: 142253
- Access type: Sort
- EXPLAIN actual time (ms): 254.000
- Raw: [raw/before_q1_error_rate_5min.txt](raw/before_q1_error_rate_5min.txt)

**After**

- Run 1: 151.5 ms
- Run 2: 153.2 ms
- Run 3: 159.2 ms
- **Median: 153.2 ms**
- Rows examined: 142253
- Access type: Sort
- EXPLAIN actual time (ms): 76.200
- Raw: [raw/after_q1_error_rate_5min.txt](raw/after_q1_error_rate_5min.txt)

> **Index had minimal effect** (149.7 ms -> 153.2 ms). Partition pruning alone may be sufficient, or result set size makes both plans equivalent.

### Q2 P95 Latency

**Before**

- Run 1: 5284.6 ms
- Run 2: 4986.9 ms
- Run 3: 4960.5 ms
- **Median: 4986.9 ms**
- Rows examined: 989521
- Access type: Filter
- EXPLAIN actual time (ms): 1157.000
- Raw: [raw/before_q2_p95_latency.txt](raw/before_q2_p95_latency.txt)

**After**

- Run 1: 5383.0 ms
- Run 2: 5165.2 ms
- Run 3: 5007.4 ms
- **Median: 5165.2 ms**
- Rows examined: 989532
- Access type: Filter
- EXPLAIN actual time (ms): 1333.000
- Raw: [raw/after_q2_p95_latency.txt](raw/after_q2_p95_latency.txt)

> **Index had minimal effect** (4986.9 ms -> 5165.2 ms). Partition pruning alone may be sufficient, or result set size makes both plans equivalent.

### Q3 Top10 Slow Endpoints

**Before**

- Run 1: 1227.7 ms
- Run 2: 1252.6 ms
- Run 3: 1202.6 ms
- **Median: 1227.7 ms**
- Rows examined: 989521
- Access type: Sort
- EXPLAIN actual time (ms): 995.000
- Raw: [raw/before_q3_top10_slow_endpoints.txt](raw/before_q3_top10_slow_endpoints.txt)

**After**

- Run 1: 1335.9 ms
- Run 2: 1281.8 ms
- Run 3: 1262.1 ms
- **Median: 1281.8 ms**
- Rows examined: 989532
- Access type: Sort
- EXPLAIN actual time (ms): 1023.000
- Raw: [raw/after_q3_top10_slow_endpoints.txt](raw/after_q3_top10_slow_endpoints.txt)

> **Index had minimal effect** (1227.7 ms -> 1281.8 ms). Partition pruning alone may be sufficient, or result set size makes both plans equivalent.

### Q4 Point Lookup

**Before**

- Run 1: 8.5 ms
- Run 2: 8.5 ms
- Run 3: 7.7 ms
- **Median: 8.5 ms**
- Rows examined: 141175
- Access type: Filter
- EXPLAIN actual time (ms): 3.490
- Raw: [raw/before_q4_point_lookup.txt](raw/before_q4_point_lookup.txt)

**After**

- Run 1: 6.2 ms
- Run 2: 5.7 ms
- Run 3: 5.7 ms
- **Median: 5.7 ms**
- Rows examined: 2340
- Access type: Index range scan
- EXPLAIN actual time (ms): 1.030
- Raw: [raw/after_q4_point_lookup.txt](raw/after_q4_point_lookup.txt)

> **Index helped.** Median 8.5 ms -> 5.7 ms (1.49x speed-up). The (service, ts) index enables an index range scan instead of a full partition scan.

### Q5 Error Lookup

**Before**

- Run 1: 17.6 ms
- Run 2: 14.1 ms
- Run 3: 15.5 ms
- **Median: 15.5 ms**
- Rows examined: 141175
- Access type: Filter
- EXPLAIN actual time (ms): 11.500
- Raw: [raw/before_q5_error_lookup.txt](raw/before_q5_error_lookup.txt)

**After**

- Run 1: 21.4 ms
- Run 2: 21.0 ms
- Run 3: 14.5 ms
- **Median: 21.0 ms**
- Rows examined: 57096
- Access type: Filter
- EXPLAIN actual time (ms): 13.900
- Raw: [raw/after_q5_error_lookup.txt](raw/after_q5_error_lookup.txt)

> **Index did not improve this query** (15.5 ms -> 21.0 ms). See raw EXPLAIN ANALYZE for details.

## Methodology

- Timings: wall-clock via `time.perf_counter()` (Python).
- `EXPLAIN ANALYZE` forces full execution; `actual time` is server-side only.
- `ANALYZE TABLE events` runs after index creation for fresh optimizer stats.
- Buffer pool is NOT flushed between runs; runs 2-3 reflect warm-cache behaviour.
- Raw EXPLAIN ANALYZE outputs: `docs/benchmarks/raw/`.
