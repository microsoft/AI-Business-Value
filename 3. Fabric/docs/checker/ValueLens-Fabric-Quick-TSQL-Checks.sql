-- ValueLens Fabric | Quick SQL checks
-- T-SQL edition | Four read-only queries
-- Run in the Lakehouse SQL analytics endpoint (Tables / Views / SQL query tabs), NOT a Spark SQL notebook.
-- Run one query at a time.
-- Reviewed against the local notebook/model contracts only; not executed against a live endpoint.

-- 1) Total users, rows and date range
-- Compare coverage before/after backfill. Users = identities with activity, not all licensed users.
SELECT 'parsed' AS stage, COUNT_BIG(*) AS total_rows,
       COUNT(DISTINCT Audit_UserId) AS active_users,
       MIN(CreationDate) AS earliest_activity,
       MAX(CreationDate) AS latest_activity
FROM dbo.copilot_interactions_parsed
UNION ALL
SELECT 'curated', COUNT_BIG(*), COUNT(DISTINCT Audit_UserId),
       MIN(CreationDate), MAX(CreationDate)
FROM dbo.copilot_interactions_curated;

-- 2) Weekly tasks, messages, sessions and users
-- Uses stored Monday-based WeekStart. Prompt rows match the shipped AI Tasks definition;
-- resource expansion means they are NOT distinct prompts.
SELECT CAST(WeekStart AS date) AS week_start,
       COUNT_BIG(*) AS prompt_rows_AI_tasks,
       COUNT(DISTINCT Message_Id) AS distinct_prompt_messages,
       COUNT(DISTINCT ThreadId) AS sessions,
       COUNT(DISTINCT Audit_UserId) AS prompt_active_users
FROM dbo.copilot_interactions_curated
WHERE UPPER(LTRIM(RTRIM(Message_isPrompt))) = 'TRUE'
GROUP BY CAST(WeekStart AS date)
ORDER BY week_start;

-- 3) Weekly parsed versus curated row counts
-- Derives Monday weeks from CreationDate instead of relying on parsed WeekStart.
-- Matching counts help with parity checks, but do not prove perfect deduplication.
WITH stages AS (
  SELECT 'parsed' AS stage, CreationDate
  FROM dbo.copilot_interactions_parsed
  UNION ALL
  SELECT 'curated', CreationDate
  FROM dbo.copilot_interactions_curated
), weeks AS (
  SELECT stage,
    DATEADD(day,
      -((DATEDIFF(day, CAST('19000101' AS date),
                       CAST(CreationDate AS date)) % 7 + 7) % 7),
      CAST(CreationDate AS date)) AS week_start
  FROM stages
)
SELECT week_start,
       SUM(CASE WHEN stage = 'parsed' THEN CAST(1 AS bigint) ELSE 0 END) AS parsed_rows,
       SUM(CASE WHEN stage = 'curated' THEN CAST(1 AS bigint) ELSE 0 END) AS curated_rows
FROM weeks
GROUP BY week_start
ORDER BY week_start;

-- 4) Current licensed-user snapshot
-- Roster rows include unlicensed users. These are current licences, not historical entitlement.
SELECT COUNT_BIG(*) AS roster_rows,
       COUNT(DISTINCT UPN_Normalized) AS distinct_roster_users,
       COUNT(DISTINCT CASE
         WHEN UPPER(LTRIM(RTRIM(Has_license))) IN ('TRUE', 'YES', 'Y', '1')
         THEN UPN_Normalized END) AS licensed_users
FROM dbo.copilot_licensed_users;

-- Notes:
-- - Save baseline results, then compare after normal scheduled runs.
-- - Compare stable historical weeks; exclude a still-moving current week.
-- - Rising rows with flat distinct messages/sessions can indicate replay or resource expansion.
-- - Weekly distinct users/sessions/messages are not additive across weeks.
-- - SQL excludes NULL from DISTINCT counts; Power BI can count BLANK under its own filters.
-- - After a parsed-table backfill, rerun the processor before expecting curated/report changes.
