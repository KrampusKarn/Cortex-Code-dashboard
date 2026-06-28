-- =====================================================================
-- reset_for_coco.sql  --  Stage the DEMO account for a Cortex Code (CoCo) rebuild
--
-- Trial accounts can't use External Access Integration, so the live API-extraction
-- demo runs on the DEMO account (sevenpeaks_partner_demo / DEMO_EMPLOYEE_APP), which
-- already has everything built. This clears ONLY the medallion so CoCo can rebuild
-- Bronze -> Silver -> Gold (+ the HR_ANALYST semantic view) from empty, while leaving
-- PUBLIC (the app, chat tables, Cortex Search, docs) and the warehouses intact.
--
-- Run as ACCOUNTADMIN, ONCE, right before the demo. DESTRUCTIVE (drops the medallion).
-- After this, drive CoCo through src/:
--   02_bronze.sql  -> set the network rule to your ngrok host -> CALL SP_INGEST_ALL_BRONZE
--   03_silver.sql  -> CALL SP_BUILD_SILVER
--   04_gold.sql    -> 05_semantic_analyst.sql
-- The existing dashboard (reads GOLD) lights up again once GOLD is rebuilt; the
-- Documents assistant (Cortex Search in PUBLIC) keeps working throughout.
-- =====================================================================
USE ROLE ACCOUNTADMIN;
USE DATABASE DEMO_EMPLOYEE_APP;

-- Drop the integration FIRST so the BRONZE network rule it references drops cleanly.
-- (02_bronze.sql recreates both the rule and the integration.)
DROP EXTERNAL ACCESS INTEGRATION IF EXISTS OMNI_HARVEST_EAI;

-- Drop the medallion: tables, views, procs, the network rule, and HR_ANALYST.
DROP SCHEMA IF EXISTS DEMO_EMPLOYEE_APP.GOLD;
DROP SCHEMA IF EXISTS DEMO_EMPLOYEE_APP.SILVER;
DROP SCHEMA IF EXISTS DEMO_EMPLOYEE_APP.BRONZE;

-- KEPT: PUBLIC (DASHBOARD_SPS, CHAT_SESSIONS/CHAT_MESSAGES, DOCUMENT_CHUNKS,
-- COMPANY_KB_SEARCH, COMPANY_DOCS + SP_REBUILD_DOC_CHUNKS) and the two warehouses.

-- ── Lighter alternative (no schema drop — "watch the data refill") ────
-- Skip the drops above; instead TRUNCATE only the entity tables (NOT the config
-- tables BRONZE.BRONZE_ENDPOINTS / SILVER.SILVER_FIELD_MAP), then have CoCo run just
-- the two ingest CALLs. Objects + app stay; only the data reflows.

-- ── Optional: let CoCo re-create the Streamlit app too ───────────────
-- The live app is auto-named (YFE09SNXUSHHL2EH); deploy_app.sql creates one named
-- DASHBOARD_SPS. To avoid two apps, drop the existing one first, then have CoCo run
-- deploy_app.sql:
--   DROP STREAMLIT IF EXISTS DEMO_EMPLOYEE_APP.PUBLIC.YFE09SNXUSHHL2EH;
-- =====================================================================
