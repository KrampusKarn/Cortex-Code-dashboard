-- =====================================================================
-- deploy_app.sql  --  Workspace / Cortex Code-native deploy of DASHBOARD_SPS
--
-- Creates the Employee 360 Streamlit app from the repo's `deployed_app/app/` folder
-- WITHOUT the `snow` CLI — so Cortex Code (in a Snowflake Workspace) can build the
-- dashboard from a prompt as the final step of the demo. The app is the single
-- `streamlit_app.py` monolith (the MAIN_FILE); it plus `environment.yml` are served
-- straight from the git stage.
--
-- PREREQUISITES (build the data + AI layers first, or the app loads empty/errors):
--   02_bronze.sql → 03_silver.sql → ingest (SP_INGEST_ALL_BRONZE + SP_BUILD_SILVER)
--   → 04_gold.sql → 05_semantic_analyst.sql → 01_document_ingestion.sql
--
-- Points at the PUBLIC repo KrampusKarn/Cortex-Code-dashboard @ main (no credentials).
-- If you fork/rename, update the owner/repo/branch in the three string literals below.
--
-- Run as ACCOUNTADMIN. Idempotent (CREATE OR REPLACE / IF NOT EXISTS).
-- NOTE: names the app `DASHBOARD_SPS` directly — intended for a FRESH account (the
-- from-scratch CoCo build). The existing DEMO account already has the live app under
-- an auto-generated name, so running this there creates a *second* app.
-- =====================================================================
USE ROLE ACCOUNTADMIN;
USE DATABASE DEMO_EMPLOYEE_APP;
USE SCHEMA PUBLIC;

-- 1) Git API integration (PUBLIC repo => no secret / GIT_CREDENTIALS) ---
CREATE OR REPLACE API INTEGRATION GIT_API_INTEGRATION
  API_PROVIDER = GIT_HTTPS_API
  API_ALLOWED_PREFIXES = ('https://github.com/KrampusKarn')
  ENABLED = TRUE
  COMMENT = 'Read-only access to the public Cortex Dashboard Kit repo for app deploy';

-- 2) Git repository object + fetch the latest commit --------------------
CREATE OR REPLACE GIT REPOSITORY DEMO_EMPLOYEE_APP.PUBLIC.CORTEX_REPO
  API_INTEGRATION = GIT_API_INTEGRATION
  ORIGIN = 'https://github.com/KrampusKarn/Cortex-Code-dashboard.git';

ALTER GIT REPOSITORY DEMO_EMPLOYEE_APP.PUBLIC.CORTEX_REPO FETCH;

-- 3) Create the Streamlit straight from the repo folder -----------------
--    ROOT_LOCATION serves the app folder (streamlit_app.py + environment.yml);
--    MAIN_FILE is the monolith.
CREATE OR REPLACE STREAMLIT DEMO_EMPLOYEE_APP.PUBLIC.DASHBOARD_SPS
  ROOT_LOCATION = '@DEMO_EMPLOYEE_APP.PUBLIC.CORTEX_REPO/branches/main/examples/hris_people/deployed_app/app'
  MAIN_FILE = 'streamlit_app.py'
  QUERY_WAREHOUSE = 'DEMO_EMPLOYEE_APP'
  TITLE = 'Employee 360 Dashboard'
  COMMENT = 'Employee 360 — reads GOLD; Documents (Cortex Search) + Ask Your Data (Cortex Analyst)';

-- =====================================================================
-- VERIFY:
--   SHOW STREAMLITS IN SCHEMA DEMO_EMPLOYEE_APP.PUBLIC;   -- DASHBOARD_SPS present
--   -- then open it from Snowsight → Projects → Streamlit
--
-- RE-DEPLOY after pushing app changes: re-run the FETCH + CREATE OR REPLACE STREAMLIT
--   (FETCH pulls the new commit; the Streamlit picks up the refreshed files).
--
-- RELATED — load the RAG docs from the git stage (the other PUT the CLI used to do).
-- Run after 01_document_ingestion.sql created @COMPANY_DOCS + SP_REBUILD_DOC_CHUNKS:
--   COPY FILES INTO @DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS
--     FROM '@DEMO_EMPLOYEE_APP.PUBLIC.CORTEX_REPO/branches/main/examples/hris_people/deployed_app/docs/';
--   ALTER STAGE DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS REFRESH;
--   CALL DEMO_EMPLOYEE_APP.PUBLIC.SP_REBUILD_DOC_CHUNKS();
-- =====================================================================
