-- Major incidents and problem candidates, derived from gold_incident_facts.
-- Rebuilt in full on every refresh: small tables, and detection depends on the whole history.
USE CATALOG workspace;
USE SCHEMA incident_copilot;

-- The fix with ticket-specific detail removed, so tickets resolved the same way group together.
CREATE OR REPLACE TEMPORARY VIEW resolved_fixes AS
SELECT
  number,
  trim(regexp_replace(
    regexp_replace(
      regexp_replace(close_notes, '\\s*Followed KB[0-9]{7}\\.', ''),
      '\\b[A-Z]{2,}-[A-Z]{2,}-[0-9]+\\b', '<device>'),
    '[0-9]+', '#')) AS fix
FROM gold_incident_facts
WHERE close_notes IS NOT NULL;

----------------------------------------------------------------------------------------------
-- Major incidents: a subcategory whose daily volume jumps to at least 10 tickets and 5x its
-- trailing 28-day average. When 80%+ of that day's tickets come from one site, the incident
-- is scoped to that site.
----------------------------------------------------------------------------------------------
CREATE OR REPLACE TEMPORARY VIEW daily_volume AS
WITH calendar AS (
  SELECT explode(sequence(min(opened_date), max(opened_date), INTERVAL 1 DAY)) AS day
  FROM gold_incident_facts
),
subcategories AS (SELECT DISTINCT subcategory FROM gold_incident_facts)
SELECT s.subcategory, c.day, count(f.number) AS tickets
FROM subcategories s
CROSS JOIN calendar c
LEFT JOIN gold_incident_facts f ON f.subcategory = s.subcategory AND f.opened_date = c.day
GROUP BY s.subcategory, c.day;

CREATE OR REPLACE TEMPORARY VIEW spike_days AS
WITH scored AS (
  SELECT
    *,
    avg(tickets) OVER w AS baseline,
    count(*) OVER w AS history_days
  FROM daily_volume
  WINDOW w AS (PARTITION BY subcategory ORDER BY day ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING)
),
spikes AS (
  SELECT subcategory, day, tickets, baseline
  FROM scored
  WHERE history_days >= 7 AND tickets >= 10 AND tickets >= 5 * greatest(baseline, 1)
),
by_site AS (
  SELECT s.subcategory, s.day, f.location, count(*) AS site_tickets
  FROM spikes s
  JOIN gold_incident_facts f ON f.subcategory = s.subcategory AND f.opened_date = s.day
  GROUP BY s.subcategory, s.day, f.location
),
dominant AS (
  SELECT
    subcategory,
    day,
    max_by(location, site_tickets) AS location,
    max(site_tickets) / sum(site_tickets) AS share
  FROM by_site
  GROUP BY subcategory, day
)
SELECT
  concat('MI', date_format(s.day, 'yyyyMMdd'), '-', s.subcategory) AS mi_id,
  s.subcategory,
  s.day,
  s.baseline,
  CASE WHEN d.share >= 0.8 THEN d.location END AS site
FROM spikes s
JOIN dominant d ON d.subcategory = s.subcategory AND d.day = s.day;

CREATE OR REPLACE TABLE major_incident_members
COMMENT 'Tickets belonging to each detected major incident.'
AS
SELECT s.mi_id, f.number
FROM spike_days s
JOIN gold_incident_facts f
  ON f.subcategory = s.subcategory
  AND f.opened_date = s.day
  AND (s.site IS NULL OR f.location = s.site);

