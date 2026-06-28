# Employee 360 Dashboard - Architecture & Documentation

## Overview

The Employee 360 Dashboard is a comprehensive Streamlit application built on Snowflake that serves as a one-stop executive dashboard for the People Department and Operations team. It integrates data modeled after **OmniHR** (HR — `Omni API v1`) and **Harvest** (Project Delivery), plus a custom RAG-powered Company Knowledge Assistant.

> **OmniHR replaces Freshteam** (which is being shut down) as the HR source — see "Porting to Production" below.

The dashboard reads from the **`DEMO_EMPLOYEE_APP.GOLD`** schema — the curated presentation
layer of the Bronze → Silver → Gold medallion (built by [`src/04_gold.sql`](src/04_gold.sql)):
GOLD exposes a 1:1 entity view per business table (over SILVER, the API-flattened layer) plus the
cross-entity analytics views. App-managed runtime tables (`CHAT_SESSIONS`/`CHAT_MESSAGES`) and the
Cortex Search service stay in `PUBLIC`. The read schema is the single `SCH` constant at the top of
`streamlit_app.py` (`SCH="GOLD"`, `APP_SCH="PUBLIC"`) — exactly the "view schema" indirection in
"Porting to Production" below, so the app can be lifted to prod and re-pointed at real
API-sourced tables by editing those constants.

> **Authoritative structure:** the live tables are defined in [`src/00_setup.sql`](src/00_setup.sql); synthetic data is loaded per source by [`src/seeders/`](src/seeders/) (OmniHR / Harvest). The table inventory below is illustrative and may lag the live schema.

---

## Runtime & Deployment

- **Runtime**: Streamlit on Snowflake
- **Database**: `DEMO_EMPLOYEE_APP` (region `AWS_AP_SOUTH_1`) — app reads `GOLD`; chat + Cortex Search in `PUBLIC`
- **Streamlit App**: `DEMO_EMPLOYEE_APP.PUBLIC.DASHBOARD_SPS`
- **Warehouses (two, by design)**: `DEMO_EMPLOYEE_APP` (app `query_warehouse`) and `DEMO_WH` (Cortex Search + document-ingestion tasks)
- **Source Stage**: `@DEMO_EMPLOYEE_APP.PUBLIC.STREAMLIT_STAGE`

---

## Repository Layout

Four concerns, four folders — **app** (Python/Streamlit), **src** (SQL), **mock_api** (Extract
source), **docs** (RAG corpus):

| Path | Purpose |
|---|---|
| `app/streamlit_app.py` | **The running app (monolith)** — exactly what the Streamlit runtime executes. Edit it directly. |
| `app/environment.yml` | Conda dependencies (Python 3.11, Streamlit, snowflake-snowpark-python, pandas, altair) |
| `app/snowflake.yml` | Redeploy descriptor targeting the existing app object (`DASHBOARD_SPS`) |
| `src/00_setup.sql` | From-scratch infra + all 38 tables |
| `src/01_document_ingestion.sql` | RAG chat backend (`COMPANY_KB_SEARCH` over `DOCUMENT_CHUNKS`) |
| `src/02_bronze.sql` … `05_semantic_analyst.sql` | Bronze→Silver→Gold ELT + the `GOLD.HR_ANALYST` semantic view |
| `src/seeders/` | Per-source synthetic-data seeders (OmniHR / Harvest) |
| `src/migrations/` | One-off schema migrations |
| `mock_api/` | FastAPI replica of the OmniHR + Harvest APIs — the live Extract source |
| `docs/*.md` | The RAG corpus (health benefits, PTO, upcoming events) |
| `README.md`, `ARCHITECTURE.md` | This documentation |

**Edit workflow**: edit `app/streamlit_app.py` directly, then redeploy from `app/` with
`snow streamlit deploy --replace` (it reads `snowflake.yml` and updates the live `DASHBOARD_SPS`
object in place — see the Redeploy section in `README.md`).

---

## Database Schema

Database: `DEMO_EMPLOYEE_APP`, Schema: `PUBLIC`

### HR / Employee Core (OmniHR-aligned)

| Table | Purpose | Rows |
|---|---|---|
| `EMPLOYEES` | Core employee records (with termination, BU/dept/team FKs, OmniHR ID mapping) | 50 |
| `EMPLOYEE_FIELDS` | Extended HR fields (DOB, emergency contact, employment type) | 50 |
| `EMPLOYEE_PII` | Sensitive PII for HR (SSN, passport, visa, bank, insurance, EEO, benefits) | 50 |
| `EMPLOYEE_COMPENSATION_DETAILS` | Salary details, stock options, 401k, PIP status, leave balances | 50 |
| `EMPLOYEE_CERTIFICATIONS` | Professional certifications with expiry tracking | 42 |
| `EMPLOYEES_HISTORY` | Employment change timeline (hires, promotions, transfers, terminations) | 73 |
| `SALARY` | Salary history (effective dates) | 86 |
| `DEPARTMENTS_DETAIL` | Department metadata | 5 |
| `BUSINESS_UNITS` | Top-level org grouping | 3 |
| `SUB_DEPARTMENTS` | Sub-department hierarchy | 11 |
| `TEAMS` | Team-level grouping (FK to BU + Dept + Sub-Dept) | 18 |
| `HEADCOUNT_PLAN` | Planned FTE/Contractor/Managed headcount per month x dept (24 months) | 120 |

