# Semantic view + document search — skeletons

Generate `build/semantic.sql` and `build/document_search.sql` from these. They mirror the golden
`src/05_semantic_analyst.sql` and `src/01_document_ingestion.sql` so the authored SQL stays compatible with
the committed `app/streamlit_app.py`. Run as `ACCOUNTADMIN` on `sevenpeaks_partner_demo`. Grant first:
`GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE ACCOUNTADMIN;`.

## build/semantic.sql — Cortex Analyst

```sql
USE ROLE ACCOUNTADMIN; USE DATABASE DEMO_EMPLOYEE_APP; USE SCHEMA GOLD;

CREATE OR REPLACE SEMANTIC VIEW GOLD.HR_ANALYST
  TABLES (
    employees AS DEMO_EMPLOYEE_APP.GOLD.EMPLOYEE_360 PRIMARY KEY (EMPLOYEE_ID)
      WITH SYNONYMS=('people','staff','workforce') COMMENT='One row per employee',
    time_entries AS DEMO_EMPLOYEE_APP.GOLD.TIME_ENTRIES PRIMARY KEY (ENTRY_ID)
      WITH SYNONYMS=('timesheets','hours logged'),
    projects AS DEMO_EMPLOYEE_APP.GOLD.PROJECTS PRIMARY KEY (PROJECT_ID)
      WITH SYNONYMS=('engagements'),
    leave_requests AS DEMO_EMPLOYEE_APP.GOLD.LEAVE_REQUESTS PRIMARY KEY (REQUEST_ID)
      WITH SYNONYMS=('time off','pto','absences'),
    candidates AS DEMO_EMPLOYEE_APP.GOLD.CANDIDATES PRIMARY KEY (CANDIDATE_ID)
      WITH SYNONYMS=('applicants','recruiting pipeline')
  )
  RELATIONSHIPS (
    time_to_employee AS time_entries (EMPLOYEE_ID) REFERENCES employees (EMPLOYEE_ID),
    time_to_project  AS time_entries (PROJECT_ID)  REFERENCES projects  (PROJECT_ID),
    leave_to_employee AS leave_requests (EMPLOYEE_ID) REFERENCES employees (EMPLOYEE_ID)
  )
  DIMENSIONS (
    employees.department AS employees.DEPARTMENT WITH SYNONYMS=('dept','division'),
    employees.business_unit AS employees.BUSINESS_UNIT WITH SYNONYMS=('bu'),
    employees.title AS employees.TITLE WITH SYNONYMS=('role','position'),
    employees.status AS employees.STATUS,
    time_entries.spent_date AS time_entries.SPENT_DATE,
    time_entries.is_billable AS time_entries.IS_BILLABLE,
    leave_requests.leave_type AS leave_requests.LEAVE_TYPE,
    candidates.stage AS candidates.STAGE
    -- ... add the dimensions the demo questions need
  )
  METRICS (
    employees.headcount AS COUNT(employees.EMPLOYEE_ID) WITH SYNONYMS=('number of employees','staff count'),
    employees.avg_salary AS AVG(employees.BASE_SALARY) WITH SYNONYMS=('average salary'),
    time_entries.total_hours AS SUM(time_entries.HOURS) WITH SYNONYMS=('hours logged'),
    time_entries.billable_pct AS SUM(IFF(time_entries.IS_BILLABLE, time_entries.HOURS,0))*100.0
       / NULLIF(SUM(time_entries.HOURS),0) WITH SYNONYMS=('utilization','utilisation','billable rate'),
    leave_requests.total_leave_days AS SUM(leave_requests.DAYS) WITH SYNONYMS=('leave taken'),
    candidates.candidate_count AS COUNT(candidates.CANDIDATE_ID) WITH SYNONYMS=('number of candidates')
  )
  COMMENT = 'HR + delivery semantic model (OmniHR + Harvest) for Cortex Analyst over GOLD.';
```

Verify: `SELECT * FROM SEMANTIC_VIEW(GOLD.HR_ANALYST METRICS employees.headcount DIMENSIONS employees.department);`
Lift any dimension/metric you are unsure about straight from `src/05_semantic_analyst.sql` — that set already
answers the demo's "people / time / projects / leave / recruiting" questions.