CREATE OR REPLACE TABLE major_incidents
COMMENT 'Outages detected as same-day volume spikes in one subcategory, optionally one site.'
AS
WITH members AS (
  SELECT m.mi_id, f.*, x.fix
  FROM major_incident_members m
  JOIN gold_incident_facts f ON f.number = m.number
  LEFT JOIN resolved_fixes x ON x.number = f.number
),
top_fix AS (
  -- Most common fix, shown through the first ticket actually resolved that way.
  SELECT t.mi_id, min_by(m.close_notes, m.opened_at) AS example
  FROM (SELECT mi_id, mode(fix) AS fix FROM members WHERE fix IS NOT NULL GROUP BY mi_id) t
  JOIN members m ON m.mi_id = t.mi_id AND m.fix = t.fix
  GROUP BY t.mi_id
)
SELECT
  s.mi_id,
  s.day,
  s.subcategory,
  first(m.category) AS category,
  s.site,
  min(m.opened_at) AS started_at,
  max(m.resolved_at) AS restored_at,
  count(*) AS tickets,
  round(s.baseline, 2) AS baseline_daily,
  round(count(*) / greatest(s.baseline, 1), 1) AS spike_ratio,
  min(m.priority_label) AS worst_priority,
  array_sort(collect_set(m.location)) AS locations,
  array_sort(collect_set(m.assignment_group)) AS resolving_groups,
  count_if(m.sla_breached) AS sla_breaches,
  avg(m.mttr_hours) AS avg_mttr_hours,
  t.example AS top_fix
FROM spike_days s
JOIN members m ON m.mi_id = s.mi_id
LEFT JOIN top_fix t ON t.mi_id = s.mi_id
GROUP BY s.mi_id, s.day, s.subcategory, s.site, s.baseline, t.example;