### Recruitment (OmniHR-aligned)

| Table | Purpose | Rows |
|---|---|---|
| `CANDIDATES` | Applicants with stage, rating, resume URL | 80 |
| `JOB_POSTINGS` | Open positions with salary bands | 12 |
| `CANDIDATE_SOURCES` | Source lookup (LinkedIn, Indeed, Referral, etc.) | 15 |
| `CANDIDATE_SOURCE_CATEGORIES` | Source category grouping (Job Board / Referral / Agency / Direct / Social) | 5 |
| `ONBOARDING_TASKS` | New hire task tracking | 20 |

### Time & Leave (Harvest + OmniHR-aligned)

| Table | Purpose | Rows |
|---|---|---|
| `TIME_ENTRIES` | Daily time tracking (Harvest v2/time_entries) | ~15,120 |
| `EXPENSE_ENTRIES` | Billable/non-billable expenses | 20 |
| `AVAILABILITY` | Daily availability status | 1,500 |
| `LEAVE_REQUESTS` | PTO/sick/personal leave requests | 153 |
| `UTILIZATION` | Monthly aggregated utilization per employee | 600 |

### Project Delivery (Harvest-aligned)

| Table | Purpose | Rows |
|---|---|---|
| `PROJECTS` | Project master (with hourly_rate, fees, cost_budget, is_billable, budget_by) | 12 |
| `PROJECT_ASSIGNMENTS` | Employee-to-project allocation (with hourly_rate, budget, is_project_manager) | 82 |
| `PROJECT_BUDGETS` | Budget tracking (hours spent/remaining, amount spent/remaining) | 12 |
| `PROJECT_TASKS` | Project-task assignments with rates | 37 |
| `TASKS` | Task master (Development, Design, PM, etc.) | 15 |
| `CLIENTS` | Client master | 8 |
| `HARVEST_USERS` | Harvest user records (mapped to EMPLOYEES, with default_hourly_rate, cost_rate, weekly_capacity) | 50 |
| `USER_ASSIGNMENTS` | Harvest user assignments (rates, PM flags, budget) | 82 |
| `INVOICES` | Client invoices | 14 |
| `INVOICE_LINE_ITEMS` | Invoice line detail | 14 |
| `ESTIMATES` | Estimate/proposal tracking | 10 |

### RAG Knowledge Base

| Table | Purpose | Rows |
|---|---|---|
| `COMPANY_KNOWLEDGE_BASE` | Source content for RAG (Company Info, Benefits, Events - Internal/External) | 30 |

### Chat Persistence

| Table | Purpose | Rows |
|---|---|---|
| `CHAT_SESSIONS` | Per-user chat sessions (user can create/switch between chats) | variable |
| `CHAT_MESSAGES` | Chat messages per session (persisted across browser refreshes) | variable |

---

## Cortex Search Service

**Service**: `DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_KB_SEARCH`

- Embeddings model: `snowflake-arctic-embed-m-v1.5`
- Indexed column: `CONTENT`
- Attributes: `TITLE`, `CATEGORY`, `FILE_NAME`
- Source: `DOCUMENT_CHUNKS` (parsed/chunked from documents dropped in the `COMPANY_DOCS` stage — see [`src/01_document_ingestion.sql`](src/01_document_ingestion.sql)).
- Target lag: 1 minute

Used by the RAG Company Knowledge Assistant in the Overview tab to retrieve top-K relevant documents, then grounded into an answer via `SNOWFLAKE.CORTEX.COMPLETE(mistral-large2, ...)`.

---

## Stored procedures

The backend comes entirely from `src/`: [`00_setup.sql`](src/00_setup.sql) (tables),
[`01_document_ingestion.sql`](src/01_document_ingestion.sql) (the chat backend), the `02`→`05`
medallion, and [`src/seeders/`](src/seeders/) (synthetic data). The app is the single committed
`app/streamlit_app.py` monolith, deployed with `snow streamlit deploy` or
[`src/deploy_app.sql`](src/deploy_app.sql). The one stored procedure the running app depends on is
`SP_REBUILD_DOC_CHUNKS` (document ingestion).

---

## Two Cortex assistants

The dashboard ships **two** natural-language assistants, one per Cortex capability:

