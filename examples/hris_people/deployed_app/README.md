# DASHBOARD_SPS — live SPS demo deployment (Employee 360)

This folder version-controls the **actual deployed Streamlit app** behind the SPS
"Employee 360 / DASHBOARD_SPS" demo in the DEMO Snowflake account
(`DEMO_EMPLOYEE_APP.PUBLIC`, region `AWS_AP_SOUTH_1`). The source was previously
only on the Snowflake stage; it is recovered here so the deployment is reproducible.

> This is a bespoke, hand-built dashboard — **not** the kit's spec-driven tutorial app.
> Attendees following the kit's templated learn-path render their own example with
> `templates/render.py`. This folder is hand-built, not generated output — its `app/` holds the
> live Streamlit monolith; `../schema_spec.json` and `../kb_content.json` are kept as lineage only.

## What was fixed: Cortex RAG chat

The chat ("Company Knowledge Assistant", tab 1) was disabled in `streamlit_app.py`
with a hardcoded stub left over from the previous region:

> *"Company Knowledge Assistant is disabled in this region — Cortex Search Service
> is not available in AWS_AP_SOUTHEAST_7."*

After the move to `AWS_AP_SOUTH_1` with account parameter
`CORTEX_ENABLED_CROSS_REGION = ANY_REGION`, the LLM (`mistral-large2`) and embedding
(`snowflake-arctic-embed-m-v1.5`) both work, and the Cortex Search service builds and
returns results. The fix has two parts:

1. **Backend** — `src/00_setup.sql` creates the full schema (warehouses, db, stages, and all
   40 tables incl. the chat-persistence tables `CHAT_SESSIONS` / `CHAT_MESSAGES`) in
   `DEMO_EMPLOYEE_APP.PUBLIC`, owned by `ACCOUNTADMIN` (the app runs with owner's rights and
   writes the chat tables). The `COMPANY_KB_SEARCH` Cortex Search service the chat queries is
   defined by the document-ingestion pipeline below (`src/01_document_ingestion.sql`), which
   **supersedes** the original curated `COMPANY_KNOWLEDGE_BASE` source.

2. **App** — `streamlit_app.py` tab 1 now runs the real RAG block (Cortex
   `SEARCH_PREVIEW` → grounded `COMPLETE` → message persistence) instead of the stub.

## Knowledge base: drop documents in a stage

The chat's knowledge base is **document-driven**: drop company files into the
`COMPANY_DOCS` stage and they are parsed, chunked, indexed, and retrieved by Cortex
Search — no manual data entry. This replaces the old curated `COMPANY_KNOWLEDGE_BASE`
table as the chat's source.

Pipeline (`src/01_document_ingestion.sql`):

```
@COMPANY_DOCS (stage + directory table)        ← drop PDF / DOCX / PPTX / TXT / MD here
   │  CORTEX.PARSE_DOCUMENT                 → text
   │  CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER → chunks (1000 chars, 200 overlap)
   ▼
DOCUMENT_CHUNKS (FILE_NAME, TITLE, CATEGORY, CHUNK_INDEX, CONTENT)
   ▼
COMPANY_KB_SEARCH (Cortex Search, ON CONTENT) ← what the chat queries (app unchanged)
```

- **Auto-ingest:** a `STREAM` on the stage's directory table plus two `TASK`s keep the
  index in sync as files are added/changed/removed (typically ~1–2 min): `DOCS_REFRESH_TASK`
  refreshes the directory every minute, and `DOCS_INGEST_TASK` runs `SP_REBUILD_DOC_CHUNKS()`
  only when the stream has changes.
- **Title / Category:** taken from each document's first `# Heading` and a `**Category:** X`
  line (fallbacks: filename, `General`); HTML entities from parsing are decoded.
- **Same app contract:** the service keeps the name `COMPANY_KB_SEARCH` and exposes
  `CONTENT` / `TITLE` / `CATEGORY`, so `streamlit_app.py` needs no change.

Sample documents live in `docs/` (health benefits, PTO policy, upcoming events). Add your
own by dropping files in the stage and running the initial load (the tasks handle changes
afterward):

