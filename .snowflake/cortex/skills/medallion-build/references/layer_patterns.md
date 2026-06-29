# Layer patterns — copy-ready SQL skeletons

Generate each `build/<layer>.sql` from these, filling the registry / tables / field-map from
`build/extraction_map.json`. They mirror the golden `src/02_bronze.sql`, `src/03_silver.sql`,
`src/04_gold.sql` so the authored SQL converges on the known-good, dashboard-compatible shape. All run as
`ACCOUNTADMIN` on `sevenpeaks_partner_demo`. Header every file `USE DATABASE DEMO_EMPLOYEE_APP;`.

## build/bronze.sql

```sql
USE ROLE ACCOUNTADMIN; USE DATABASE DEMO_EMPLOYEE_APP; USE WAREHOUSE DEMO_WH;

CREATE SCHEMA IF NOT EXISTS BRONZE;
CREATE SCHEMA IF NOT EXISTS SILVER;
CREATE SCHEMA IF NOT EXISTS GOLD;

-- egress to the tunnel (host is set at run time, after generation)
CREATE NETWORK RULE IF NOT EXISTS BRONZE.OMNI_HARVEST_EGRESS
  MODE = EGRESS TYPE = HOST_PORT VALUE_LIST = ('REPLACE-ME');
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION OMNI_HARVEST_EAI
  ALLOWED_NETWORK_RULES = (BRONZE.OMNI_HARVEST_EGRESS) ENABLED = TRUE;

-- one row per extraction_map.tables[]  (SOURCE, API_PATH, TABLE_NAME)
CREATE OR REPLACE TABLE BRONZE.BRONZE_ENDPOINTS (SOURCE STRING, API_PATH STRING, TABLE_NAME STRING);
INSERT INTO BRONZE.BRONZE_ENDPOINTS VALUES
  ('omnihr','/api/v1/employees','EMPLOYEES'),
  ... ;                         -- emit every endpoint from the map

CREATE TABLE IF NOT EXISTS BRONZE.BRONZE_INGEST_LOG (TABLE_NAME STRING, ROW_COUNT NUMBER, LOADED_AT TIMESTAMP_NTZ);
```

Then the two procs — copy `SP_INGEST_BRONZE` (Python, `EXTERNAL_ACCESS_INTEGRATIONS=(OMNI_HARVEST_EAI)`,
paginated `requests.get` → `parse_json` → `BRONZE.<table>(PAYLOAD VARIANT,_SOURCE,_PATH,_LOADED_AT)`, sends
the `ngrok-skip-browser-warning` header) and `SP_INGEST_ALL_BRONZE(BASE_URL)` (cursor over
`BRONZE_ENDPOINTS`) **verbatim from `src/02_bronze.sql` §3–4** — they are generic over the registry, so no
per-schema edits are needed.

Run-time (after the review hook approves):
```sql
ALTER NETWORK RULE BRONZE.OMNI_HARVEST_EGRESS SET VALUE_LIST = ('<host>');
CALL BRONZE.SP_INGEST_ALL_BRONZE('https://<host>');
```

## build/silver.sql

```sql
USE ROLE ACCOUNTADMIN; USE DATABASE DEMO_EMPLOYEE_APP; USE WAREHOUSE DEMO_WH;
CREATE SCHEMA IF NOT EXISTS SILVER;

-- 1) one typed table per entity (columns + types straight from the map)
CREATE TABLE IF NOT EXISTS SILVER.EMPLOYEES (
  EMPLOYEE_ID NUMBER(38,0) NOT NULL,
  EMAIL VARCHAR(150), TITLE VARCHAR(150), DEPARTMENT VARCHAR(100), ...,
  primary key (EMPLOYEE_ID)
);
-- ... repeat for every table[] in the map

-- 2) field-map: ONLY columns whose json_path != lower(column)  (the nested ones)
CREATE OR REPLACE TABLE SILVER.SILVER_FIELD_MAP (SILVER_TABLE STRING, COLUMN_NAME STRING, JSON_PATH STRING);
INSERT INTO SILVER.SILVER_FIELD_MAP VALUES
  ('EMPLOYEES','EMAIL','work_email'),
  ('EMPLOYEES','TITLE','position.name'),
  ('EMPLOYEES','MANAGER_ID','reporting_manager.id'),
  ('TIME_ENTRIES','EMPLOYEE_ID','user.id'),
  ... ;                         -- every column with col.json_path != lower(col.name)
```

Then copy `SP_FLATTEN(TABLE_NAME)` and `SP_BUILD_SILVER()` **verbatim from `src/03_silver.sql` §3–4**. They
are data-driven: `SP_FLATTEN` reads `INFORMATION_SCHEMA.COLUMNS` LEFT JOIN `SILVER_FIELD_MAP` and emits
`INSERT OVERWRITE … SELECT PAYLOAD:COALESCE(json_path, lower(col))::string AS col …`, skipping empty Bronze —
so they work for any schema with no edits. Run-time: `CALL SILVER.SP_BUILD_SILVER();`.

> Generating the typed `CREATE TABLE`s and the `SILVER_FIELD_MAP` rows from the map is the only
> per-schema work here — exactly the part worth a review session.

## build/gold.sql

```sql
USE ROLE ACCOUNTADMIN; USE DATABASE DEMO_EMPLOYEE_APP;
CREATE SCHEMA IF NOT EXISTS GOLD;

-- entity pass-throughs: one per table the app reads
CREATE OR REPLACE VIEW GOLD.EMPLOYEES AS SELECT * FROM SILVER.EMPLOYEES;
-- ... one per entity ...

-- curated analytics views (names the committed app queries by name)
CREATE OR REPLACE VIEW GOLD.EMPLOYEE_360 AS SELECT e.EMPLOYEE_ID, e.FIRST_NAME, ... ;  -- see src/04_gold.sql
CREATE OR REPLACE VIEW GOLD.HEADCOUNT_BY_DEPARTMENT AS ... ;
CREATE OR REPLACE VIEW GOLD.LEAVE_SUMMARY AS ... ;
```

Keep the **view names identical to `src/04_gold.sql`** (`EMPLOYEE_360`, `HEADCOUNT_BY_DEPARTMENT`,
`LEAVE_SUMMARY`, utilization rollups, …) — `app/streamlit_app.py` selects them by name, and
`cortex-analyst-search` builds the `HR_ANALYST` semantic view on top of them. When unsure what a rollup
should compute, lift it from `src/04_gold.sql`; that is the version the dashboard already renders.
