---
name: dashboard-compose
description: Deploy the Employee 360 Streamlit dashboard (the committed deployed_app/app/ monolith) as the final step of the demo, once GOLD and both Cortex assistants exist. The app reads the GOLD medallion layer for its 14 tabs and wires the two assistants — Documents (Cortex Search over DOCUMENT_CHUNKS) and Ask Your Data (Cortex Analyst over GOLD.HR_ANALYST). Deploys with snow streamlit deploy (CLI) or src/deploy_app.sql (Workspace / Cortex Code-native, from the git stage), then verifies the dashboard and both assistants answer. This is step ④ — the same for the live-API and offline seeder paths.
tools:
- read_file
- run_shell_command
- ask_user_question
---

# When to Use

- Final step ④ on **either** path: the GOLD layer is built and the two assistants exist
  (`GOLD.HR_ANALYST` + `COMPANY_KB_SEARCH`), and the presenter wants the dashboard live.
- Runs on the user's active connection; for CLI steps use their default connection (`<your-connection>`).
- Keywords: deploy, Streamlit, dashboard, ship it, Employee 360, DASHBOARD_SPS, go live, publish the app.

This skill deploys the **already-committed** `examples/hris_people/deployed_app/app/streamlit_app.py` (a
single-file monolith) — it does not generate or rewrite app code. It is the only example; there is no
templated render step.

# Prerequisites

1. **GOLD is populated.** The 14 tabs read `DEMO_EMPLOYEE_APP.GOLD` (the app's `SCH="GOLD"`,
   `APP_SCH="PUBLIC"`). If GOLD is empty the app loads but charts are blank — finish `medallion-build` first.
2. **Both assistants exist.** `GOLD.HR_ANALYST` (Analyst) and `COMPANY_KB_SEARCH` over `DOCUMENT_CHUNKS`
   (Search), from `cortex-analyst-search`. The chat tables `CHAT_SESSIONS`/`CHAT_MESSAGES` (in PUBLIC, from
   `src/00_setup.sql`) hold per-user chat history.
3. **Cortex granted:** `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE ACCOUNTADMIN;`.
4. The app uses only warehouse-preinstalled packages (streamlit, pandas, altair, snowflake-snowpark-python) —
   see `app/environment.yml`; nothing to install.

# Workflows

**Pick the deploy method via the `ask_user_question` selection popup** (header `Deploy method`) before
deploying — present the two options below; the tool auto-appends a **"Something else"** free-form entry for
anything custom. On a fresh trial account prefer **Option A**; on the existing DEMO account prefer **Option B**
(`--replace` preserves the live URL). If the selection tool is unavailable, ask as a plain-text choice.

## Option A — Workspace / Cortex Code-native (no CLI): `src/deploy_app.sql`

Best when CoCo is driving from a Snowflake Workspace. It creates a Git repository object + `CREATE STREAMLIT`
straight from the repo's `deployed_app/app/` folder (no `PUT`, no local Python):

```sql
-- run as ACCOUNTADMIN; see src/deploy_app.sql
USE DATABASE DEMO_EMPLOYEE_APP; USE SCHEMA PUBLIC;
-- API integration + GIT REPOSITORY CORTEX_REPO + FETCH, then:
CREATE OR REPLACE STREAMLIT DEMO_EMPLOYEE_APP.PUBLIC.DASHBOARD_SPS
  ROOT_LOCATION = '@.../CORTEX_REPO/branches/main/examples/hris_people/deployed_app/app'
  MAIN_FILE = 'streamlit_app.py'
  QUERY_WAREHOUSE = 'DEMO_EMPLOYEE_APP'
  TITLE = 'Employee 360 Dashboard';
```
On a **fresh account** this names the app `DASHBOARD_SPS`. (The existing DEMO account already runs the live
app under an auto-generated id — running this there creates a *second* app; drop the old one first if you
want a single named app.)

## Option B — CLI: `snow streamlit deploy`

From the app folder (it has `snowflake.yml`, which targets the existing app object so the URL is preserved):
```bash
cd examples/hris_people/deployed_app/app
snow streamlit deploy --replace --connection <your-connection>
```
All artifacts in `snowflake.yml` (`streamlit_app.py`, `environment.yml`) are staged together.

## Load the RAG documents (if not already loaded by step ③)

```bash
snow sql -c <conn> --role ACCOUNTADMIN -q \
  "PUT 'file://examples/hris_people/deployed_app/docs/*.md' @DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"
snow sql -c <conn> --role ACCOUNTADMIN -q \
  "ALTER STAGE DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS REFRESH; CALL DEMO_EMPLOYEE_APP.PUBLIC.SP_REBUILD_DOC_CHUNKS();"
```
(In a Workspace, `COPY FILES` the docs from the git stage instead — see the footer of `src/deploy_app.sql`.)

## Verify

- **Dashboard** opens; the per-employee tabs and the two exec dashboards render with current-period data
  (`SELECT MAX(SPENT_DATE) FROM GOLD.TIME_ENTRIES` should reach the current month).
- **Ask Your Data** answers a question (e.g. "headcount by department") via Cortex Analyst.
- **Documents** answers "What is the PTO policy?" with a grounded reply + sources (wait for Search indexing).
- **Chat persists** across a refresh (CHAT_SESSIONS/CHAT_MESSAGES).

See `references/deploy_verify.md` for the ordered commands and the common failure fixes.

# Best Practices

- **Deploy the committed app as-is.** Don't regenerate `streamlit_app.py`; it is the hand-built 14-tab
  monolith reconciled to the live account.
- **One warehouse for the app** (`DEMO_EMPLOYEE_APP`), one for Search + tasks (`DEMO_WH`) — don't introduce
  a third.
- **`--replace`** so a redeploy updates the live object in place (preserves the URL via `snowflake.yml`).
- **Wait for Cortex Search indexing** before judging the Documents tab.
- **Grant `SNOWFLAKE.CORTEX_USER`** — the most common cause of a dead Assistant tab.

# Examples

## Example 1: Finish the demo (DEMO path)

After Gold + both assistants, CoCo runs `src/deploy_app.sql` (Workspace) or
`snow streamlit deploy --replace -c <your-connection>` (CLI), loads `docs/*.md`, opens the app, asks
"headcount by department" (Analyst) and "PTO policy" (Search), and confirms both answer.

## Example 2: Assistant tab empty

CoCo checks (a) `CORTEX_USER` is granted, (b) `SHOW CORTEX SEARCH SERVICES` shows `COMPANY_KB_SEARCH` past
its initial build, (c) `SELECT COUNT(*) FROM PUBLIC.DOCUMENT_CHUNKS` > 0 — fixes whichever is missing.

# References

- `references/deploy_verify.md` — the ordered deploy + verify commands for both options, and fixes for the
  usual failures (empty GOLD, dead Assistant tab, app won't load).
