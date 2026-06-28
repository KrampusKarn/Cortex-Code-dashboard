-- =====================================================================
-- 04_gold.sql  --  GOLD layer: the curated presentation layer the dashboard reads
--
-- GOLD is the SINGLE schema the Streamlit app (DASHBOARD_SPS) reads from. It has
-- two kinds of views, both ADDITIVE (only GOLD.* views — nothing is dropped):
--   1. Entity pass-throughs  — GOLD.<ENTITY> = SELECT * FROM SILVER.<ENTITY>, one
--      per business table the dashboard needs. This is what lets the app flip its
--      read schema from PUBLIC to GOLD with a one-line change and have every tab
--      resolve against the medallion output.
--   2. Curated analytics views — headcount, utilization, profitability, … the
--      cross-entity rollups (and the basis for the Cortex Analyst semantic view —
--      see the note at the bottom).
--
-- OmniHR + Harvest entities come from SILVER (flattened from the API via Bronze).
--
-- Run as ACCOUNTADMIN (after SILVER is built, or the SILVER-backed views return 0
-- rows until then).
-- =====================================================================
USE ROLE ACCOUNTADMIN;
USE DATABASE DEMO_EMPLOYEE_APP;
CREATE SCHEMA IF NOT EXISTS GOLD;

-- ── Entity pass-throughs (24 from SILVER) ────────────────────────────
-- 1:1 over the typed SILVER tables so GOLD is a complete read surface for the app.
CREATE OR REPLACE VIEW GOLD.EMPLOYEES                     AS SELECT * FROM SILVER.EMPLOYEES;
CREATE OR REPLACE VIEW GOLD.EMPLOYEE_FIELDS              AS SELECT * FROM SILVER.EMPLOYEE_FIELDS;
CREATE OR REPLACE VIEW GOLD.EMPLOYEE_PII                 AS SELECT * FROM SILVER.EMPLOYEE_PII;
CREATE OR REPLACE VIEW GOLD.EMPLOYEE_COMPENSATION_DETAILS AS SELECT * FROM SILVER.EMPLOYEE_COMPENSATION_DETAILS;
CREATE OR REPLACE VIEW GOLD.EMPLOYEE_CERTIFICATIONS      AS SELECT * FROM SILVER.EMPLOYEE_CERTIFICATIONS;
CREATE OR REPLACE VIEW GOLD.SALARY                       AS SELECT * FROM SILVER.SALARY;
CREATE OR REPLACE VIEW GOLD.EMPLOYEES_HISTORY            AS SELECT * FROM SILVER.EMPLOYEES_HISTORY;
CREATE OR REPLACE VIEW GOLD.BUSINESS_UNITS               AS SELECT * FROM SILVER.BUSINESS_UNITS;
CREATE OR REPLACE VIEW GOLD.DEPARTMENTS_DETAIL           AS SELECT * FROM SILVER.DEPARTMENTS_DETAIL;
CREATE OR REPLACE VIEW GOLD.SUB_DEPARTMENTS              AS SELECT * FROM SILVER.SUB_DEPARTMENTS;
CREATE OR REPLACE VIEW GOLD.TEAMS                        AS SELECT * FROM SILVER.TEAMS;
CREATE OR REPLACE VIEW GOLD.HEADCOUNT_PLAN               AS SELECT * FROM SILVER.HEADCOUNT_PLAN;
CREATE OR REPLACE VIEW GOLD.CANDIDATES                   AS SELECT * FROM SILVER.CANDIDATES;
CREATE OR REPLACE VIEW GOLD.JOB_POSTINGS                 AS SELECT * FROM SILVER.JOB_POSTINGS;
CREATE OR REPLACE VIEW GOLD.LEAVE_REQUESTS               AS SELECT * FROM SILVER.LEAVE_REQUESTS;
CREATE OR REPLACE VIEW GOLD.PROJECTS                     AS SELECT * FROM SILVER.PROJECTS;
CREATE OR REPLACE VIEW GOLD.TASKS                        AS SELECT * FROM SILVER.TASKS;
CREATE OR REPLACE VIEW GOLD.PROJECT_ASSIGNMENTS          AS SELECT * FROM SILVER.PROJECT_ASSIGNMENTS;
CREATE OR REPLACE VIEW GOLD.PROJECT_BUDGETS              AS SELECT * FROM SILVER.PROJECT_BUDGETS;
CREATE OR REPLACE VIEW GOLD.HARVEST_USERS                AS SELECT * FROM SILVER.HARVEST_USERS;
CREATE OR REPLACE VIEW GOLD.USER_ASSIGNMENTS             AS SELECT * FROM SILVER.USER_ASSIGNMENTS;
CREATE OR REPLACE VIEW GOLD.TIME_ENTRIES                 AS SELECT * FROM SILVER.TIME_ENTRIES;
CREATE OR REPLACE VIEW GOLD.EXPENSE_ENTRIES              AS SELECT * FROM SILVER.EXPENSE_ENTRIES;
CREATE OR REPLACE VIEW GOLD.UTILIZATION                  AS SELECT * FROM SILVER.UTILIZATION;

