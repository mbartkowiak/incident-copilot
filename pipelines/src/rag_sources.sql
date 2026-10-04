-- Source tables for Vector Search delta-sync indexes. MERGE (not CREATE OR REPLACE) keeps the
-- change data feed continuous so index syncs stay incremental.
USE CATALOG workspace;
USE SCHEMA incident_copilot;

-- Written by the API when a dispatcher accepts, edits or rejects an agent draft. The API's
-- service principal can write here and to kb_drafts only.
CREATE TABLE IF NOT EXISTS triage_feedback (
  run_id STRING NOT NULL,
  created_at TIMESTAMP,
  decision STRING COMMENT 'accepted | edited | rejected',
  short_description STRING,
  description STRING,
  suggested_group STRING,
  final_group STRING,
  priority STRING,
  resolution STRING,
  citations STRING,
  agent_model STRING,
  decided_by STRING COMMENT 'Signed-in user who made the decision (added 2026-10 with sign-in)'
);

-- Live tickets created in the app (conversational intake, then triage and dispatcher work).
-- Timestamps are company local time (America/Chicago), like the source extract. The API's
-- service principal can write here too.
CREATE TABLE IF NOT EXISTS tickets (
  number STRING NOT NULL COMMENT 'INC1000001 upward, history uses INC00xxxxx',
  opened_at TIMESTAMP,
  updated_at TIMESTAMP,
  state STRING COMMENT 'New | In Progress | Resolved',
  caller STRING,
  location STRING,
  contact_type STRING,
  category STRING,
  subcategory STRING,
  cmdb_ci STRING,
  impact INT,
  urgency INT,
  priority INT,
  short_description STRING,
  description STRING,
  assignment_group STRING,
  suggested_group STRING COMMENT 'Routing model prediction at creation',
  triage_confidence DOUBLE,
  triage_mode STRING COMMENT 'auto (assigned by the model) | review (waiting for a dispatcher) | manual',
  resolved_at TIMESTAMP,
  close_code STRING,
  close_notes STRING,
  work_notes STRING COMMENT 'Journal lines: <timestamp> - <author>: <text>',
  origin STRING COMMENT 'app (virtual agent) | servicenow (imported by the connector)',
  sn_sys_id STRING COMMENT 'Linked ServiceNow incident',
  sn_number STRING
);

-- History and live tickets in one shape, read by the incident queue and ticket pages.
-- SLA fields for live tickets are computed at query time against the company's clock.
CREATE OR REPLACE VIEW incident_queue AS
SELECT
  number, opened_at, resolved_at, closed_at, state, priority, priority_label,
  short_description, description, category, subcategory, cmdb_ci, location, contact_type,
  caller_id, assignment_group, assigned_to, reassignment_count, reopen_count, close_code,
  close_notes, work_notes, sla_target_hours, sla_breached, mttr_hours, is_resolved,
  'history' AS source,
  CAST(NULL AS DOUBLE) AS live_elapsed_hours,
  CAST(NULL AS STRING) AS sn_number,
  CAST(NULL AS STRING) AS sn_sys_id
FROM gold_incident_facts

UNION ALL

SELECT
  number, opened_at, resolved_at, CAST(NULL AS TIMESTAMP) AS closed_at, state, priority,
  CASE priority WHEN 1 THEN '1 - Critical' WHEN 2 THEN '2 - High' WHEN 3 THEN '3 - Moderate'
    WHEN 4 THEN '4 - Low' ELSE '5 - Planning' END AS priority_label,
  short_description, description, category, subcategory, cmdb_ci, location, contact_type,
  caller AS caller_id, assignment_group, CAST(NULL AS STRING) AS assigned_to,
  size(split(coalesce(work_notes, ''), 'Reassigning to ')) - 1 AS reassignment_count,
  0 AS reopen_count, close_code, close_notes, work_notes, sla_target_hours,
  elapsed_hours > sla_target_hours AS sla_breached,
  CASE WHEN resolved_at IS NOT NULL THEN elapsed_hours END AS mttr_hours,
  resolved_at IS NOT NULL AS is_resolved,
  'live' AS source,
  elapsed_hours AS live_elapsed_hours,
  sn_number,
  sn_sys_id
FROM (
  SELECT
    *,
    CASE priority WHEN 1 THEN 4 WHEN 2 THEN 8 WHEN 3 THEN 72 WHEN 4 THEN 120 ELSE 240 END
      AS sla_target_hours,
    (unix_timestamp(coalesce(resolved_at,
                             from_utc_timestamp(current_timestamp(), 'America/Chicago')))
     - unix_timestamp(opened_at)) / 3600.0 AS elapsed_hours
  FROM tickets
);

