-- ==============================================================================
-- LogPulse Partition Maintenance Script: Adding Future Partitions
-- ==============================================================================
--
-- Why REORGANIZE PARTITION?
-- When a table includes a catch-all partition (`pmax VALUES LESS THAN MAXVALUE`),
-- you cannot simply use `ALTER TABLE ... ADD PARTITION` because any future value
-- already falls within `pmax`.
-- Instead, MySQL requires splitting `pmax` using `REORGANIZE PARTITION pmax INTO (...)`.
--
-- Operational Scheduling:
-- Run this script as a daily automated job (e.g., via AWS EventBridge -> Lambda,
-- a Kubernetes CronJob, or a standard host cron) scheduled at 00:05 UTC.
-- Maintaining a rolling window of 7-14 days of future partitions ensures that any
-- clock drift or early-arriving events never land into `pmax`, keeping partition
-- pruning highly optimal.
--
-- Example: Reorganizing pmax to introduce partition for 2026-10-12
-- ==============================================================================

USE logpulse;

ALTER TABLE events REORGANIZE PARTITION pmax INTO (
    PARTITION p20261012 VALUES LESS THAN (TO_DAYS('2026-10-13')),
    PARTITION pmax VALUES LESS THAN MAXVALUE
);

-- ==============================================================================
-- Automated Dynamic Procedure Example (Optional / Native Event Scheduler)
-- ==============================================================================
-- The following stored procedure demonstrates how to calculate tomorrow's date
-- dynamically and execute the reorganization:
--
-- DELIMITER //
-- CREATE PROCEDURE MaintainPartitions()
-- BEGIN
--     DECLARE v_next_date DATE;
--     DECLARE v_part_name VARCHAR(32);
--     DECLARE v_less_than_date DATE;
--     DECLARE v_sql TEXT;
--
--     -- Look ahead 7 days into future
--     SET v_next_date = DATE_ADD(CURDATE(), INTERVAL 8 DAY);
--     SET v_part_name = CONCAT('p', DATE_FORMAT(v_next_date, '%Y%m%d'));
--     SET v_less_than_date = DATE_ADD(v_next_date, INTERVAL 1 DAY);
--
--     SET @sql = CONCAT(
--         'ALTER TABLE events REORGANIZE PARTITION pmax INTO (',
--         'PARTITION ', v_part_name, ' VALUES LESS THAN (TO_DAYS(''', v_less_than_date, ''')),',
--         'PARTITION pmax VALUES LESS THAN MAXVALUE)'
--     );
--     PREPARE stmt FROM @sql;
--     EXECUTE stmt;
--     DEALLOCATE PREPARE stmt;
-- END //
-- DELIMITER ;
-- ==============================================================================
