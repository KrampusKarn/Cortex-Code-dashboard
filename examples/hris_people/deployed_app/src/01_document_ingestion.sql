-- =====================================================================
-- 01_document_ingestion.sql  --  The live RAG chat backend for DASHBOARD_SPS.
--
-- Prereq: run 00_setup.sql first (it creates the COMPANY_DOCS stage and the
-- DOCUMENT_CHUNKS / DOC_INGEST_LOG tables this script populates and indexes).
--
-- Pipeline: users drop company documents (PDF / DOCX / PPTX / TXT / MD) into
-- the COMPANY_DOCS stage. A Stream + Task pair parses them with
-- SNOWFLAKE.CORTEX.PARSE_DOCUMENT, chunks them with
-- SPLIT_TEXT_RECURSIVE_CHARACTER, and lands them in DOCUMENT_CHUNKS, which the
-- COMPANY_KB_SEARCH Cortex Search service indexes. The Streamlit app is
-- unchanged -- it queries COMPANY_KB_SEARCH for CONTENT / TITLE / CATEGORY.
--
-- This is the chat's source of truth. (The earlier curated COMPANY_KNOWLEDGE_BASE
-- table is no longer indexed; it is kept only for lineage.)
-- Owned by ACCOUNTADMIN to match the rest of DEMO_EMPLOYEE_APP.PUBLIC.
-- =====================================================================
USE ROLE ACCOUNTADMIN;
USE SCHEMA DEMO_EMPLOYEE_APP.PUBLIC;
USE WAREHOUSE DEMO_WH;

-- 1) Rebuild procedure: parse every file currently in the stage, chunk it,
--    and replace DOCUMENT_CHUNKS. A full rebuild is trivial at demo scale and
--    handles add / modify / delete uniformly. TITLE comes from the first H1
--    heading (fallback: filename); CATEGORY from a "Category:" line (fallback:
--    General) -- documents can set these with a leading `# Title` and
--    `**Category:** X`.
CREATE OR REPLACE PROCEDURE SP_REBUILD_DOC_CHUNKS()
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    -- Rebuild atomically so a manual CALL and a scheduled task run can never
    -- interleave their DELETE/INSERT and double the rows (one loses on conflict).
    BEGIN TRANSACTION;
    DELETE FROM DOCUMENT_CHUNKS;

    INSERT INTO DOCUMENT_CHUNKS (FILE_NAME, TITLE, CATEGORY, CHUNK_INDEX, CONTENT)
    WITH parsed AS (
        SELECT
            d.RELATIVE_PATH AS FILE_NAME,
            -- PARSE_DOCUMENT (LAYOUT) HTML-escapes ampersands and angle brackets;
            -- decode the common entities so retrieved text and titles read naturally.
            -- CHR(38) is the ampersand, written this way so a literal '&' is never
            -- mistaken for a client-side variable.
            REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                SNOWFLAKE.CORTEX.PARSE_DOCUMENT('@COMPANY_DOCS', d.RELATIVE_PATH, {'mode': 'LAYOUT'}):content::STRING,
                CHR(38)||'amp;', CHR(38)), CHR(38)||'lt;', '<'), CHR(38)||'gt;', '>'),
                CHR(38)||'quot;', '"'), CHR(38)||'#39;', '''') AS DOC_TEXT
        FROM DIRECTORY('@COMPANY_DOCS') d
    ),
    meta AS (
        SELECT
            FILE_NAME,
            DOC_TEXT,
            COALESCE(
                NULLIF(TRIM(REGEXP_SUBSTR(DOC_TEXT, '^# (.+)$', 1, 1, 'em', 1)), ''),
                INITCAP(REPLACE(REGEXP_REPLACE(FILE_NAME, '[.][^.]*$', ''), '-', ' '))
            ) AS TITLE,
            COALESCE(
                NULLIF(TRIM(REGEXP_SUBSTR(DOC_TEXT, 'Category:[^A-Za-z]*([A-Za-z][A-Za-z ]*)', 1, 1, 'ie', 1)), ''),
                'General'
            ) AS CATEGORY
        FROM parsed
    )
    SELECT
        m.FILE_NAME,
        m.TITLE,
        m.CATEGORY,
        c.INDEX AS CHUNK_INDEX,
        c.VALUE::STRING AS CONTENT
    FROM meta m,
         LATERAL FLATTEN(input => SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER(m.DOC_TEXT, 'markdown', 1000, 200)) c;
    COMMIT;

    -- Drain the stream so the ingest task's WHEN gate resets.
    INSERT INTO DOC_INGEST_LOG (RUN_AT, METADATA_ACTION, FILE_NAME)
    SELECT CURRENT_TIMESTAMP(), METADATA$ACTION, RELATIVE_PATH
    FROM COMPANY_DOCS_STREAM;

    RETURN 'DOCUMENT_CHUNKS rebuilt from @COMPANY_DOCS';
END
$$;

-- 2) Stream on the stage's directory table: captures added/changed/removed files.
CREATE OR REPLACE STREAM COMPANY_DOCS_STREAM ON STAGE COMPANY_DOCS;

-- 3) Tasks: one keeps the directory table current, one ingests on change.
--    (Internal-stage directory tables are not event-driven, so a short-interval
--    REFRESH task is the reliable trigger; the ingest task only does work when
--    the stream has data.)
CREATE OR REPLACE TASK DOCS_REFRESH_TASK
    WAREHOUSE = DEMO_WH
    SCHEDULE = '1 MINUTE'
AS
    ALTER STAGE COMPANY_DOCS REFRESH;

CREATE OR REPLACE TASK DOCS_INGEST_TASK
    WAREHOUSE = DEMO_WH
    SCHEDULE = '1 MINUTE'
    WHEN SYSTEM$STREAM_HAS_DATA('DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS_STREAM')
AS
    CALL SP_REBUILD_DOC_CHUNKS();

ALTER TASK DOCS_REFRESH_TASK RESUME;
ALTER TASK DOCS_INGEST_TASK RESUME;

-- 4) Point the chat's Cortex Search service at the document chunks.
--    Same service name + columns (CONTENT/TITLE/CATEGORY) the app already uses,
--    so no app change is needed. TARGET_LAG kept short for a responsive demo.
CREATE OR REPLACE CORTEX SEARCH SERVICE COMPANY_KB_SEARCH
    ON CONTENT
    ATTRIBUTES TITLE, CATEGORY, FILE_NAME
    WAREHOUSE = DEMO_WH
    TARGET_LAG = '1 minute'
    EMBEDDING_MODEL = 'snowflake-arctic-embed-m-v1.5'
    AS SELECT CONTENT, TITLE, CATEGORY, FILE_NAME
       FROM DEMO_EMPLOYEE_APP.PUBLIC.DOCUMENT_CHUNKS;

-- ---------------------------------------------------------------------
-- BOOTSTRAP (run after 00_setup.sql, then upload documents to the stage):
--   snow sql -c <conn> --role ACCOUNTADMIN -q \
--     "PUT 'file://path/to/docs/*.md' @DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"
-- then:
--   ALTER STAGE COMPANY_DOCS REFRESH;
--   CALL SP_REBUILD_DOC_CHUNKS();
-- The repo's ../docs/*.md (pto-policy, health-benefits, upcoming-events) are
-- the documents currently loaded in the live account.
-- Thereafter the tasks pick up new/changed files automatically (~1 min).
-- ---------------------------------------------------------------------
