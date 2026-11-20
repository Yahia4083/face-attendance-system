-- Manual repair helper for historical attendance rows that were previously
-- marked as unscheduled but still contain scheduled/late values.
--
-- Review the SELECT output first. Run the UPDATE only after an administrator
-- confirms these rows are truly unscheduled historical inconsistencies.
-- This script intentionally does not run automatically from the application.

SELECT
    id,
    employee_id,
    attendance_date,
    status,
    is_unscheduled,
    is_late,
    is_early_departure,
    scheduled_start_datetime,
    scheduled_end_datetime,
    late_minutes,
    early_departure_minutes
FROM attendance_records
WHERE is_unscheduled = 1
  AND (
      status <> 'UNSCHEDULED'
      OR scheduled_start_datetime IS NOT NULL
      OR scheduled_end_datetime IS NOT NULL
      OR is_late <> 0
      OR is_early_departure <> 0
      OR late_minutes <> 0
      OR early_departure_minutes <> 0
  )
ORDER BY attendance_date, id;

-- If the reviewed rows are confirmed as truly unscheduled, execute inside
-- a transaction. Use ROLLBACK instead of COMMIT if the affected rows look wrong.
--
-- START TRANSACTION;
--
-- UPDATE attendance_records
-- SET
--     status = 'UNSCHEDULED',
--     employee_schedule_id = NULL,
--     schedule_template_id = NULL,
--     scheduled_start_datetime = NULL,
--     scheduled_end_datetime = NULL,
--     is_unscheduled = 1,
--     is_late = 0,
--     is_early_departure = 0,
--     late_minutes = 0,
--     early_departure_minutes = 0,
--     updated_at = UTC_TIMESTAMP()
-- WHERE is_unscheduled = 1
--   AND (
--       status <> 'UNSCHEDULED'
--       OR scheduled_start_datetime IS NOT NULL
--       OR scheduled_end_datetime IS NOT NULL
--       OR is_late <> 0
--       OR is_early_departure <> 0
--       OR late_minutes <> 0
--       OR early_departure_minutes <> 0
--   );
--
-- SELECT ROW_COUNT() AS repaired_rows;
--
-- COMMIT;
