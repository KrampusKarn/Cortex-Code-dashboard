-- =====================================================================
-- 00_setup.sql  --  PUBLIC app + RAG layer for the DASHBOARD_SPS app
-- (Employee 360 / DEMO_EMPLOYEE_APP.PUBLIC).
--
-- Creates ONLY what PUBLIC owns: warehouses, database, schema, the COMPANY_DOCS
-- stage, and the chat + document tables. Idempotent (IF NOT EXISTS), so re-running
-- never drops data.
--
-- The business ENTITY data does NOT live in PUBLIC — it lives in the medallion
-- (BRONZE -> SILVER -> GOLD). SILVER owns the entity DDL (03_silver.sql) and the
-- dashboard reads GOLD, so this file creates none of it.
--
-- Run order:  00_setup.sql -> fill Bronze (02_bronze.sql + ingest, OR
--   seeders/seed_bronze.sh) -> 03_silver.sql -> CALL SP_BUILD_SILVER ->
--   04_gold.sql -> 05_semantic_analyst.sql -> 01_document_ingestion.sql ->
--   deploy the Streamlit app (see ../app/snowflake.yml / ../README.md).
--
-- Two warehouses, by design (matches the live account):
--   DEMO_EMPLOYEE_APP  -- the Streamlit app's query_warehouse
--   DEMO_WH            -- the Cortex Search service + ingestion tasks
-- Objects are owned by ACCOUNTADMIN in the live account (the app runs with
-- owner's rights and must write the chat tables), so create them as such.
-- =====================================================================
USE ROLE ACCOUNTADMIN;

-- 1) Warehouses ------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS DEMO_EMPLOYEE_APP
    WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 300 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Query warehouse for the DASHBOARD_SPS Streamlit app';
CREATE WAREHOUSE IF NOT EXISTS DEMO_WH
    WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Cortex Search service + document-ingestion tasks';

-- 2) Database + schema ----------------------------------------------
CREATE DATABASE IF NOT EXISTS DEMO_EMPLOYEE_APP
    COMMENT = 'Employee 360 / DASHBOARD_SPS demo (synthetic data)';
CREATE SCHEMA IF NOT EXISTS DEMO_EMPLOYEE_APP.PUBLIC;
USE SCHEMA DEMO_EMPLOYEE_APP.PUBLIC;
USE WAREHOUSE DEMO_WH;

-- 3) Stage -----------------------------------------------------------
-- COMPANY_DOCS needs SSE so CORTEX.PARSE_DOCUMENT can read it (used by 01).
CREATE STAGE IF NOT EXISTS COMPANY_DOCS
    DIRECTORY = (ENABLE = TRUE)
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    COMMENT = 'Drop company docs here; parsed + chunked + indexed by Cortex Search (see 01_document_ingestion.sql)';

-- 4) App + RAG tables (PUBLIC owns only these four) -----------------
--    CHAT_SESSIONS / CHAT_MESSAGES   : per-user chat persistence (app writes at runtime)
--    DOCUMENT_CHUNKS / DOC_INGEST_LOG: populated by 01_document_ingestion.sql
CREATE TABLE IF NOT EXISTS CHAT_MESSAGES (
	MESSAGE_ID NUMBER(38,0) NOT NULL autoincrement start 1 increment 1 noorder,
	SESSION_ID NUMBER(38,0),
	USERNAME VARCHAR(150),
	ROLE VARCHAR(20),
	CONTENT VARCHAR(16777216),
	SOURCES VARCHAR(16777216),
	CREATED_AT TIMESTAMP_NTZ(9) DEFAULT CURRENT_TIMESTAMP(),
	primary key (MESSAGE_ID)
);
CREATE TABLE IF NOT EXISTS CHAT_SESSIONS (
	SESSION_ID NUMBER(38,0) NOT NULL autoincrement start 1 increment 1 noorder,
	USERNAME VARCHAR(150),
	SESSION_NAME VARCHAR(200),
	CREATED_AT TIMESTAMP_NTZ(9) DEFAULT CURRENT_TIMESTAMP(),
	LAST_ACTIVE TIMESTAMP_NTZ(9) DEFAULT CURRENT_TIMESTAMP(),
	primary key (SESSION_ID)
);
CREATE TABLE IF NOT EXISTS DOCUMENT_CHUNKS (
	CHUNK_ID NUMBER(38,0) NOT NULL autoincrement start 1 increment 1 noorder,
	FILE_NAME VARCHAR(16777216),
	TITLE VARCHAR(16777216),
	CATEGORY VARCHAR(16777216),
	CHUNK_INDEX NUMBER(38,0),
	CONTENT VARCHAR(16777216),
	INGESTED_AT TIMESTAMP_NTZ(9) DEFAULT CURRENT_TIMESTAMP(),
	primary key (CHUNK_ID)
);
CREATE TABLE IF NOT EXISTS DOC_INGEST_LOG (
	RUN_AT TIMESTAMP_NTZ(9) DEFAULT CURRENT_TIMESTAMP(),
	METADATA_ACTION VARCHAR(16777216),
	FILE_NAME VARCHAR(16777216)
);

-- 5) Sanity check ----------------------------------------------------
-- PUBLIC should hold ONLY these four tables + the COMPANY_DOCS stage here;
-- 01_document_ingestion.sql then adds the stream, tasks, SP_REBUILD_DOC_CHUNKS,
-- and the COMPANY_KB_SEARCH service. Entity data lives in BRONZE/SILVER/GOLD.
SHOW TABLES IN SCHEMA DEMO_EMPLOYEE_APP.PUBLIC;
