-- =====================================================================
-- 02_bronze.sql  --  BRONZE layer + live API ingestion (External Access)
--
-- The "Extract + Load" of the medallion (BRONZE -> SILVER -> GOLD schemas). Pulls
-- raw JSON from the mock OmniHR + Harvest API (../mock_api/) into BRONZE.* VARIANT
-- tables. ADDITIVE: creates the BRONZE/SILVER/GOLD schemas + Bronze objects only.
--
-- PREREQUISITES (the mock API must be reachable over HTTPS):
--   Easiest: cd ../mock_api && ./serve_eai.sh start   (boots the API + tunnel, points the
--     network rule, and prints the ingest CALLs). ngrok static domain => stable URL forever;
--     cloudflare quick tunnel => new URL each run (the script re-points the rule for you).
--   Manual: run the API + a tunnel yourself, set the HOST in the ALTER below, run this file,
--     then CALL BRONZE.SP_INGEST_ALL_BRONZE('https://<your-tunnel-host>');
--
-- Run as ACCOUNTADMIN (External Access Integration + owner's rights).
-- =====================================================================
USE ROLE ACCOUNTADMIN;
USE DATABASE DEMO_EMPLOYEE_APP;
USE WAREHOUSE DEMO_WH;

-- 0) Medallion schemas -------------------------------------------------
CREATE SCHEMA IF NOT EXISTS BRONZE;   -- raw VARIANT landing
CREATE SCHEMA IF NOT EXISTS SILVER;   -- typed/cleaned tables
CREATE SCHEMA IF NOT EXISTS GOLD;     -- business views

-- 1) Egress allow-list -------------------------------------------------
--    EDIT the host below to your tunnel host (host only). When the tunnel URL
--    changes, just re-run this one ALTER — the integration follows it.
CREATE NETWORK RULE IF NOT EXISTS BRONZE.OMNI_HARVEST_EGRESS
  MODE = EGRESS TYPE = HOST_PORT
  VALUE_LIST = ('REPLACE-ME.trycloudflare.com')
  COMMENT = 'Egress to the mock OmniHR+Harvest API tunnel';
ALTER NETWORK RULE BRONZE.OMNI_HARVEST_EGRESS SET VALUE_LIST = ('REPLACE-ME.trycloudflare.com');

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION OMNI_HARVEST_EAI
  ALLOWED_NETWORK_RULES = (BRONZE.OMNI_HARVEST_EGRESS)
  ENABLED = TRUE
  COMMENT = 'Lets Snowflake call the mock OmniHR+Harvest API for Bronze ingestion';

-- 2) Endpoint registry (drives ingestion + Silver flatten) -------------
--    SOURCE | API_PATH | TABLE_NAME (the BRONZE.* and SILVER.* table name)
CREATE OR REPLACE TABLE BRONZE.BRONZE_ENDPOINTS (SOURCE STRING, API_PATH STRING, TABLE_NAME STRING);
INSERT INTO BRONZE.BRONZE_ENDPOINTS (SOURCE, API_PATH, TABLE_NAME) VALUES
  ('omnihr','/api/v1/organization/business-units','BUSINESS_UNITS'),
  ('omnihr','/api/v1/organization/departments','DEPARTMENTS_DETAIL'),
  ('omnihr','/api/v1/organization/sub-departments','SUB_DEPARTMENTS'),
  ('omnihr','/api/v1/organization/teams','TEAMS'),
  ('omnihr','/api/v1/employees','EMPLOYEES'),
  ('omnihr','/api/v1/employee-fields','EMPLOYEE_FIELDS'),
  ('omnihr','/api/v1/employee-pii','EMPLOYEE_PII'),
  ('omnihr','/api/v1/employee-compensation','EMPLOYEE_COMPENSATION_DETAILS'),
  ('omnihr','/api/v1/employee-certifications','EMPLOYEE_CERTIFICATIONS'),
  ('omnihr','/api/v1/compensation/salary','SALARY'),
  ('omnihr','/api/v1/employee-history','EMPLOYEES_HISTORY'),
  ('omnihr','/api/v1/organization/headcount-plan','HEADCOUNT_PLAN'),
  ('omnihr','/api/v1/ats/source-categories','CANDIDATE_SOURCE_CATEGORIES'),
  ('omnihr','/api/v1/ats/sources','CANDIDATE_SOURCES'),
  ('omnihr','/api/v1/ats/jobs','JOB_POSTINGS'),
  ('omnihr','/api/v1/ats/candidates','CANDIDATES'),
  ('omnihr','/api/v1/onboarding/tasks','ONBOARDING_TASKS'),
  ('omnihr','/api/v1/time-off/requests','LEAVE_REQUESTS'),
  ('harvest','/v2/clients','CLIENTS'),
  ('harvest','/v2/projects','PROJECTS'),
  ('harvest','/v2/tasks','TASKS'),
  ('harvest','/v2/users','HARVEST_USERS'),
  ('harvest','/v2/project_assignments','PROJECT_ASSIGNMENTS'),
  ('harvest','/v2/reports/project_budget','PROJECT_BUDGETS'),
  ('harvest','/v2/task_assignments','PROJECT_TASKS'),
  ('harvest','/v2/user_assignments','USER_ASSIGNMENTS'),
  ('harvest','/v2/time_entries','TIME_ENTRIES'),
  ('harvest','/v2/expenses','EXPENSE_ENTRIES'),
  ('harvest','/v2/availability','AVAILABILITY'),
  ('harvest','/v2/reports/uninvoiced','UTILIZATION'),
  ('harvest','/v2/invoices','INVOICES'),
  ('harvest','/v2/invoice_line_items','INVOICE_LINE_ITEMS'),
  ('harvest','/v2/estimates','ESTIMATES');

