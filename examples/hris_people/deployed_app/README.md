# DASHBOARD_SPS — Employee 360

The deployed Streamlit app behind the **Employee 360 / DASHBOARD_SPS** demo, running in
`DEMO_EMPLOYEE_APP.PUBLIC`. A Snowflake-native HRIS dashboard that reads a **Bronze → Silver → Gold**
medallion and ships **two Cortex assistants**:

- **Documents** — a Cortex Search RAG chat grounded in company documents (`DOCUMENT_CHUNKS`).
- **Ask Your Data** — Cortex Analyst answering natural-language questions over the
  `GOLD.HR_ANALYST` semantic view.

> A bespoke, hand-built app — not the kit's spec-driven tutorial output. The kit's templated
> learn-path renders its own example with `templates/render.py`; the `../schema_spec.json` and
> `../kb_content.json` alongside this folder are kept as lineage only.

## Layout

Four concerns, four folders:

| Path | Role |
|---|---|
| `app/streamlit_app.py` | The running app (single-file monolith). Reads `GOLD`; the dashboard tabs + both assistants. |
| `app/environment.yml`, `app/snowflake.yml` | Streamlit runtime deps + the redeploy descriptor (targets the live app object). |
| `src/` | Setup + medallion SQL (`00`→`05`), `deploy_app.sql`, `seeders/`, `migrations/`. See [`src/README.md`](src/README.md). |
| `mock_api/` | FastAPI replica of the OmniHR + Harvest APIs — the live Extract source. See [`mock_api/README.md`](mock_api/README.md). |
| `docs/*.md` | The RAG corpus (health benefits, PTO, upcoming events). |
| `ARCHITECTURE.md` | Design notes. |

## Data model

The dashboard reads one schema: **`GOLD`**. Gold is 1:1 pass-through views over **`SILVER`** plus
curated analytics views (headcount, utilization, `EMPLOYEE_360`, …). Silver is the typed, flattened
entity layer; Bronze is the raw VARIANT landing. Silver gets populated two ways — both converge on
the same tables, so Gold and the dashboard look identical either way:

- **Medallion ELT (mock API):** `mock_api/` serves OmniHR + Harvest JSON over an HTTPS tunnel;
  Snowflake extracts it into Bronze, then `SP_BUILD_SILVER` flattens it into Silver.
- **Seeders (direct load):** `src/seeders/` writes the same synthetic, FK-coherent data straight
  into the tables — no API or external-access integration needed.

## Knowledge base — the Documents assistant

The chat's knowledge base is document-driven: drop company files into the `COMPANY_DOCS` stage and
they are parsed, chunked, indexed, and retrieved by Cortex Search.

```
@COMPANY_DOCS (stage + directory table)        ← drop PDF / DOCX / PPTX / TXT / MD here
   │  CORTEX.PARSE_DOCUMENT                 → text
   │  CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER → chunks (1000 chars, 200 overlap)
   ▼
DOCUMENT_CHUNKS (FILE_NAME, TITLE, CATEGORY, CHUNK_INDEX, CONTENT)
   ▼
COMPANY_KB_SEARCH (Cortex Search, ON CONTENT) ← what the chat queries
```

- **Auto-ingest:** a `STREAM` on the stage's directory table plus two `TASK`s keep the index in
  sync as files are added/changed/removed (`DOCS_REFRESH_TASK` refreshes the directory every minute;
  `DOCS_INGEST_TASK` runs `SP_REBUILD_DOC_CHUNKS()` only when the stream has changes).
- **Title / Category:** taken from each document's first `# Heading` and a `**Category:** X` line
  (fallbacks: filename, `General`).
- **Service contract:** `COMPANY_KB_SEARCH` exposes `CONTENT` / `TITLE` / `CATEGORY` — the app reads
  only those.

## Running the demo

The app and both assistants deploy straight from the public repo
**https://github.com/KrampusKarn/Cortex-Code-dashboard** (`main`). Connect it once in Snowsight:
**Projects → Workspaces → From Git repository** → paste the URL (public, no auth). Or let
`src/deploy_app.sql` create the Snowflake Git repository object.

