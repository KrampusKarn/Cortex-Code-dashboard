-- =====================================================================
-- 2026-06_drop_superseded_public_tables.sql
--
-- One-time cleanup of DEMO_EMPLOYEE_APP.PUBLIC after the dashboard was repointed
-- to the GOLD medallion layer (GOLD ← SILVER). The 35 business data tables that
-- used to live in PUBLIC are now stale duplicates of the SILVER tables the
-- medallion builds from the API — nothing reads them anymore — so they are dropped.
-- Also drops the no-longer-indexed COMPANY_KNOWLEDGE_BASE and the leftover load /
-- artifact stages (DEMO_SEED_STAGE, TABLE_DATA, STREAMLIT_STAGE) that the current
-- deploy no longer uses.
--
-- DESTRUCTIVE. Run as ACCOUNTADMIN, only on an account that still has the old
-- PUBLIC data tables. KEPT in PUBLIC (NOT dropped): the app + assistants
-- infrastructure — CHAT_SESSIONS, CHAT_MESSAGES, DOCUMENT_CHUNKS, DOC_INGEST_LOG,
-- COMPANY_DOCS (stage/stream/tasks), SP_REBUILD_DOC_CHUNKS, COMPANY_KB_SEARCH,
-- and the Streamlit app.
--
-- Fresh builds already come up clean: 00_setup.sql now creates only the PUBLIC
-- app/RAG layer (SILVER owns the entity DDL, seed_bronze.sh loads BRONZE). This
-- migration only converges an account that was built before that slim.
-- =====================================================================
USE ROLE ACCOUNTADMIN;
USE DATABASE DEMO_EMPLOYEE_APP;
USE SCHEMA PUBLIC;

-- ── Superseded business data tables (now owned by SILVER) ────────────
DROP TABLE IF EXISTS PUBLIC.AVAILABILITY;
DROP TABLE IF EXISTS PUBLIC.BUSINESS_UNITS;
DROP TABLE IF EXISTS PUBLIC.CANDIDATES;
DROP TABLE IF EXISTS PUBLIC.CANDIDATE_SOURCES;
DROP TABLE IF EXISTS PUBLIC.CANDIDATE_SOURCE_CATEGORIES;
DROP TABLE IF EXISTS PUBLIC.CLIENTS;
DROP TABLE IF EXISTS PUBLIC.DEPARTMENTS_DETAIL;
DROP TABLE IF EXISTS PUBLIC.EMPLOYEES;
DROP TABLE IF EXISTS PUBLIC.EMPLOYEES_HISTORY;
DROP TABLE IF EXISTS PUBLIC.EMPLOYEE_CERTIFICATIONS;
DROP TABLE IF EXISTS PUBLIC.EMPLOYEE_COMPENSATION_DETAILS;
DROP TABLE IF EXISTS PUBLIC.EMPLOYEE_FIELDS;
DROP TABLE IF EXISTS PUBLIC.EMPLOYEE_NOTES;          -- retired performance/notes table
DROP TABLE IF EXISTS PUBLIC.EMPLOYEE_PII;
DROP TABLE IF EXISTS PUBLIC.ESTIMATES;
DROP TABLE IF EXISTS PUBLIC.EXPENSE_ENTRIES;
DROP TABLE IF EXISTS PUBLIC.HARVEST_USERS;
DROP TABLE IF EXISTS PUBLIC.HEADCOUNT_PLAN;
DROP TABLE IF EXISTS PUBLIC.INVOICES;
DROP TABLE IF EXISTS PUBLIC.INVOICE_LINE_ITEMS;
DROP TABLE IF EXISTS PUBLIC.JOB_POSTINGS;
DROP TABLE IF EXISTS PUBLIC.LEAVE_REQUESTS;
DROP TABLE IF EXISTS PUBLIC.ONBOARDING_TASKS;
DROP TABLE IF EXISTS PUBLIC.PERFORMANCE_REVIEWS;     -- retired performance/notes table
DROP TABLE IF EXISTS PUBLIC.PROJECTS;
DROP TABLE IF EXISTS PUBLIC.PROJECT_ASSIGNMENTS;
DROP TABLE IF EXISTS PUBLIC.PROJECT_BUDGETS;
DROP TABLE IF EXISTS PUBLIC.PROJECT_TASKS;
DROP TABLE IF EXISTS PUBLIC.SALARY;
DROP TABLE IF EXISTS PUBLIC.SUB_DEPARTMENTS;
DROP TABLE IF EXISTS PUBLIC.TASKS;
DROP TABLE IF EXISTS PUBLIC.TEAMS;
DROP TABLE IF EXISTS PUBLIC.TIME_ENTRIES;
DROP TABLE IF EXISTS PUBLIC.USER_ASSIGNMENTS;
DROP TABLE IF EXISTS PUBLIC.UTILIZATION;

-- ── Old curated KB table (no longer indexed; Search uses DOCUMENT_CHUNKS) ──
DROP TABLE IF EXISTS PUBLIC.COMPANY_KNOWLEDGE_BASE;

-- ── Leftover stages the current deploy no longer uses ────────────────
DROP STAGE IF EXISTS PUBLIC.DEMO_SEED_STAGE;   -- old PUT-based CSV seeding
DROP STAGE IF EXISTS PUBLIC.TABLE_DATA;        -- old data dump
DROP STAGE IF EXISTS PUBLIC.STREAMLIT_STAGE;   -- old app-artifact stage (deploy now uses the git stage / snow CLI)

-- =====================================================================
-- VERIFY (PUBLIC should now hold only app + assistants objects):
--   SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='PUBLIC';
--   -> CHAT_SESSIONS, CHAT_MESSAGES, DOCUMENT_CHUNKS, DOC_INGEST_LOG
-- =====================================================================