-- ── Curated analytics views ──────────────────────────────────────────
-- Cross-entity rollups. The app can read these directly; they are also the basis
-- for the Cortex Analyst semantic view (05).

-- Employee 360 — THE canonical employee dimension the app reads (sidebar, exec
-- dashboards, org tree). One row per employee with org rollup, manager, comp, tenure,
-- plus the raw FK/lifecycle columns the dashboards filter on (BUSINESS_UNIT_ID,
-- TERMINATION_DATE, EMPLOYMENT_TYPE) so charts join this view instead of raw tables.
CREATE OR REPLACE VIEW GOLD.EMPLOYEE_360 AS
SELECT
  e.EMPLOYEE_ID, e.FIRST_NAME, e.LAST_NAME, e.EMAIL, e.TITLE,
  e.DEPARTMENT, bu.NAME AS BUSINESS_UNIT, sd.NAME AS SUB_DEPARTMENT, t.NAME AS TEAM,
  e.LOCATION, e.STATUS, e.HIRE_DATE, e.TERMINATION_DATE,
  DATEDIFF('month', e.HIRE_DATE, CURRENT_DATE()) AS TENURE_MONTHS,
  e.BUSINESS_UNIT_ID, e.SUB_DEPT_ID, e.TEAM_ID,
  ef.EMPLOYMENT_TYPE,
  e.MANAGER_ID, mgr.FIRST_NAME || ' ' || mgr.LAST_NAME AS MANAGER_NAME,
  ecd.ANNUAL_LEAVE_BALANCE, ecd.NEXT_REVIEW_DATE, ecd.PIP_STATUS,
  sal.BASE_SALARY
FROM SILVER.EMPLOYEES e
LEFT JOIN SILVER.BUSINESS_UNITS bu       ON e.BUSINESS_UNIT_ID = bu.BU_ID
LEFT JOIN SILVER.SUB_DEPARTMENTS sd      ON e.SUB_DEPT_ID = sd.SUB_DEPT_ID
LEFT JOIN SILVER.TEAMS t                 ON e.TEAM_ID = t.TEAM_ID
LEFT JOIN SILVER.EMPLOYEE_FIELDS ef      ON e.EMPLOYEE_ID = ef.EMPLOYEE_ID
LEFT JOIN SILVER.EMPLOYEES mgr           ON e.MANAGER_ID = mgr.EMPLOYEE_ID
LEFT JOIN SILVER.EMPLOYEE_COMPENSATION_DETAILS ecd ON e.EMPLOYEE_ID = ecd.EMPLOYEE_ID
LEFT JOIN (SELECT EMPLOYEE_ID, MAX_BY(BASE_SALARY, EFFECTIVE_DATE) AS BASE_SALARY
           FROM SILVER.SALARY GROUP BY EMPLOYEE_ID) sal ON e.EMPLOYEE_ID = sal.EMPLOYEE_ID;

