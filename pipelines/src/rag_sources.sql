-- Source tables for Vector Search delta-sync indexes. MERGE (not CREATE OR REPLACE) keeps the
-- change data feed continuous so index syncs stay incremental.
USE CATALOG workspace;
USE SCHEMA incident_copilot;

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
  assignment_group STRING COMMENT 'Team that most often resolved it',
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
    mode(assignment_group) AS assignment_group,
    max_by(location, opened_at) AS location,
    max_by(priority_label, opened_at) AS priority_label,
    avg(mttr_hours) AS mttr_hours,
    mode(kb_reference) AS kb_reference,
    count(*) AS occurrences,
    max(opened_at) AS last_seen
  FROM incident_docs
  GROUP BY sha2(lower(embed_text), 256)
) s
ON t.precedent_id = s.precedent_id
-- Only touch rows whose content changed, so syncs don't re-embed unchanged precedents.
WHEN MATCHED AND (t.number <> s.number OR t.occurrences <> s.occurrences) THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
WHEN NOT MATCHED BY SOURCE THEN DELETE;

CREATE TABLE IF NOT EXISTS kb_docs (
  number STRING NOT NULL,
  title STRING,
  embed_text STRING,
  text STRING,
  kb_category STRING,
  category STRING,
  subcategory STRING
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

MERGE INTO kb_docs t
USING (
  SELECT number, title, concat_ws('\n', title, text) AS embed_text, text, kb_category, category, subcategory
  FROM silver_kb_articles
) s
ON t.number = s.number
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
WHEN NOT MATCHED BY SOURCE THEN DELETE;
