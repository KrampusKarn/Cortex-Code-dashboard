# DASHBOARD_SPS — Employee 360

The deployed Streamlit app behind the **Employee 360 / DASHBOARD_SPS** demo, running in
`DEMO_EMPLOYEE_APP.PUBLIC`. A Snowflake-native HRIS dashboard that reads a **Bronze → Silver → Gold**
medallion and ships **two Cortex assistants**:

- **Documents** — a Cortex Search RAG chat grounded in company documents (`DOCUMENT_CHUNKS`).
- **Ask Your Data** — Cortex Analyst answering natural-language questions over the
  `GOLD.HR_ANALYST` semantic view.

> The one worked demo, driven by the five Cortex Code skills (see the repo-root `README.md`). The
> `../schema_spec.json` alongside this folder is an entity/lineage reference only — not executed or validated.

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

Entity data lives entirely in the **medallion** (`BRONZE` → `SILVER` → `GOLD`). The dashboard reads
one schema, **`GOLD`** (1:1 pass-through views over `SILVER` plus curated analytics views like
`EMPLOYEE_360`); `SILVER` is the typed, flattened layer; `BRONZE` is the raw VARIANT landing.
**`PUBLIC` holds only the app + RAG objects** (chat tables, documents, Cortex Search, the app) — no
entity data.

`BRONZE` is filled two ways — both then run the **same** `SP_BUILD_SILVER` → Gold, so the dashboard
is identical either way:

- **Live API ingest (live-API path):** `mock_api/` serves OmniHR + Harvest JSON
  over an HTTPS tunnel; `SP_INGEST_ALL_BRONZE` pulls it into Bronze. Skill-driven — see the DEMO path below.
- **Offline seeder (trial account, no EAI):** `src/seeders/seed_bronze.sh` generates the same JSON and
  loads it straight into Bronze — no API or external-access integration needed.

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

### Live-API path — live mock API, skill-driven (presenter)

The showcase: Cortex Code **extracts the live API and generates the medallion**, pausing for your review at
each layer. You don't run `02→05.sql` by hand — those stay as the golden reference CoCo converges on (and the
offline seeder runtime). Pass `--connection <your-connection>` on every `snow` command (or set it as your default).

0. **Clean slate:** `src/reset_for_coco.sql` — drops only `BRONZE`/`SILVER`/`GOLD` (keeps the app, chat
   tables, Cortex Search, docs).
1. `src/00_setup.sql` — database, the two warehouses, PUBLIC app/RAG tables (idempotent).
2. Start the API + tunnel: `cd mock_api && ./serve_eai.sh start` (first time / after a reset: add `--set-rule`
   so the network rule points at your tunnel).
3. **Drive Cortex Code through the skills** (each medallion layer is generated into `build/`, reviewed, then
   run):
   - `api-schema-extraction` → reads the live API → `build/extraction_map.json`
   - `medallion-build` → `build/bronze.sql` **→ review → run** (sets the rule + `CALL SP_INGEST_ALL_BRONZE`) →
     `build/silver.sql` **→ review → run** (`CALL SP_BUILD_SILVER`) → `build/gold.sql` **→ review → run**
   - `cortex-analyst-search` → semantic view + document Search **→ review → run**
   - `dashboard-compose` → deploy the app + load the documents (see **Deploy** below)

> The committed `src/02→05.sql` are the **golden reference** these skills converge on — read them to
> sanity-check what CoCo generates; don't run them by hand on this path.

### Offline seeder path — trial account, offline Bronze load, no EAI (attendees)

Trial accounts can't use an External Access Integration, so instead of pulling the mock API over a tunnel,
load the **same JSON locally** into Bronze and run the committed reference SQL. Same Bronze → Silver → Gold as
the live-API path — just fed from files. Pass `--connection <your-connection>` on every command.

1. `src/00_setup.sql` — database, warehouses, PUBLIC app/RAG tables.
2. `src/03_silver.sql` — Silver schema + typed tables + `SP_BUILD_SILVER` (the flatten proc).
3. Load Bronze (the offline twin of `SP_INGEST_ALL_BRONZE`), then flatten to Silver:
   ```bash
   cd src/seeders && ./seed_bronze.sh --connection <your-connection>
   # then (the loader prints these):
   snow sql -c <your-connection> --role ACCOUNTADMIN -q "CALL DEMO_EMPLOYEE_APP.SILVER.SP_BUILD_SILVER();"
   ```
4. `src/04_gold.sql` → `src/05_semantic_analyst.sql` → `src/01_document_ingestion.sql`.
5. Load the documents + deploy the app (below).

### Deploy the app + load the documents

- **App** — on a **fresh account** (trial), run `src/deploy_app.sql` (creates the Git repository
  object + `CREATE STREAMLIT` from the repo's `app/` folder, no CLI). On the **existing DEMO
  account**, redeploy in place from `app/`: `snow streamlit deploy --replace -c <connection>`
  (it reads `snowflake.yml` and updates the live object, preserving its URL).
- **Documents** — load `docs/*.md` and rebuild the chunks. **Preferred (server-side, from the git stage —
  no local transfer, no OAuth prompt):**
  ```sql
  COPY FILES INTO @DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS
    FROM '@DEMO_EMPLOYEE_APP.PUBLIC.CORTEX_REPO/branches/main/examples/hris_people/deployed_app/docs/';
  ALTER STAGE DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS REFRESH;
  CALL DEMO_EMPLOYEE_APP.PUBLIC.SP_REBUILD_DOC_CHUNKS();
  ```
  **Fallback (local CLI upload)** — note `snow sql PUT` can hang on a browser OAuth flow even with a
  key-pair connection, so prefer `COPY FILES` above:
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