-- Headcount by department + status.
CREATE OR REPLACE VIEW GOLD.HEADCOUNT_BY_DEPARTMENT AS
SELECT
  DEPARTMENT,
  COUNT(*)                       AS HEADCOUNT,
  COUNT_IF(STATUS = 'Active')    AS ACTIVE,
  COUNT_IF(STATUS = 'On Leave')  AS ON_LEAVE,
  COUNT_IF(STATUS = 'Left')      AS DEPARTED
FROM SILVER.EMPLOYEES
GROUP BY DEPARTMENT;

-- Recruitment funnel — candidates by job + stage.
CREATE OR REPLACE VIEW GOLD.RECRUITMENT_FUNNEL AS
SELECT
  j.TITLE AS JOB_TITLE, j.DEPARTMENT, j.STATUS AS JOB_STATUS,
  c.STAGE, COUNT(*) AS CANDIDATES, AVG(c.RATING) AS AVG_RATING
FROM SILVER.CANDIDATES c
LEFT JOIN SILVER.JOB_POSTINGS j ON c.JOB_ID = j.JOB_ID
GROUP BY j.TITLE, j.DEPARTMENT, j.STATUS, c.STAGE;

-- Monthly utilization — billable vs total hours per employee.
CREATE OR REPLACE VIEW GOLD.UTILIZATION_MONTHLY AS
SELECT
  te.EMPLOYEE_ID,
  e.FIRST_NAME || ' ' || e.LAST_NAME AS EMPLOYEE,
  DATE_TRUNC('month', te.SPENT_DATE) AS MONTH,
  SUM(te.HOURS)                                  AS TOTAL_HOURS,
  SUM(IFF(te.IS_BILLABLE, te.HOURS, 0))          AS BILLABLE_HOURS,
  ROUND(100 * SUM(IFF(te.IS_BILLABLE, te.HOURS, 0)) / NULLIF(SUM(te.HOURS), 0), 1) AS BILLABLE_PCT
FROM SILVER.TIME_ENTRIES te
LEFT JOIN SILVER.EMPLOYEES e ON te.EMPLOYEE_ID = e.EMPLOYEE_ID
GROUP BY te.EMPLOYEE_ID, EMPLOYEE, DATE_TRUNC('month', te.SPENT_DATE);

-- Project profitability — budget vs logged hours vs billable value.
CREATE OR REPLACE VIEW GOLD.PROJECT_PROFITABILITY AS
SELECT
  p.PROJECT_ID, p.PROJECT_NAME, cl.NAME AS CLIENT, p.STATUS,
  p.BUDGET, p.FEES, p.COST_BUDGET,
  COALESCE(SUM(te.HOURS), 0)                         AS HOURS_LOGGED,
  COALESCE(SUM(IFF(te.IS_BILLABLE, te.HOURS, 0)), 0) * MAX(p.HOURLY_RATE) AS BILLABLE_VALUE
FROM SILVER.PROJECTS p
LEFT JOIN SILVER.CLIENTS cl     ON p.CLIENT_ID = cl.CLIENT_ID
LEFT JOIN SILVER.TIME_ENTRIES te ON te.PROJECT_ID = p.PROJECT_ID
GROUP BY p.PROJECT_ID, p.PROJECT_NAME, cl.NAME, p.STATUS, p.BUDGET, p.FEES, p.COST_BUDGET;

-- Leave summary — requests + days by type and status.
CREATE OR REPLACE VIEW GOLD.LEAVE_SUMMARY AS
SELECT LEAVE_TYPE, STATUS, COUNT(*) AS REQUESTS, SUM(DAYS) AS TOTAL_DAYS
FROM SILVER.LEAVE_REQUESTS
GROUP BY LEAVE_TYPE, STATUS;

-- =====================================================================
-- VERIFY:
--   SELECT * FROM GOLD.EMPLOYEE_360 LIMIT 10;
--   SELECT * FROM GOLD.HEADCOUNT_BY_DEPARTMENT ORDER BY HEADCOUNT DESC;
--
-- NEXT (the "talk to your data" tab) — Cortex Analyst reads a SEMANTIC VIEW over
-- these GOLD views/SILVER tables (dimensions + metrics + relationships), built in a
-- later step (05_semantic_analyst.sql). The Search tab stays on DOCUMENT_CHUNKS / 01.
-- =====================================================================
