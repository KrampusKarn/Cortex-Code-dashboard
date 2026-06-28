# `src/` — setup SQL for the live DASHBOARD_SPS app

These scripts reproduce the backend of the **Employee 360 / DASHBOARD_SPS** Streamlit app
in `DEMO_EMPLOYEE_APP.PUBLIC`. They were captured from the live DEMO account
(`sevenpeaks_partner_demo`) via `GET_DDL` and made **non-destructive** (`IF NOT EXISTS`),
so running them never drops existing data.

## Files & run order

| Order | File | Creates |
|---|---|---|
| 1 | `00_setup.sql` | Warehouses, database, schema, stages, and **all 40 tables** (empty) |
| 2 | `migrations/2026-06_rename_freshteam_to_omni.sql` | One-time: rename `EMPLOYEES.FRESHTEAM_ID → OMNI_EMPLOYEE_ID` (only on an account that predates the rename; fresh `00_setup.sql` builds already have the new name) |
| 3 | **Populate Silver — pick A or B** | |
| 3·A | `seeders/` (`seed_all.sh --reset`) | **Direct load** — one seeder per source (OmniHR → Harvest → Lattice). The "clone the repo" path. See [`seeders/README.md`](seeders/README.md). |
| 3·B | `02_bronze.sql` → `03_silver.sql` | **Medallion ELT** — extract the mock API (`../mock_api/`) into Bronze VARIANT, then flatten into Silver. The live-demo path. Start the API + tunnel with `../mock_api/serve_eai.sh start` (ngrok static domain = stable URL; see [`mock_api/README.md`](../mock_api/README.md)). |
| 4 | `04_gold.sql` | **Gold** — the schema the dashboard reads: 1:1 entity pass-through views (over SILVER) **+** curated analytics views (incl. `EMPLOYEE_360`, the canonical employee dimension). The app's `SCH="GOLD"` resolves every tab here. OmniHR + Harvest only (no Lattice). |
| 5 | `05_semantic_analyst.sql` | **`GOLD.HR_ANALYST` semantic view** — the Cortex Analyst model behind the "Ask Your Data" tab (people / time / projects / leave / recruiting, with dimensions, metrics, relationships, synonyms) |
| 6 | `01_document_ingestion.sql` | The RAG chat backend: `SP_REBUILD_DOC_CHUNKS`, the `COMPANY_DOCS` stream + ingest/refresh tasks, and the `COMPANY_KB_SEARCH` Cortex Search service over `DOCUMENT_CHUNKS` (the "Documents" assistant) |
| 7 | `deploy_app.sql` **or** `snow streamlit deploy` | Deploy the dashboard. **Workspace / Cortex Code-native:** `deploy_app.sql` (git repo object + `CREATE STREAMLIT` from `deployed_app/app/` — no CLI; fill in the repo owner/name/branch). **CLI:** `snow streamlit deploy` (see `../app/snowflake.yml`). Then load docs: upload `../docs/*.md` to `@COMPANY_DOCS` (or `COPY FILES` from the git stage) and `CALL SP_REBUILD_DOC_CHUNKS()`. |

```bash
snow sql -c sevenpeaks_partner_demo --role ACCOUNTADMIN -f 00_setup.sql
snow sql -c sevenpeaks_partner_demo --role ACCOUNTADMIN -f migrations/2026-06_rename_freshteam_to_omni.sql   # one-time

# 3·A — direct synthetic load
./seeders/seed_all.sh --reset

# 3·B — OR the medallion ELT (one-time object build)
snow sql -c sevenpeaks_partner_demo --role ACCOUNTADMIN -f 02_bronze.sql       # BRONZE/SILVER/GOLD schemas + EAI + ingest procs
snow sql -c sevenpeaks_partner_demo --role ACCOUNTADMIN -f 03_silver.sql       # SILVER tables + flatten procs
#     start the API + tunnel, then ingest. ngrok static domain => rule is pinned (add --set-rule the first time):
#       cd ../mock_api && ./serve_eai.sh start
#     run the two CALLs it prints (URL = your stable https://<you>.ngrok-free.app):
snow sql -c sevenpeaks_partner_demo --role ACCOUNTADMIN -q "CALL BRONZE.SP_INGEST_ALL_BRONZE('https://<your-static-domain>');"
snow sql -c sevenpeaks_partner_demo --role ACCOUNTADMIN -q "CALL SILVER.SP_BUILD_SILVER();"

snow sql -c sevenpeaks_partner_demo --role ACCOUNTADMIN -f 04_gold.sql                # GOLD views (GOLD schema)
snow sql -c sevenpeaks_partner_demo --role ACCOUNTADMIN -f 05_semantic_analyst.sql    # GOLD.HR_ANALYST semantic view (Cortex Analyst)
snow sql -c sevenpeaks_partner_demo --role ACCOUNTADMIN -f 01_document_ingestion.sql  # RAG chat (Cortex Search)
# then PUT ../docs/*.md to @COMPANY_DOCS, REFRESH, and CALL SP_REBUILD_DOC_CHUNKS()
```

## Facts about the live account (so nothing drifts)

- **Two warehouses, by design:** `DEMO_EMPLOYEE_APP` is the app's `query_warehouse`; `DEMO_WH`
  runs the Cortex Search service and the ingestion tasks.
- **Ownership:** objects are owned by `ACCOUNTADMIN` (the app runs with owner's rights and must
  write the chat tables) — create them as `ACCOUNTADMIN`.
- **The chat indexes `DOCUMENT_CHUNKS`,** parsed from `../docs/*.md` (pto-policy, health-benefits,
  upcoming-events). The curated `COMPANY_KNOWLEDGE_BASE` table still exists but is **no longer
  indexed** — kept only for lineage.

## Data

`00_setup.sql` creates **structure only** (no rows). Load synthetic, API-realistic, FK-coherent
data with the per-source seeders in [`seeders/`](seeders/) — `./seeders/seed_all.sh --reset`
regenerates all 35 data tables (OmniHR → Harvest → Lattice). This is also how the two lookup
tables that were **empty in the live account** (`BUSINESS_UNITS`, `DEPARTMENTS_DETAIL`) get
populated, so dashboard joins stop showing gaps.