| Assistant | Tab | Cortex feature | Grounded on |
|---|---|---|---|
| **Company Knowledge** (documents) | Overview | Cortex **Search** → `COMPLETE` (RAG) | `DOCUMENT_CHUNKS` via `COMPANY_KB_SEARCH` (unstructured docs) |
| **Ask Your Data** (analytics) | 💬 Ask Your Data | Cortex **Analyst** | `GOLD.HR_ANALYST` semantic view (structured GOLD layer) |

"Ask Your Data" sends the question to `/api/v2/cortex/analyst/message` with
`semantic_view = DEMO_EMPLOYEE_APP.GOLD.HR_ANALYST`, then runs the SQL Analyst returns and
renders the table/chart. The semantic model (dimensions, metrics, relationships, synonyms over
people / time / projects / leave / recruiting) is built by [`src/05_semantic_analyst.sql`](src/05_semantic_analyst.sql).

## Dashboard Tabs (14 total)

### Per-Employee Tabs (1-5) - select an employee in sidebar

1. **Overview** - Profile card, key metrics, **RAG Company Knowledge Assistant** (persistent chat with session history)
2. **Utilization & Time** - Utilization trend, weekly billable/non-billable hours, hours by project
3. **Bench & Staffing** - Bench list (<30% allocation), who is on which project, Harvest user assignments with rates
4. **Projects** - Assignments, budget burn progress, rates & margin breakdown
5. **Compensation** - Salary history, equity/401k, leave balances, PIP, expenses

### Organization Tabs

- **Recruitment** - Pipeline funnel, candidates by source/category, open positions
- **Leave** - Leave balances, team calendar, leave by type (reads `GOLD.LEAVE_SUMMARY`)
- **People & HR** - PII profile, visa alerts, benefits, demographics, event planning info
- **Skills & Certs** - Certifications matrix, expiring certs, skills search for staffing
- **PIP Tracker** - Employees on a Performance Improvement Plan / flagged for review (OmniHR comp data)
- **Directory** - Searchable directory, employment-history timeline, org-hierarchy tree (reads `GOLD.EMPLOYEE_360`)

### Executive Dashboards (13-14) - with multi-select filters + cross-filter charts

13. **People Dashboard**
    - Workforce card (EOM Headcount, FTE, Contractor, M-Workforce)
    - Headcount by Department (click bars to filter)
    - Actual vs Planned Headcount trend
    - Joiners vs Leavers chart
    - Attrition - FTE (Quarterly)
    - Internal Training % of Total Hours
    - **Filters**: Multi-select BU, Multi-select Department, Year

14. **Performance Dashboard**
    - Utilization cards (MTD/YTD Gross/Net/Availability)
    - This Month Revenue (MTD Harvest + Projected + Avg Revenue Per Hour)
    - Bench (Total count, Availability hours, Bench Value)
    - Revenue by Department (click bars to filter)
    - Monthly & Weekly Utilization multi-line charts with Target Gross line
    - **Filters**: Multi-select BU, Multi-select Department, Year

### Interactive Features (Tabs 13-14)

- **Multi-select** for BU and Department filters
- **Cross-filtering** via Altair `selection_point` - click chart bars to push selection into the department multi-select
- **Clear Filters** button to reset
- **Verification caption** shows matched employee/project counts so you can visually confirm filter scope

---

## Porting to Production (OmniHR / Harvest)

### Strategy: View Layer Indirection

Instead of rewriting Streamlit queries, create a schema with **views** that map our logical table names to your real production tables:

```sql
CREATE OR REPLACE VIEW PROD_DASHBOARD.EMPLOYEES AS
SELECT 
    system_id              AS EMPLOYEE_ID,
    first_name             AS FIRST_NAME,
    last_name              AS LAST_NAME,
    work_email             AS EMAIL,
    department             AS DEPARTMENT,
    position               AS TITLE,
    hired_date             AS HIRE_DATE,
    reporting_manager_id   AS MANAGER_ID,
    employment_status      AS STATUS,
    ...
FROM OMNIHR.OMNIHR_EMPLOYEES;   -- OmniHR GET /employee/ landed via Fivetran/custom ingestion
```

Then point the dashboard code (change the `DB`/`SCH` constants at the top of `streamlit_app.py`) to the view schema.

### Suggested Logical-to-Production Mapping

