-- =====================================================================
-- 05_semantic_analyst.sql  --  Cortex Analyst semantic model over GOLD
--
-- Builds GOLD.HR_ANALYST, a native Snowflake SEMANTIC VIEW that powers the
-- dashboard's "Ask Your Data" tab (Cortex Analyst — natural-language → SQL).
-- The Search tab keeps using Cortex Search over DOCUMENT_CHUNKS (01); this is the
-- structured "talk to your data" half.
--
-- It models the GOLD layer (OmniHR + Harvest) as business entities:
--   employees (dimension)  ←  time_entries / leave_requests (facts)
--   projects  (dimension)  ←  time_entries
--   candidates (recruiting, standalone)
-- with dimensions, metrics, relationships and synonyms so Analyst maps plain
-- English ("billable % by department", "headcount by BU", "leave days by type")
-- onto the right joins/aggregations.
--
-- Run as ACCOUNTADMIN after 04_gold.sql. ADDITIVE: only creates GOLD.HR_ANALYST.
-- =====================================================================
USE ROLE ACCOUNTADMIN;
USE DATABASE DEMO_EMPLOYEE_APP;
USE SCHEMA GOLD;

CREATE OR REPLACE SEMANTIC VIEW GOLD.HR_ANALYST

  TABLES (
    employees AS DEMO_EMPLOYEE_APP.GOLD.EMPLOYEE_360
      PRIMARY KEY (EMPLOYEE_ID)
      WITH SYNONYMS = ('people','staff','workforce','employee')
      COMMENT = 'One row per employee with org rollup, manager, comp and tenure',
    time_entries AS DEMO_EMPLOYEE_APP.GOLD.TIME_ENTRIES
      PRIMARY KEY (ENTRY_ID)
      WITH SYNONYMS = ('time logs','timesheets','hours logged')
      COMMENT = 'Hours logged per employee, project and day',
    projects AS DEMO_EMPLOYEE_APP.GOLD.PROJECTS
      PRIMARY KEY (PROJECT_ID)
      WITH SYNONYMS = ('engagements','client projects')
      COMMENT = 'Delivery projects with budget and billing',
    leave_requests AS DEMO_EMPLOYEE_APP.GOLD.LEAVE_REQUESTS
      PRIMARY KEY (REQUEST_ID)
      WITH SYNONYMS = ('time off','pto','absences','leave')
      COMMENT = 'Employee leave / time-off requests',
    candidates AS DEMO_EMPLOYEE_APP.GOLD.CANDIDATES
      PRIMARY KEY (CANDIDATE_ID)
      WITH SYNONYMS = ('applicants','recruits','recruiting pipeline')
      COMMENT = 'Recruitment pipeline candidates'
  )

  RELATIONSHIPS (
    time_to_employee AS time_entries (EMPLOYEE_ID) REFERENCES employees (EMPLOYEE_ID),
    time_to_project  AS time_entries (PROJECT_ID)  REFERENCES projects  (PROJECT_ID),
    leave_to_employee AS leave_requests (EMPLOYEE_ID) REFERENCES employees (EMPLOYEE_ID)
  )

  DIMENSIONS (
    employees.employee_name AS employees.FIRST_NAME || ' ' || employees.LAST_NAME
      WITH SYNONYMS = ('name','full name'),
    employees.department AS employees.DEPARTMENT WITH SYNONYMS = ('dept','division'),
    employees.business_unit AS employees.BUSINESS_UNIT WITH SYNONYMS = ('bu','unit'),
    employees.team AS employees.TEAM,
    employees.title AS employees.TITLE WITH SYNONYMS = ('role','position','job title'),
    employees.location AS employees.LOCATION WITH SYNONYMS = ('office','city'),
    employees.status AS employees.STATUS WITH SYNONYMS = ('employment status'),
    employees.employment_type AS employees.EMPLOYMENT_TYPE WITH SYNONYMS = ('worker type','fte or contractor'),
    employees.manager_name AS employees.MANAGER_NAME WITH SYNONYMS = ('manager','reports to'),
    employees.hire_date AS employees.HIRE_DATE WITH SYNONYMS = ('start date','joined date'),
    employees.termination_date AS employees.TERMINATION_DATE WITH SYNONYMS = ('exit date','left date'),
    employees.tenure_months AS employees.TENURE_MONTHS WITH SYNONYMS = ('tenure'),
    projects.project_name AS projects.PROJECT_NAME WITH SYNONYMS = ('project'),
    projects.client AS projects.CLIENT WITH SYNONYMS = ('customer','account'),
    projects.project_status AS projects.STATUS,
    time_entries.spent_date AS time_entries.SPENT_DATE WITH SYNONYMS = ('work date','logged date'),
    time_entries.is_billable AS time_entries.IS_BILLABLE WITH SYNONYMS = ('billable flag'),
    leave_requests.leave_type AS leave_requests.LEAVE_TYPE WITH SYNONYMS = ('absence type','time off type'),
    leave_requests.leave_status AS leave_requests.STATUS,
    candidates.stage AS candidates.STAGE WITH SYNONYMS = ('pipeline stage'),
    candidates.source AS candidates.SOURCE WITH SYNONYMS = ('sourcing channel'),
    candidates.candidate_status AS candidates.STATUS
  )

  METRICS (
    employees.headcount AS COUNT(employees.EMPLOYEE_ID)
      WITH SYNONYMS = ('number of employees','total employees','staff count','headcount')
      COMMENT = 'Number of employees',
    employees.avg_salary AS AVG(employees.BASE_SALARY)
      WITH SYNONYMS = ('average salary','mean salary'),
    employees.total_salary AS SUM(employees.BASE_SALARY)
      WITH SYNONYMS = ('total payroll','salary cost'),
    employees.avg_tenure_months AS AVG(employees.TENURE_MONTHS)
      WITH SYNONYMS = ('average tenure'),
    employees.avg_leave_balance AS AVG(employees.ANNUAL_LEAVE_BALANCE)
      WITH SYNONYMS = ('average leave balance'),
    time_entries.total_hours AS SUM(time_entries.HOURS)
      WITH SYNONYMS = ('hours logged','logged hours','total hours'),
    time_entries.billable_hours AS SUM(IFF(time_entries.IS_BILLABLE, time_entries.HOURS, 0))
      WITH SYNONYMS = ('billable time','billable hours'),
    time_entries.billable_pct AS SUM(IFF(time_entries.IS_BILLABLE, time_entries.HOURS, 0)) * 100.0 / NULLIF(SUM(time_entries.HOURS), 0)
      WITH SYNONYMS = ('utilization','utilisation','billable percentage','billable rate')
      COMMENT = 'Billable hours as a percent of total logged hours',
    leave_requests.total_leave_days AS SUM(leave_requests.DAYS)
      WITH SYNONYMS = ('days off','leave taken','total leave days'),
    leave_requests.leave_request_count AS COUNT(leave_requests.REQUEST_ID)
      WITH SYNONYMS = ('number of leave requests'),
    candidates.candidate_count AS COUNT(candidates.CANDIDATE_ID)
      WITH SYNONYMS = ('number of candidates','applicant count'),
    candidates.avg_candidate_rating AS AVG(candidates.RATING)
      WITH SYNONYMS = ('average candidate rating')
  )

  COMMENT = 'HR + delivery semantic model (OmniHR + Harvest) for Cortex Analyst: people, time/utilization, projects, leave and recruiting over the GOLD layer.';

-- =====================================================================
-- VERIFY (semantic views are directly queryable via the SEMANTIC_VIEW table fn):
--   SELECT * FROM SEMANTIC_VIEW(
--     GOLD.HR_ANALYST METRICS employees.headcount DIMENSIONS employees.department)
--   ORDER BY headcount DESC;
--
--   SELECT * FROM SEMANTIC_VIEW(
--     GOLD.HR_ANALYST METRICS time_entries.billable_pct DIMENSIONS employees.business_unit);
--
-- The dashboard's "Ask Your Data" tab passes {"semantic_view":"DEMO_EMPLOYEE_APP.GOLD.HR_ANALYST"}
-- to /api/v2/cortex/analyst/message and runs the SQL Cortex Analyst returns.
-- =====================================================================
