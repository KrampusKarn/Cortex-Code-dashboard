# Deploy + verify — ordered commands and fixes

The app is `examples/hris_people/deployed_app/app/streamlit_app.py` (committed monolith). It reads
`DEMO_EMPLOYEE_APP.GOLD` and wires the two assistants. Deploy it last, after GOLD + the assistants exist.

## Deploy

**Workspace (no CLI)** — run `src/deploy_app.sql` as `ACCOUNTADMIN`: it creates the `GIT_API_INTEGRATION`,
the `CORTEX_REPO` git repository object, `FETCH`es, and `CREATE OR REPLACE STREAMLIT … DASHBOARD_SPS` from
`@CORTEX_REPO/branches/main/examples/hris_people/deployed_app/app`. Then `COPY FILES` the docs from the git
stage (footer of `deploy_app.sql`), `ALTER STAGE COMPANY_DOCS REFRESH`, `CALL SP_REBUILD_DOC_CHUNKS()`.

**CLI** —
```bash
cd examples/hris_people/deployed_app/app
snow streamlit deploy --replace --connection <your-connection>
# load docs — PREFERRED: server-side COPY FILES from the git stage (no local transfer, no OAuth prompt):
snow sql -c <conn> --role ACCOUNTADMIN -q \
  "COPY FILES INTO @DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS FROM '@DEMO_EMPLOYEE_APP.PUBLIC.CORTEX_REPO/branches/main/examples/hris_people/deployed_app/docs/';"
# FALLBACK (local upload) — `snow sql PUT` may hang on a browser OAuth flow even with key-pair auth; prefer COPY FILES:
#   snow sql -c <conn> --role ACCOUNTADMIN -q \
#     "PUT 'file://../docs/*.md' @DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"
snow sql -c <conn> --role ACCOUNTADMIN -q \
  "ALTER STAGE DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS REFRESH; CALL DEMO_EMPLOYEE_APP.PUBLIC.SP_REBUILD_DOC_CHUNKS();"
```

## Verify

```sql
SHOW STREAMLITS IN SCHEMA DEMO_EMPLOYEE_APP.PUBLIC;          -- the app object is present
SELECT MAX(SPENT_DATE) FROM DEMO_EMPLOYEE_APP.GOLD.TIME_ENTRIES;   -- reaches the current month
SELECT COUNT(*) FROM DEMO_EMPLOYEE_APP.PUBLIC.DOCUMENT_CHUNKS;     -- > 0
SHOW CORTEX SEARCH SERVICES IN SCHEMA DEMO_EMPLOYEE_APP.PUBLIC;    -- COMPANY_KB_SEARCH, build finished
SELECT * FROM SEMANTIC_VIEW(GOLD.HR_ANALYST METRICS employees.headcount DIMENSIONS employees.department);
```
Then open the app: tabs render, **Ask Your Data** answers "headcount by department", **Documents** answers
"What is the PTO policy?" with sources, and chat survives a refresh.

## Fixes

| Symptom | Cause | Fix |
|---|---|---|
| Charts blank / "no data" | GOLD empty — medallion not built/flattened | finish `medallion-build`: ingest Bronze → `SP_BUILD_SILVER` → `04`-equivalent Gold |
| Documents tab: "No relevant information found" | Search still indexing, or `DOCUMENT_CHUNKS` empty | wait ~1 min; confirm docs loaded + `CALL SP_REBUILD_DOC_CHUNKS()` ran |
| Either assistant dead | `SNOWFLAKE.CORTEX_USER` not granted | `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE ACCOUNTADMIN;` |
| App won't load / slow first load | compute pool suspended | first load after 5-min suspend takes ~30–60s; `SHOW COMPUTE POOLS;` |
| Two apps appear | `deploy_app.sql` ran on an account that already had the live app | drop the old auto-named Streamlit, keep `DASHBOARD_SPS` |
| Redeploy didn't update | deployed without `--replace` | re-run `snow streamlit deploy --replace` (or re-`FETCH` + `CREATE OR REPLACE STREAMLIT`) |
| Doc load hangs / "OAuth message timeout" | `snow sql PUT` negotiated a browser OAuth flow (even with a key-pair connection) | use the server-side `COPY FILES` from the git stage instead of `PUT` (preferred path above) |