| Dashboard Table | Production Source |
|---|---|
| `EMPLOYEES`, `EMPLOYEE_FIELDS`, `EMPLOYEE_PII` | OmniHR `GET /employee/` (+ `/employee/{id}/bank-information/`, `/id-information/`) split into 3 views |
| `EMPLOYEES_HISTORY` | OmniHR `GET /employee/{id}/job/` (Job_Serializer `event_reason` events) |
| `DEPARTMENTS_DETAIL` | OmniHR `GET /organization/departments/` |
| `SUB_DEPARTMENTS` | OmniHR `GET /organization/departments/` (sub-department records) |
| `BUSINESS_UNITS` | OmniHR `GET /organization/departments/` (top-level grouping) |
| `TEAMS` | OmniHR `GET /organization/teams/` |
| `CANDIDATES` | OmniHR `GET /employee/ats/candidates/` (external ATS: Breezy / Manatal / TeamTailor / Zoho) |
| `JOB_POSTINGS` | OmniHR `GET /organization/positions/` + `GET /employee/ats/pending-hires/` |
| `CANDIDATE_SOURCES`, `CANDIDATE_SOURCE_CATEGORIES` | OmniHR ATS integration sources (Breezy / Go Hire / Manatal / TeamTailor / Zoho / Candily) |
| `ONBOARDING_TASKS` | OmniHR `GET /onboarding/{user_id}/task/` |
| `EMPLOYEE_COMPENSATION_DETAILS`, `SALARY` | OmniHR `GET /employee/{id}/compensation/` (+ `/base-salary/`) |
| `PROJECTS`, `PROJECT_ASSIGNMENTS`, `PROJECT_TASKS`, `PROJECT_BUDGETS` | Harvest `/v2/projects`, `/v2/user_assignments`, `/v2/task_assignments` |
| `TASKS` | Harvest `/v2/tasks` |
| `CLIENTS` | Harvest `/v2/clients` |
| `TIME_ENTRIES` | Harvest `/v2/time_entries` |
| `EXPENSE_ENTRIES` | Harvest `/v2/expenses` |
| `INVOICES`, `INVOICE_LINE_ITEMS` | Harvest `/v2/invoices` + line items + Xero invoices |
| `ESTIMATES` | Harvest `/v2/estimates` |
| `HARVEST_USERS`, `USER_ASSIGNMENTS` | Harvest `/v2/users`, `/v2/user_assignments` |
| `UTILIZATION` | Harvest `/v2/reports/time` aggregated monthly |
| `COMPANY_KNOWLEDGE_BASE` | Keep as-is or source from internal wiki/Confluence export |
| `LEAVE_REQUESTS` | OmniHR `GET /time-off/1.0/time-off-requests/` |
| `HEADCOUNT_PLAN` | Internal planning table (populate from HR plan) |

### Porting Steps

1. Create a new schema in prod, e.g. `EMPLOYEE_360_PROD.PUBLIC`
2. Create views (as above) mapping real production tables to the logical table names the app expects
3. Update the `DB`/`SCH` constants at the top of `streamlit_app.py` to point at the view schema, then `snow streamlit deploy --replace`
4. Create the `COMPANY_KB_SEARCH` Cortex Search service on your real knowledge-base content (or keep the document-ingestion pipeline in `src/01_document_ingestion.sql`)
5. Create the `CHAT_SESSIONS` and `CHAT_MESSAGES` tables for chat persistence (in `src/00_setup.sql`)
6. Grant access to the Streamlit app to target users

---

## Key Design Decisions

1. **Single-file app** - the live `app/streamlit_app.py` is a self-contained monolith; edit it directly and redeploy via `snowflake.yml`.
2. **Warehouse-friendly packages** - uses only pre-installed packages (streamlit, pandas, altair, snowflake-snowpark-python) for maximum portability
3. **Persistent chat storage** - RAG chat survives browser refresh and is scoped per `CURRENT_USER()` with multi-session support
4. **Cross-filter UX** - charts use Altair `selection_point` with Streamlit `on_select="rerun"` and a `pending_*` session_state pattern to sync chart clicks --> multiselect widgets
5. **Filter verification caption** - every dashboard shows matched entity counts so users can confirm filter scope visually
6. **Interpretation A filtering** - YTD/MTD metrics respect Department/BU filters; only the time window is fixed (standard BI convention)

---

## Support / Troubleshooting

- **App not loading?** Check container status: `SHOW COMPUTE POOLS;`. Pool auto-suspends after 5 min - first load after suspension takes ~30-60s.
- **"Invalid expression in VALUES clause"** - Snowflake does not allow subqueries in `VALUES(...)`. Use `INSERT INTO ... SELECT` instead.
- **Altair `Selections are activated but no selections defined`** - Add `alt.selection_point()` with `.add_params()` to the chart.
- **Chart click not updating multi-select** - Use the `pending_*` session_state pattern (set `st.session_state["pending_key"] = value` BEFORE the widget is rendered).
- **Dashboard metrics empty** - Check time-period data. Current date vs data date range: `SELECT MAX(SPENT_DATE) FROM TIME_ENTRIES`.

---

*Reconciled to the live `DEMO_EMPLOYEE_APP` account and the OmniHR HR source. Authoritative structure: [`src/00_setup.sql`](src/00_setup.sql).*
