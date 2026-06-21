---
name: dashboard-rag-scaffold
description: Take a validated schema_spec.json plus its generated seed CSVs and stand up the dashboard on Snowflake. Renders the deployable bundle with templates/render.py (deploy SQL + Streamlit RAG app), loads the data and creates the Cortex Search service via deploy/run.sh, deploys the Streamlit-in-Snowflake app with the snow CLI, verifies the RAG Assistant returns grounded answers, and explains how to re-point the app at production data later. Use after the spec validates and seed CSVs exist.
tools:
- read_file
- run_shell_command
---

# When to Use

- A `schema_spec.json` validates AND seed CSVs have been generated (and a curated `kb_content.json` exists).
- The user wants to deploy/stand up the dashboard, create the Cortex Search service, or publish the Streamlit app + RAG chat.
- The user asks to "deploy the dashboard", "set up the Cortex chat", "ship it to Snowflake", or "re-point this at production data".
- Keywords: deploy, Snowflake, Cortex Search, Streamlit, RAG, run.sh, snow CLI, go live.

Do NOT use this skill to design the schema (`api-schema-extraction`) or to generate data (`demo-data-generator`).

# Prerequisites

1. A validated `schema_spec.json`, its `kb_content.json`, and generated seed CSVs (a `seed/` dir).
2. The **`snow` CLI** installed and a connection configured in `~/.snowflake/connections.toml` (the kit never stores credentials in-repo). Confirm with `snow connection test -c <conn>`.
3. A Snowflake account with **Cortex enabled** (Cortex Search + `SNOWFLAKE.CORTEX.COMPLETE`/`SEARCH_PREVIEW`).
4. The deploy role needs the Cortex role:
   ```sql
   GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <app.role>;
   ```

# Workflows

## 1. Render the deployable bundle

```bash
python3 templates/render.py --spec path/to/schema_spec.json --out path/to/bundle/
```
Produces:
- `bundle/deploy/00_bootstrap.sql` — warehouse + database + schema + stages
- `bundle/deploy/01_ddl.sql` — `CREATE TABLE` for every table (incl. chat tables, with AUTOINCREMENT PKs + timestamp defaults)
- `bundle/deploy/04_cortex_search.sql` — the Cortex Search service over the knowledge-base table
- `bundle/deploy/05_load_seed.sql` — `COPY INTO` for every data table + a row-count check
- `bundle/deploy/run.sh` — one-shot orchestrator
- `bundle/app/{app_config.py, snowflake.yml, _core.py, rag_chat.py, streamlit_app.py, environment.yml}`

For the worked examples the bundle is rendered in place (the `deploy/` and `app/` dirs sit next to the spec and `seed/`), so you can point `run.sh` straight at the existing `seed/`.

## 2. Load data + create the search service

```bash
bundle/deploy/run.sh <snow_connection_name>
```
It runs, in order: `00_bootstrap.sql` → `01_ddl.sql` → `PUT` every `../seed/*.csv` to the stage → `05_load_seed.sql` → `04_cortex_search.sql`, then **asserts every data table is non-empty** (it exits non-zero if any table loaded 0 rows — this is the guard against the silent empty-table bug). Finally it prints the Streamlit deploy command.

You can also run the four SQL files individually with `snow sql -c <conn> -f <file>` if you prefer step-by-step.

## 3. Let the Cortex Search service finish indexing

`CREATE CORTEX SEARCH SERVICE` builds embeddings asynchronously (governed by `TARGET_LAG`, default `1 hour`, but the initial build is usually minutes for a small KB). Until it is ready, the RAG Assistant returns no results. Check:
```sql
SHOW CORTEX SEARCH SERVICES IN SCHEMA <db>.<schema>;
DESCRIBE CORTEX SEARCH SERVICE <db>.<schema>.<service_name>;
```

## 4. Deploy the Streamlit app

From the bundle's `app/` directory (it contains `snowflake.yml`):
```bash
cd path/to/bundle/app
snow streamlit deploy --connection <snow_connection_name> --replace
```
All artifacts listed in `snowflake.yml` (`streamlit_app.py`, `_core.py`, `rag_chat.py`, `app_config.py`, `environment.yml`) are staged together — it is a multi-file app. Open the returned URL.

## 5. Verify

- **Assistant tab**: ask one of the `dashboard.suggested_prompts`. You should get a grounded answer with a **Sources** expander citing KB docs. If it says "No relevant information found", the search service is still indexing or the KB table is empty.
- **Dashboard tabs**: charts render and the current month/period has data.
- **Chat persistence**: ask a question, refresh the app — the conversation is still there (CHAT_SESSIONS/CHAT_MESSAGES).

Use `references/deploy_checklist.md` for the exact ordered commands and `references/troubleshooting.md` when something is off.

## 6. Re-point at production data later

The app reads only logical table names from `app_config.py`. To go from demo → real data without touching app code:
1. Land real API data into bronze tables (Fivetran / custom ingestion).
2. Create **views** in the app's schema that map the logical table names + columns the app expects to your bronze tables — use the `api_field` annotations in the spec as the field-mapping guide.
3. Re-deploy the app (same `app_config.py`) — it now reads the views.
4. Replace any mock-derived columns with live Cortex calls (e.g. `SNOWFLAKE.CORTEX.SENTIMENT(written_feedback)` for a sentiment score).

# Best Practices

- **Grant `SNOWFLAKE.CORTEX_USER` before deploying** — the most common cause of a dead Assistant tab.
- **Trust the row-count assertion** in `run.sh`; if it fails, a `COPY INTO` rejected rows (often a header/column mismatch) — fix the spec/CSV, don't bypass the check.
- **One warehouse name** comes from `app.warehouse`; don't introduce a second name in any manual step.
- **Wait for indexing** before judging the RAG quality.
- **Never put credentials in the repo** — the `snow` CLI reads them from `~/.snowflake/connections.toml`.
- **Re-deploy with `--replace`** so the live app updates in place.

# Examples

## Example 1: Deploy the HRIS example end to end

Agent: `python3 templates/render.py --spec examples/hris_people/schema_spec.json --out examples/hris_people` → `examples/hris_people/deploy/run.sh my_demo_conn` (loads + verifies row counts + creates `COMPANY_KB_SEARCH`) → `cd examples/hris_people/app && snow streamlit deploy --connection my_demo_conn --replace` → opens the app, asks "What is the PTO policy?", confirms a grounded answer with sources.

## Example 2: Assistant returns nothing

Agent: checks (a) `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE SYSADMIN;` is in place; (b) `SHOW CORTEX SEARCH SERVICES` shows the service and it has finished its initial build; (c) `SELECT COUNT(*) FROM <db>.<schema>.COMPANY_KNOWLEDGE_BASE` is non-zero. Fixes whichever is missing and retries.

## Example 3: A table loaded zero rows

Agent: `run.sh` exited at the verification step naming the empty table. Inspects the `COPY INTO` for that table and the CSV header — finds a column-list/header mismatch, corrects the spec column order, regenerates that CSV, and re-runs the load.

# References

- `references/deploy_checklist.md` — the exact ordered commands from render → load → search → deploy → verify.
- `references/troubleshooting.md` — symptoms and fixes (CORTEX_USER grant, indexing lag, empty tables, warehouse name, connection auth).