```bash
snow sql -c <connection> --role ACCOUNTADMIN -q \
  "PUT 'file://docs/*.md' @DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"
snow sql -c <connection> --role ACCOUNTADMIN -q \
  "ALTER STAGE DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS REFRESH; CALL DEMO_EMPLOYEE_APP.PUBLIC.SP_REBUILD_DOC_CHUNKS();"
```

## Files

The folder separates the four concerns — **app** (Python/Streamlit), **src** (SQL), **mock_api**
(the Extract source), and **docs** (the RAG corpus):

| Path | Role |
|---|---|
| `app/streamlit_app.py` | **The running app** (single-file monolith). Reads `GOLD`; dashboard tabs + Documents (Cortex Search) + Ask Your Data (Cortex Analyst). |
| `app/environment.yml`, `app/snowflake.yml` | Streamlit runtime deps + the redeploy descriptor (targets the existing app object). |
| `ARCHITECTURE.md` | Design notes for the deployed app. |
| `src/00_setup.sql` | From-scratch infra: warehouses, db, schema, stages, all 40 tables (incl. chat tables). Non-destructive (`IF NOT EXISTS`); captured from the live account via `GET_DDL`. |
| `src/01_document_ingestion.sql` | Document-ingestion pipeline + the `COMPANY_KB_SEARCH` service. |
| `src/02_bronze.sql` … `05_semantic_analyst.sql` | The Bronze→Silver→Gold medallion ELT + the `GOLD.HR_ANALYST` semantic view. |
| `src/seeders/` | Per-source synthetic-data seeders (OmniHR / Harvest / Lattice) — structure-driven, FK-coherent, API-realistic. `seed_all.sh --reset` for a full reseed. See `src/seeders/README.md`. |
| `src/migrations/` | One-off schema migrations (e.g. the `FRESHTEAM_ID → OMNI_EMPLOYEE_ID` rename). |
| `src/README.md` | Run order + live-account facts (two warehouses, `ACCOUNTADMIN` ownership, doc-driven chat). |
| `mock_api/` | Standalone FastAPI replica of the OmniHR + Harvest APIs (serves the same synthetic data the seeders load) — the live *Extract* source for the Bronze→Silver→Gold demo. See `mock_api/README.md`. |
| `docs/*.md` | Sample company documents (health benefits, PTO, upcoming events) — the live chat's actual source. |

## Redeploy

```bash
# 1) Infra + all 40 tables (non-destructive IF NOT EXISTS; a safe no-op against the live account)
snow sql -c <connection> --role ACCOUNTADMIN -f src/00_setup.sql

# 2) Document-ingestion pipeline + Cortex Search service (idempotent)
snow sql -c <connection> --role ACCOUNTADMIN --enable-templating NONE \
  -f src/01_document_ingestion.sql

# 3) Upload the sample docs + initial load (tasks auto-ingest changes afterward)
snow sql -c <connection> --role ACCOUNTADMIN -q \
  "PUT 'file://docs/*.md' @DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"
snow sql -c <connection> --role ACCOUNTADMIN -q \
  "ALTER STAGE DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS REFRESH; CALL DEMO_EMPLOYEE_APP.PUBLIC.SP_REBUILD_DOC_CHUNKS();"

# 4) App (updates the existing object in place; preserves its URL)
snow streamlit deploy --replace --role ACCOUNTADMIN -c <connection> --project app
```

> `--enable-templating NONE` on step 2 is belt-and-suspenders; the SQL avoids literal
> `&` (it uses `CHR(38)`), so it also runs cleanly in a Snowsight worksheet.

Notes:
- The app object's identifier is the Snowsight-generated `YFE09SNXUSHHL2EH`
  (title `DASHBOARD_SPS`); `snowflake.yml` targets it so the redeploy updates in
  place rather than creating a duplicate.
- `query_warehouse` is `DEMO_EMPLOYEE_APP` (an existing warehouse), matching the
  live object.

## Known follow-up (not changed here)

The app writes chat rows with string-interpolated SQL (with quote-escaping). The kit
convention (see `templates/app/rag_chat.py`) is fully parameterized binds. Hardening
this app to parameterized writes is a sensible follow-up; it was left at parity to keep
the chat-restore change minimal.