CREATE TABLE IF NOT EXISTS incident_docs (
  number STRING NOT NULL,
  embed_text STRING COMMENT 'Problem statement only: what a new ticket will be compared against',
  short_description STRING,
  close_notes STRING,
  category STRING,
  subcategory STRING,
  assignment_group STRING,
  location STRING,
  cmdb_ci STRING,
  priority_label STRING,
  opened_at TIMESTAMP,
  mttr_hours DOUBLE,
  kb_reference STRING
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

MERGE INTO incident_docs t
USING (
  SELECT
    number,
    concat_ws('\n', short_description, description) AS embed_text,
    short_description,
    close_notes,
    category,
    subcategory,
    assignment_group,
    location,
    cmdb_ci,
    priority_label,
    opened_at,
    mttr_hours,
    kb_reference
  FROM gold_incident_facts
  WHERE is_resolved AND close_notes IS NOT NULL

  UNION ALL

  -- Agent memory: dispatcher-approved triage becomes a precedent (number prefix FB-).
  SELECT
    concat('FB-', substr(run_id, 1, 8)) AS number,
    concat_ws('\n', short_description, description) AS embed_text,
    short_description,
    resolution AS close_notes,
    NULL AS category,
    NULL AS subcategory,
    final_group AS assignment_group,
    NULL AS location,
    NULL AS cmdb_ci,
    priority AS priority_label,
    created_at AS opened_at,
    NULL AS mttr_hours,
    NULL AS kb_reference
  FROM triage_feedback
  WHERE decision IN ('accepted', 'edited')
) s
ON t.number = s.number
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
WHEN NOT MATCHED BY SOURCE THEN DELETE;

-- One row per distinct problem statement. Repeat tickets collapse into a single precedent, so
-- retrieval returns varied cases instead of five copies of the same one, and far fewer rows
-- need embedding.
CREATE TABLE IF NOT EXISTS incident_precedents (
  precedent_id STRING NOT NULL,
  number STRING COMMENT 'Most recent incident with this problem statement',
  embed_text STRING,
  short_description STRING,
  close_notes STRING,
  category STRING,
  subcategory STRING,
  assignment_group STRING COMMENT 'Team that resolved the example ticket',
  location STRING,
  priority_label STRING,
  mttr_hours DOUBLE COMMENT 'Average across occurrences',
  kb_reference STRING,
  occurrences BIGINT,
  last_seen TIMESTAMP
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

MERGE INTO incident_precedents t
USING (
  SELECT
    sha2(lower(embed_text), 256) AS precedent_id,
    max_by(number, opened_at) AS number,
    max_by(embed_text, opened_at) AS embed_text,
    max_by(short_description, opened_at) AS short_description,
    max_by(close_notes, opened_at) AS close_notes,
    max_by(category, opened_at) AS category,
    max_by(subcategory, opened_at) AS subcategory,
    -- Team, fix and KB all come from the same example ticket so they never contradict each
    -- other (vague problem statements are resolved by different teams over time).
    max_by(assignment_group, opened_at) AS assignment_group,
    max_by(location, opened_at) AS location,
    max_by(priority_label, opened_at) AS priority_label,
    avg(mttr_hours) AS mttr_hours,
    max_by(kb_reference, opened_at) AS kb_reference,
    count(*) AS occurrences,
    max(opened_at) AS last_seen
  FROM incident_docs
  GROUP BY sha2(lower(embed_text), 256)
) s
ON t.precedent_id = s.precedent_id
-- Only touch rows whose content changed, so syncs don't re-embed unchanged precedents.
WHEN MATCHED AND (
  t.number <> s.number
  OR t.occurrences <> s.occurrences
  OR NOT (t.assignment_group <=> s.assignment_group)
  OR NOT (t.kb_reference <=> s.kb_reference)
) THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
WHEN NOT MATCHED BY SOURCE THEN DELETE;

-- Written by the API when an engineer approves or rejects a knowledge draft made from a
-- resolved ticket. The API's service principal can write here and to triage_feedback only.
CREATE TABLE IF NOT EXISTS kb_drafts (
  draft_id STRING NOT NULL,
  created_at TIMESTAMP,
  decision STRING COMMENT 'approved | rejected',
  action STRING COMMENT 'update (revises target_kb) | new (becomes KBD-<draft_id prefix>)',
  source_number STRING COMMENT 'Resolved incident the draft was written from',
  target_kb STRING,
  title STRING,
  text STRING COMMENT 'Full article markdown, same shape as source articles',
  kb_category STRING,
  category STRING,
  subcategory STRING,
  agent_model STRING,
  decided_by STRING COMMENT 'Signed-in user who made the decision (added 2026-10 with sign-in)'
);

CREATE TABLE IF NOT EXISTS kb_docs (
  number STRING NOT NULL,
  title STRING,
  embed_text STRING,
  text STRING,
  kb_category STRING,
  category STRING,
  subcategory STRING
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

-- Source articles plus approved new drafts, each overlaid with its latest approved revision.
MERGE INTO kb_docs t
USING (
  WITH articles AS (
    SELECT number, title, text, kb_category, category, subcategory
    FROM silver_kb_articles

    UNION ALL

    SELECT concat('KBD-', substr(draft_id, 1, 8)), title, text, kb_category, category, subcategory
    FROM kb_drafts
    WHERE decision = 'approved' AND action = 'new'
  ),
  revisions AS (
    SELECT target_kb, max_by(title, created_at) AS title, max_by(text, created_at) AS text
    FROM kb_drafts
    WHERE decision = 'approved' AND action = 'update'
    GROUP BY target_kb
  )
  SELECT
    a.number,
    coalesce(r.title, a.title) AS title,
    concat_ws('\n', coalesce(r.title, a.title), coalesce(r.text, a.text)) AS embed_text,
    coalesce(r.text, a.text) AS text,
    a.kb_category,
    a.category,
    a.subcategory
  FROM articles a
  LEFT JOIN revisions r ON r.target_kb = a.number
) s
ON t.number = s.number
-- Only changed articles are rewritten, so a sync re-embeds just those.
WHEN MATCHED AND (t.embed_text <> s.embed_text OR NOT (t.kb_category <=> s.kb_category))
  THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
WHEN NOT MATCHED BY SOURCE THEN DELETE;
