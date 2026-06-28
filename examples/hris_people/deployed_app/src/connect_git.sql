-- =====================================================================
-- connect_git.sql  --  Wire Snowflake to the public GitHub repo
--
-- Creates the Git repository OBJECT (API integration + git repository + fetch) so
-- Snowflake can read the repo as a stage. Used by:
--   • deploy_app.sql   — CREATE STREAMLIT from the repo's app/ folder
--   • the docs load     — COPY FILES from .../docs into @COMPANY_DOCS
-- PUBLIC repo => no credentials needed.
--
-- Run as ACCOUNTADMIN. Idempotent (CREATE OR REPLACE). Re-run the ALTER … FETCH
-- anytime to pull the latest commit.
--
-- NOTE — this is the Git repository *object*, not a Snowsight *Workspace*. The
-- Workspace (the editing surface where Cortex Code runs) is created once in the
-- browser: Snowsight → Projects → Workspaces → From Git repository → paste the
-- repo URL. There is no SQL/CLI to create the Workspace itself.
--
-- (deploy_app.sql contains these same two CREATEs inline so it stays self-contained;
--  keep the owner/repo/branch here in sync with it if you fork or rename.)
-- =====================================================================
USE ROLE ACCOUNTADMIN;
USE DATABASE DEMO_EMPLOYEE_APP;
USE SCHEMA PUBLIC;

-- 1) Git API integration (PUBLIC repo => no secret / GIT_CREDENTIALS) ----
CREATE OR REPLACE API INTEGRATION GIT_API_INTEGRATION
  API_PROVIDER = GIT_HTTPS_API
  API_ALLOWED_PREFIXES = ('<your github repo url>')
  ENABLED = TRUE
  COMMENT = 'Read-only access to the public Cortex Dashboard Kit repo';

-- 2) Git repository object + pull the latest commit --------------------
CREATE OR REPLACE GIT REPOSITORY DEMO_EMPLOYEE_APP.PUBLIC.CORTEX_REPO
  API_INTEGRATION = GIT_API_INTEGRATION
  ORIGIN = '<your github repo url>';

ALTER GIT REPOSITORY DEMO_EMPLOYEE_APP.PUBLIC.CORTEX_REPO FETCH;

-- VERIFY — Snowflake can now see the repo's branches + files:
SHOW GIT BRANCHES IN DEMO_EMPLOYEE_APP.PUBLIC.CORTEX_REPO;
LS @DEMO_EMPLOYEE_APP.PUBLIC.CORTEX_REPO/branches/main/examples/hris_people/deployed_app/app;
-- =====================================================================