**Prerequisites (any account):** Cortex enabled, and the deploy role granted Cortex:
`GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE ACCOUNTADMIN;`. If the LLM / embedding models
aren't available in your region, run `ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';`.
Run all SQL as `ACCOUNTADMIN`; every script is idempotent.

### Path A — DEMO account + mock API (medallion ELT)

Demonstrates the live Extract → Bronze → Silver → Gold flow. The mock API + tunnel run on your
machine; pass `--connection <your-demo-connection>` on every `snow` command.

0. *(optional — for a clean "CoCo builds it from empty" run)* `src/reset_for_coco.sql` — drops the
   `BRONZE`/`SILVER`/`GOLD` schemas (keeps the app, chat tables, Cortex Search, and docs).
1. `src/00_setup.sql` — database, warehouses, PUBLIC schema, chat + document tables (idempotent).
2. Start the API + tunnel on your machine: `cd mock_api && ./serve_eai.sh start`.
3. `src/02_bronze.sql` — creates `BRONZE`/`SILVER`/`GOLD`, the external-access integration, the
   network rule, and the ingest procedures.
4. Point the network rule at your tunnel: `./serve_eai.sh start --set-rule`. Needed the first time
   and **after any reset** (`02_bronze` recreates the rule with a placeholder host); skip only if
   the rule already points at your stable ngrok domain.
5. Ingest: `CALL BRONZE.SP_INGEST_ALL_BRONZE('https://<your-domain>');` — use the exact URL
   `serve_eai.sh` printed.
6. `src/03_silver.sql`, then `CALL SILVER.SP_BUILD_SILVER();`
7. `src/04_gold.sql` → `src/05_semantic_analyst.sql` → `src/01_document_ingestion.sql`.
8. Deploy the app + load the documents (see **Deploy** below).

### Path B — trial account + offline Bronze load (full medallion, no EAI)

Trial accounts can't use an External Access Integration, so instead of pulling the mock API over a
tunnel, generate the **same JSON locally** and load it straight into Bronze. Same
Bronze → Silver → Gold flow as Path A — just fed from files instead of HTTP. Pass
`--connection <your-trial-connection>` on every command.

1. `src/00_setup.sql` — database, warehouses, PUBLIC schema, chat + document tables.
2. `src/03_silver.sql` — Silver schema + typed tables + `SP_BUILD_SILVER` (the flatten proc).
3. Load Bronze (the offline twin of `SP_INGEST_ALL_BRONZE`), then flatten to Silver:
   ```bash
   cd src/seeders && ./seed_bronze.sh --connection <your-trial-connection>
   # then (the loader prints these):
   snow sql -c <your-trial-connection> --role ACCOUNTADMIN -q "CALL DEMO_EMPLOYEE_APP.SILVER.SP_BUILD_SILVER();"
   ```
4. `src/04_gold.sql` → `src/05_semantic_analyst.sql` → `src/01_document_ingestion.sql`.
5. Load the documents + deploy the app (below).

### Deploy the app + load the documents

- **App** — on a **fresh account** (trial), run `src/deploy_app.sql` (creates the Git repository
  object + `CREATE STREAMLIT` from the repo's `app/` folder, no CLI). On the **existing DEMO
  account**, redeploy in place from `app/`: `snow streamlit deploy --replace -c <connection>`
  (it reads `snowflake.yml` and updates the live object, preserving its URL).
- **Documents** — upload `docs/*.md` and rebuild the chunks:
  ```bash
  snow sql -c <connection> --role ACCOUNTADMIN -q \
    "PUT 'file://docs/*.md' @DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"
  snow sql -c <connection> --role ACCOUNTADMIN -q \
    "ALTER STAGE DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS REFRESH; CALL DEMO_EMPLOYEE_APP.PUBLIC.SP_REBUILD_DOC_CHUNKS();"
  ```

## Live-account facts

- **Two warehouses:** `DEMO_EMPLOYEE_APP` (the app's query warehouse) and `DEMO_WH` (Cortex Search +
  ingest tasks).
- **Ownership:** objects are owned by `ACCOUNTADMIN` — the app runs with owner's rights so it can
  write the chat tables.
- **App object:** the Snowsight-generated id `YFE09SNXUSHHL2EH` (title `DASHBOARD_SPS`);
  `app/snowflake.yml` targets it so `snow streamlit deploy` updates in place.
