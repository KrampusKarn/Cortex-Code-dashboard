# `src/` — setup SQL for the DASHBOARD_SPS app

These scripts build the backend of the **Employee 360 / DASHBOARD_SPS** Streamlit app: the schemas
and tables, the Bronze → Silver → Gold medallion, the `GOLD.HR_ANALYST` semantic view, and the
document-ingestion chat. All are idempotent (`IF NOT EXISTS` / `CREATE OR REPLACE`), so a re-run
never drops existing data.

## Files & run order

The dashboard reads **`GOLD`**, which is built from **`SILVER`**. Steps 1–2 and 4–7 are common;
**step 3** is how you fill Bronze — **DEMO** (live mock-API ingest, needs External Access) or **7ptrial**
(offline seeder, trial-friendly).

> **These committed files are the golden reference and the 7ptrial runtime.** On the **DEMO path** the
> presenter does NOT run `02→05.sql` by hand — Cortex Code (the `medallion-build` / `cortex-analyst-search`
> skills) *generates* the equivalent SQL into `build/`, you review each layer, then CoCo runs it. The table
> below is the canonical shape that generated SQL converges on, and exactly what the **7ptrial** path runs.

| Order | File | Creates |
|---|---|---|
| 1 | `00_setup.sql` | The PUBLIC **app/RAG layer only**: warehouses, database, schema, the `COMPANY_DOCS` stage, and the 4 chat/document tables. (Entity DDL lives in SILVER — step 2.) |
| 2 | `03_silver.sql` | The **Silver** schema + typed entity tables (the read source for Gold). |
| 3 | **Fill Bronze → flatten to Silver — DEMO or 7ptrial** (both end the same way) | |
| 3·DEMO | `02_bronze.sql` → `CALL BRONZE.SP_INGEST_ALL_BRONZE(<url>)` → `CALL SILVER.SP_BUILD_SILVER()` | **Live API ingest (connection `sevenpeaks_partner_demo`).** Extract the mock API into Bronze VARIANT over the tunnel, then flatten. On the DEMO path the `medallion-build` skill generates Bronze+Silver into `build/` for review; this committed `02`/`03` is the reference. Start the API with `../mock_api/serve_eai.sh start` (see [`mock_api/README.md`](../mock_api/README.md)). |
| 3·7ptrial | `seeders/seed_bronze.sh` → `CALL SILVER.SP_BUILD_SILVER()` | **Offline Bronze load (connection `7ptrial`, no EAI).** Generates the same JSON locally and loads it into Bronze VARIANT — no tunnel — then the same flatten. The full medallion without External Access. See [`seeders/README.md`](seeders/README.md). |
| 4 | `04_gold.sql` | **Gold** — 1:1 pass-through views over Silver + curated analytics views (incl. `EMPLOYEE_360`, the canonical employee dimension). The app's `SCH="GOLD"` resolves every tab here. |
| 5 | `05_semantic_analyst.sql` | **`GOLD.HR_ANALYST` semantic view** — the Cortex Analyst model behind the "Ask Your Data" tab (people / time / projects / leave / recruiting). |
| 6 | `01_document_ingestion.sql` | The RAG chat backend: `SP_REBUILD_DOC_CHUNKS`, the `COMPANY_DOCS` stream + ingest/refresh tasks, and the `COMPANY_KB_SEARCH` Cortex Search service over `DOCUMENT_CHUNKS` (the "Documents" assistant). |
| 7 | `deploy_app.sql` **or** `snow streamlit deploy` | Deploy the dashboard. **Workspace / Cortex Code-native:** `deploy_app.sql` (Git repository object + `CREATE STREAMLIT` from `deployed_app/app/`). **CLI:** `snow streamlit deploy` from `../app/`. Then load docs: PUT `../docs/*.md` to `@COMPANY_DOCS` and `CALL SP_REBUILD_DOC_CHUNKS()`. |
| — | `connect_git.sql` | (Standalone) wire Snowflake → the public GitHub repo (API integration + git repository object + fetch). Included inline in `deploy_app.sql`; run it on its own when you want the git stage first (e.g. `COPY FILES` docs, or letting CoCo read repo files). |
| — | `migrations/` | (Optional) one-off schema migrations for accounts that predate a change — not needed for a fresh build. |

```bash
# <conn> = sevenpeaks_partner_demo (DEMO) or 7ptrial (7ptrial)
# common
snow sql -c <conn> --role ACCOUNTADMIN -f 00_setup.sql
snow sql -c <conn> --role ACCOUNTADMIN -f 03_silver.sql

# 3·DEMO — live API ingest into Bronze (needs External Access; connection sevenpeaks_partner_demo)
#   On the DEMO path this is the reference shape — the medallion-build skill generates the equivalent
#   into build/ for review, then runs it. The raw SQL is here for sanity-checking, not hand-running.
snow sql -c sevenpeaks_partner_demo --role ACCOUNTADMIN -f 02_bronze.sql
#   start the API + tunnel (ngrok static domain; add --set-rule the first time):
#     cd ../mock_api && ./serve_eai.sh start
snow sql -c sevenpeaks_partner_demo --role ACCOUNTADMIN -q "CALL BRONZE.SP_INGEST_ALL_BRONZE('https://<your-domain>');"
snow sql -c sevenpeaks_partner_demo --role ACCOUNTADMIN -q "CALL SILVER.SP_BUILD_SILVER();"

# 3·7ptrial — OR offline Bronze load (no External Access; connection 7ptrial), then the same flatten
cd seeders && ./seed_bronze.sh --connection 7ptrial && cd ..
snow sql -c 7ptrial --role ACCOUNTADMIN -q "CALL SILVER.SP_BUILD_SILVER();"

# finish (both paths)
snow sql -c <conn> --role ACCOUNTADMIN -f 04_gold.sql
snow sql -c <conn> --role ACCOUNTADMIN -f 05_semantic_analyst.sql
snow sql -c <conn> --role ACCOUNTADMIN -f 01_document_ingestion.sql
# then PUT ../docs/*.md to @COMPANY_DOCS, REFRESH, and CALL SP_REBUILD_DOC_CHUNKS()
```

## Live-account facts

- **Two warehouses:** `DEMO_EMPLOYEE_APP` is the app's `query_warehouse`; `DEMO_WH` runs the Cortex
  Search service and the ingestion tasks.
- **Ownership:** objects are owned by `ACCOUNTADMIN` (the app runs with owner's rights and must
  write the chat tables) — create them as `ACCOUNTADMIN`.
- **The chat indexes `DOCUMENT_CHUNKS`,** parsed from `../docs/*.md` (pto-policy, health-benefits,
  upcoming-events).