----------------------------------------------------------------------------------------------
-- Problem candidates: a subcategory running well above its normal weekly volume for weeks.
-- A week is flagged when the 4 weeks ending there hold at least 15 tickets and 2.5x the
-- 12-week baseline before them. The surge is the run of consecutive weeks inside flagged
-- windows whose own volume is 2x baseline or more.
----------------------------------------------------------------------------------------------
CREATE OR REPLACE TEMPORARY VIEW weekly_volume AS
WITH calendar AS (
  SELECT explode(sequence(min(opened_week), max(opened_week), INTERVAL 7 DAY)) AS week
  FROM gold_incident_facts
),
subcategories AS (SELECT DISTINCT subcategory FROM gold_incident_facts),
counts AS (
  SELECT s.subcategory, c.week, count(f.number) AS tickets
  FROM subcategories s
  CROSS JOIN calendar c
  LEFT JOIN gold_incident_facts f ON f.subcategory = s.subcategory AND f.opened_week = c.week
  GROUP BY s.subcategory, c.week
)
SELECT
  *,
  sum(tickets) OVER (PARTITION BY subcategory ORDER BY week ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
    AS window_tickets,
  avg(tickets) OVER (PARTITION BY subcategory ORDER BY week ROWS BETWEEN 15 PRECEDING AND 4 PRECEDING)
    AS baseline_weekly,
  count(*) OVER (PARTITION BY subcategory ORDER BY week ROWS BETWEEN 15 PRECEDING AND 4 PRECEDING)
    AS history_weeks
FROM counts;

CREATE OR REPLACE TEMPORARY VIEW surge_weeks AS
WITH flagged AS (
  SELECT subcategory, week, baseline_weekly
  FROM weekly_volume
  WHERE history_weeks >= 8
    AND window_tickets >= 15
    AND window_tickets >= 2.5 * greatest(4 * baseline_weekly, 1)
),
elevated AS (
  -- Weeks inside a flagged window, judged against that window's baseline.
  SELECT DISTINCT v.subcategory, v.week
  FROM flagged fl
  JOIN weekly_volume v
    ON v.subcategory = fl.subcategory
    AND v.week BETWEEN date_sub(fl.week, 21) AND fl.week
    AND v.tickets >= 2 * greatest(fl.baseline_weekly, 1)
),
islands AS (
  SELECT
    *,
    -- Consecutive weeks share a key: week minus 7 days per preceding row.
    date_sub(week, 7 * (row_number() OVER (PARTITION BY subcategory ORDER BY week) - 1)) AS run_key
  FROM elevated
)
SELECT
  subcategory,
  week,
  concat('PRB', date_format(min(week) OVER (PARTITION BY subcategory, run_key), 'yyyyMMdd'), '-',
         subcategory) AS problem_id
FROM islands;

CREATE OR REPLACE TABLE problem_members
COMMENT 'Tickets opened during each problem candidate''s surge.'
AS
SELECT s.problem_id, f.number
FROM surge_weeks s
JOIN gold_incident_facts f ON f.subcategory = s.subcategory AND f.opened_week = s.week;

CREATE OR REPLACE TABLE problem_candidates
COMMENT 'Sustained volume surges in one subcategory, with the dominant fix as root-cause evidence.'
AS
WITH surges AS (
  SELECT
    problem_id,
    subcategory,
    min(week) AS first_week,
    max(week) AS last_week,
    count(*) AS weeks
  FROM surge_weeks
  GROUP BY problem_id, subcategory
),
baseline AS (
  -- The 12 weeks before each surge.
  SELECT s.problem_id, avg(v.tickets) AS baseline_weekly
  FROM surges s
  JOIN weekly_volume v
    ON v.subcategory = s.subcategory
    AND v.week BETWEEN date_sub(s.first_week, 84) AND date_sub(s.first_week, 7)
  GROUP BY s.problem_id
),
members AS (
  SELECT m.problem_id, f.*, x.fix
  FROM problem_members m
  JOIN gold_incident_facts f ON f.number = m.number
  LEFT JOIN resolved_fixes x ON x.number = f.number
),
top_fix AS (
  SELECT problem_id, mode(fix) AS fix FROM members WHERE fix IS NOT NULL GROUP BY problem_id
),
fix_share AS (
  -- How much of the surge the top fix explains, against its usual share of this subcategory.
  -- The fix is shown through the first ticket actually resolved that way.
  SELECT
    t.problem_id,
    min_by(m.close_notes, m.opened_at) FILTER (WHERE m.fix = t.fix) AS example,
    avg(CASE WHEN m.fix = t.fix THEN 1.0 ELSE 0.0 END) AS share_in_surge
  FROM top_fix t
  JOIN members m ON m.problem_id = t.problem_id AND m.fix IS NOT NULL
  GROUP BY t.problem_id
),
usual_share AS (
  SELECT
    t.problem_id,
    avg(CASE WHEN x.fix = t.fix THEN 1.0 ELSE 0.0 END) AS share_usually
  FROM top_fix t
  JOIN surges s ON s.problem_id = t.problem_id
  JOIN gold_incident_facts f ON f.subcategory = s.subcategory
  JOIN resolved_fixes x ON x.number = f.number
  WHERE NOT exists(SELECT 1 FROM problem_members pm WHERE pm.number = f.number)
  GROUP BY t.problem_id
),
linked AS (
  -- An outage inside the surge window is the likely trigger.
  SELECT s.problem_id, min(mi.mi_id) AS mi_id
  FROM surges s
  JOIN major_incidents mi
    ON mi.subcategory = s.subcategory
    AND mi.day BETWEEN s.first_week AND date_add(s.last_week, 6)
  GROUP BY s.problem_id
)
SELECT
  s.problem_id,
  s.subcategory,
  first(m.category) AS category,
  s.first_week,
  s.last_week,
  s.weeks,
  count(*) AS tickets,
  round(b.baseline_weekly, 2) AS baseline_weekly,
  round(count(*) - b.baseline_weekly * s.weeks) AS excess_tickets,
  round(sum(m.mttr_hours), 1) AS hours_to_resolve,
  count_if(m.sla_breached) AS sla_breaches,
  array_sort(collect_set(m.location)) AS locations,
  array_sort(collect_set(m.assignment_group)) AS resolving_groups,
  fs.example AS top_fix,
  round(fs.share_in_surge, 3) AS top_fix_share,
  round(u.share_usually, 3) AS top_fix_usual_share,
  l.mi_id AS major_incident
FROM surges s
JOIN members m ON m.problem_id = s.problem_id
LEFT JOIN baseline b ON b.problem_id = s.problem_id
LEFT JOIN fix_share fs ON fs.problem_id = s.problem_id
LEFT JOIN usual_share u ON u.problem_id = s.problem_id
LEFT JOIN linked l ON l.problem_id = s.problem_id
GROUP BY s.problem_id, s.subcategory, s.first_week, s.last_week, s.weeks, b.baseline_weekly,
         fs.example, fs.share_in_surge, u.share_usually, l.mi_id;