CREATE TABLE IF NOT EXISTS BRONZE.BRONZE_INGEST_LOG (
  TABLE_NAME STRING, ROW_COUNT NUMBER, LOADED_AT TIMESTAMP_NTZ);

-- 3) Generic ingest proc: pull one paginated endpoint -> BRONZE.<table> -------
CREATE OR REPLACE PROCEDURE BRONZE.SP_INGEST_BRONZE(BASE_URL STRING, API_PATH STRING, TABLE_NAME STRING, SRC STRING)
  RETURNS STRING
  LANGUAGE PYTHON RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python','requests')
  EXTERNAL_ACCESS_INTEGRATIONS = (OMNI_HARVEST_EAI)
  HANDLER = 'run'
AS
$$
import json
import requests
from snowflake.snowpark.functions import parse_json, col, lit, current_timestamp

def run(session, base_url, api_path, table_name, src):
    base = base_url.rstrip('/')
    target = f"DEMO_EMPLOYEE_APP.BRONZE.{table_name}"
    # non-browser UA + skip header so ngrok's free-tier interstitial never replaces the JSON
    headers = {'ngrok-skip-browser-warning': 'true', 'User-Agent': 'snowflake-bronze-ingest'}
    rows, page = [], 1
    while True:
        resp = requests.get(base + api_path, headers=headers,
                            params={'page': page, 'page_size': 500, 'per_page': 500}, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, dict):
            batch = body.get('results')
            if batch is None:
                batch = next((v for v in body.values() if isinstance(v, list)), [])
            has_next = bool(body.get('next') or body.get('next_page'))
        else:
            batch, has_next = body, False
        rows.extend(batch or [])
        if not batch or not has_next:
            break
        page += 1
    session.sql(f"CREATE TABLE IF NOT EXISTS {target} "
                f"(PAYLOAD VARIANT, _SOURCE STRING, _PATH STRING, _LOADED_AT TIMESTAMP_NTZ)").collect()
    session.sql(f"TRUNCATE TABLE {target}").collect()
    if rows:
        df = session.create_dataframe([[json.dumps(r)] for r in rows], schema=['S'])
        df.select(parse_json(col('S')).alias('PAYLOAD'), lit(src).alias('_SOURCE'),
                  lit(api_path).alias('_PATH'), current_timestamp().alias('_LOADED_AT')) \
          .write.mode('append').save_as_table(['DEMO_EMPLOYEE_APP', 'BRONZE', table_name])
    session.sql(f"INSERT INTO DEMO_EMPLOYEE_APP.BRONZE.BRONZE_INGEST_LOG (TABLE_NAME, ROW_COUNT, LOADED_AT) "
                f"SELECT '{table_name}', {len(rows)}, CURRENT_TIMESTAMP()").collect()
    return f"{table_name}: {len(rows)} rows"
$$;

-- 4) Driver: ingest every registered endpoint --------------------------
CREATE OR REPLACE PROCEDURE BRONZE.SP_INGEST_ALL_BRONZE(BASE_URL STRING)
  RETURNS STRING LANGUAGE SQL
AS
$$
DECLARE
  n INT DEFAULT 0;
  c CURSOR FOR SELECT SOURCE, API_PATH, TABLE_NAME FROM DEMO_EMPLOYEE_APP.BRONZE.BRONZE_ENDPOINTS;
BEGIN
  TRUNCATE TABLE IF EXISTS DEMO_EMPLOYEE_APP.BRONZE.BRONZE_INGEST_LOG;
  FOR r IN c DO
    LET p STRING := r.API_PATH;
    LET tn STRING := r.TABLE_NAME;
    LET s STRING := r.SOURCE;
    CALL DEMO_EMPLOYEE_APP.BRONZE.SP_INGEST_BRONZE(:BASE_URL, :p, :tn, :s);
    n := n + 1;
  END FOR;
  RETURN 'ingested ' || n || ' endpoints; see BRONZE.BRONZE_INGEST_LOG';
END;
$$;

-- =====================================================================
-- RUN (after the API is up + tunnel host set):
--   ALTER NETWORK RULE BRONZE.OMNI_HARVEST_EGRESS SET VALUE_LIST = ('abc123.trycloudflare.com');
--   CALL BRONZE.SP_INGEST_ALL_BRONZE('https://abc123.trycloudflare.com');
--   -- single-endpoint smoke test:
--   CALL BRONZE.SP_INGEST_BRONZE('https://abc123.trycloudflare.com','/api/v1/employees','EMPLOYEES','omnihr');
-- VERIFY:
--   SELECT * FROM BRONZE.BRONZE_INGEST_LOG ORDER BY ROW_COUNT DESC;
--   SELECT PAYLOAD FROM BRONZE.EMPLOYEES LIMIT 1;       -- raw nested JSON
-- =====================================================================