## build/document_search.sql — Cortex Search RAG

Copy `SP_REBUILD_DOC_CHUNKS`, the stream, the two tasks, and the search service **verbatim from
`src/01_document_ingestion.sql`** — they are content-agnostic. The shape:

```sql
USE ROLE ACCOUNTADMIN; USE SCHEMA DEMO_EMPLOYEE_APP.PUBLIC; USE WAREHOUSE DEMO_WH;

CREATE OR REPLACE PROCEDURE SP_REBUILD_DOC_CHUNKS() RETURNS STRING LANGUAGE SQL AS
$$ BEGIN
  BEGIN TRANSACTION; DELETE FROM DOCUMENT_CHUNKS;
  INSERT INTO DOCUMENT_CHUNKS (FILE_NAME, TITLE, CATEGORY, CHUNK_INDEX, CONTENT)
  WITH parsed AS (SELECT d.RELATIVE_PATH AS FILE_NAME,
      SNOWFLAKE.CORTEX.PARSE_DOCUMENT('@COMPANY_DOCS', d.RELATIVE_PATH, {'mode':'LAYOUT'}):content::STRING AS DOC_TEXT
    FROM DIRECTORY('@COMPANY_DOCS') d),
  meta AS (SELECT FILE_NAME, DOC_TEXT,
      COALESCE(NULLIF(TRIM(REGEXP_SUBSTR(DOC_TEXT,'^# (.+)$',1,1,'em',1)),''),
               INITCAP(REPLACE(REGEXP_REPLACE(FILE_NAME,'[.][^.]*$',''),'-',' '))) AS TITLE,
      COALESCE(NULLIF(TRIM(REGEXP_SUBSTR(DOC_TEXT,'Category:[^A-Za-z]*([A-Za-z][A-Za-z ]*)',1,1,'ie',1)),''),
               'General') AS CATEGORY
    FROM parsed)
  SELECT m.FILE_NAME, m.TITLE, m.CATEGORY, c.INDEX, c.VALUE::STRING
  FROM meta m, LATERAL FLATTEN(input =>
       SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER(m.DOC_TEXT,'markdown',1000,200)) c;
  COMMIT;
  INSERT INTO DOC_INGEST_LOG (RUN_AT, METADATA_ACTION, FILE_NAME)
    SELECT CURRENT_TIMESTAMP(), METADATA$ACTION, RELATIVE_PATH FROM COMPANY_DOCS_STREAM;
  RETURN 'rebuilt'; END $$;

CREATE OR REPLACE STREAM COMPANY_DOCS_STREAM ON STAGE COMPANY_DOCS;
CREATE OR REPLACE TASK DOCS_REFRESH_TASK WAREHOUSE=DEMO_WH SCHEDULE='1 MINUTE' AS ALTER STAGE COMPANY_DOCS REFRESH;
CREATE OR REPLACE TASK DOCS_INGEST_TASK WAREHOUSE=DEMO_WH SCHEDULE='1 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS_STREAM') AS CALL SP_REBUILD_DOC_CHUNKS();
ALTER TASK DOCS_REFRESH_TASK RESUME; ALTER TASK DOCS_INGEST_TASK RESUME;

CREATE OR REPLACE CORTEX SEARCH SERVICE COMPANY_KB_SEARCH
  ON CONTENT ATTRIBUTES TITLE, CATEGORY, FILE_NAME
  WAREHOUSE=DEMO_WH TARGET_LAG='1 minute' EMBEDDING_MODEL='snowflake-arctic-embed-m-v1.5'
  AS SELECT CONTENT, TITLE, CATEGORY, FILE_NAME FROM DEMO_EMPLOYEE_APP.PUBLIC.DOCUMENT_CHUNKS;
```

Then load the docs (`PUT` via CLI, or `COPY FILES` from the git stage in a Workspace),
`ALTER STAGE COMPANY_DOCS REFRESH;`, `CALL SP_REBUILD_DOC_CHUNKS();`. The committed
`src/01_document_ingestion.sql` has the production version with HTML-entity decoding — prefer copying it.
