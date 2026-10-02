-- ==============================================================================
-- LogPulse Database Schema (MySQL 8)
-- ==============================================================================
-- Architecture Note on Partitioning & Idempotency:
-- 1. MySQL Partitioning Constraint:
--    In MySQL, every unique key (including the PRIMARY KEY) on a partitioned table
--    MUST include all columns used in the partitioning expression (here, `ts` via `TO_DAYS(ts)`).
--    This constraint ensures that unique key checks can be performed locally within the
--    relevant partition rather than requiring global cross-partition coordination.
--
-- 2. Source-Driven Idempotency:
--    Because `ts` is strictly part of the composite unique constraint `uq_trace (trace_id, ts)`,
--    ingestion idempotency and deduplication strictly require that `ts` is generated
--    and attached by the originating client/producer, NEVER defaulted to `NOW()` or `CURRENT_TIMESTAMP`.
--    If timestamps were generated at database insertion time, network retries of the same event
--    would receive different timestamps and bypass the deduplication constraint.
--
-- Note on Secondary Indexes:
--    At this initial stage, NO secondary index exists other than `uq_trace` to represent
--    the baseline "before" state for index benchmarking.
-- ==============================================================================

USE logpulse;

DROP TABLE IF EXISTS events;

CREATE TABLE events (
    id BIGINT UNSIGNED AUTO_INCREMENT,
    trace_id CHAR(36) NOT NULL,
    service VARCHAR(64) NOT NULL,
    host VARCHAR(64) NOT NULL,
    level ENUM('DEBUG', 'INFO', 'WARN', 'ERROR') NOT NULL,
    ts DATETIME(3) NOT NULL,
    message TEXT,
    latency_ms INT,
    endpoint VARCHAR(128),
    PRIMARY KEY (id, ts),
    UNIQUE KEY uq_trace (trace_id, ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
PARTITION BY RANGE (TO_DAYS(ts)) (
    -- Test data historical window (7 days)
    PARTITION p20260926 VALUES LESS THAN (TO_DAYS('2026-09-27')),
    PARTITION p20260927 VALUES LESS THAN (TO_DAYS('2026-09-28')),
    PARTITION p20260928 VALUES LESS THAN (TO_DAYS('2026-09-29')),
    PARTITION p20260929 VALUES LESS THAN (TO_DAYS('2026-09-30')),
    PARTITION p20260930 VALUES LESS THAN (TO_DAYS('2026-10-01')),
    PARTITION p20261001 VALUES LESS THAN (TO_DAYS('2026-10-02')),
    PARTITION p20261002 VALUES LESS THAN (TO_DAYS('2026-10-03')),
    -- Current day
    PARTITION p20261003 VALUES LESS THAN (TO_DAYS('2026-10-04')),
    -- Future window (next 7 days)
    PARTITION p20261004 VALUES LESS THAN (TO_DAYS('2026-10-05')),
    PARTITION p20261005 VALUES LESS THAN (TO_DAYS('2026-10-06')),
    PARTITION p20261006 VALUES LESS THAN (TO_DAYS('2026-10-07')),
    PARTITION p20261007 VALUES LESS THAN (TO_DAYS('2026-10-08')),
    PARTITION p20261008 VALUES LESS THAN (TO_DAYS('2026-10-09')),
    PARTITION p20261009 VALUES LESS THAN (TO_DAYS('2026-10-10')),
    PARTITION p20261010 VALUES LESS THAN (TO_DAYS('2026-10-11')),
    PARTITION p20261011 VALUES LESS THAN (TO_DAYS('2026-10-12')),
    -- Catch-all partition for any future records
    PARTITION pmax VALUES LESS THAN MAXVALUE
);
